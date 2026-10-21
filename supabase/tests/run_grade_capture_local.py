#!/usr/bin/env python3
"""Captura de notas en PostgreSQL desechable; nunca Supabase real.

Requiere Python 3, Docker y postgres:17-bookworm. Crea exclusivamente su propio
contenedor sin red ni puertos. Todas las consultas usan docker exec; no admite
DSN, endpoint ni credenciales. Auth es un fixture mínimo, no Supabase Auth real.
"""
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'seminario-capture-test-' + uuid.uuid4().hex[:10]
checks = 0


def run(*args, input=None, check=True):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=check)


def sql(query, ok=True):
    result = run('docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres', '-d',
                 'postgres', '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose',
                 input=query, check=False)
    if ok and result.returncode:
        raise AssertionError(result.stderr)
    if not ok and not result.returncode:
        raise AssertionError('Expected failure: ' + query)
    return result


def test(name, query, expected=None, error=None):
    global checks
    result = sql(query, ok=error is None)
    if expected is not None:
        assert result.stdout.strip() == str(expected), (name, result.stdout, result.stderr)
    if error:
        assert error in result.stderr, (name, result.stderr)
    checks += 1
    print('PASS', name, flush=True)


def scalar(uid, statement, role='authenticated'):
    claim = '' if uid is None else uid
    return (f"begin; set local role {role}; set local request.jwt.claim.sub = '{claim}'; "
            f"set local request.jwt.claims = '{{\"sub\":\"{claim}\",\"role\":\"{role}\"}}'; "
            f'{statement}; rollback;')


def uid(n):
    return f'10000000-0000-4000-8000-{n:012d}'


A, B, D, I, P, Q, IP, C, N, F = [uid(n) for n in range(1, 11)]
ZERO = '00000000-0000-0000-0000-000000000000'


def assignment(professor, code, period='DEMO 2026 — semestre de prueba'):
    return sql(f"select t.id from public.teaching_assignments t "
               f"join public.subjects s on s.id=t.subject_id "
               f"join public.academic_periods p on p.id=t.period_id "
               f"where t.professor_id='{professor}' and s.code='{code}' "
               f"and p.name='{period}'").stdout.strip()


def roster(assignment_id, offset='0', limit='20'):
    return f"public.get_teaching_roster('{assignment_id}',{offset},{limit})"



def committed(actor, statement):
    return scalar(actor, statement).replace('; rollback;', '; commit;')


def call(name, a, e, *args):
    return f"public.{name}('{a}','{e}'" + ''.join(',' + str(x) for x in args) + ')'


def output(name, a, e, *args):
    return 'select row_to_json(r) from ' + call(name, a, e, *args) + ' r'


def read(actor, a, e):
    import json
    return json.loads(sql(scalar(actor, output('get_teaching_grade', a, e))).stdout.strip())


def wait_sleep(tag):
    for _ in range(100):
        if sql(f"select count(*) from pg_stat_activity where application_name='{tag}' and wait_event='PgSleep'").stdout.strip() == '1':
            return
        time.sleep(.02)
    raise AssertionError('Concurrent writer did not acquire its transaction locks')


def background(query):
    proc = subprocess.Popen(['docker','exec','-i',NAME,'psql','-U','postgres','-d','postgres','-X','-q','-t','-A','-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    proc.stdin.write(query)
    proc.stdin.close()
    return proc


try:
    run('docker', 'run', '--rm', '-d', '--name', NAME, '--network', 'none', '-e',
        'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:17-bookworm')
    for _ in range(100):
        logs = run('docker', 'logs', NAME, check=False)
        if ('PostgreSQL init process complete' in logs.stdout + logs.stderr
                and run('docker', 'exec', NAME, 'pg_isready', '-U', 'postgres', check=False).returncode == 0):
            break
        time.sleep(.2)
    else:
        raise AssertionError('PostgreSQL did not start')
    sql('''create role anon nologin; create role authenticated nologin;
        create schema auth; create table auth.users (id uuid primary key);
        create function auth.uid() returns uuid language sql stable as $$
            select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
        $$;
        grant usage on schema auth to anon, authenticated;
        grant execute on function auth.uid() to anon, authenticated;''')
    for name in ['20261021000000_create_profiles.sql',
                 '20261021010000_create_academics.sql',
                 '20261021020000_create_enrollment_grades.sql',
                 '20261021030000_create_teaching_assignments.sql',
                 '20261021040000_enable_grade_capture.sql']:
        sql((ROOT / 'supabase/migrations' / name).read_text())
    sql('insert into auth.users(id) values ' + ','.join(f"('{u}')" for u in [A, B, D, I, P, Q, IP, C, N, F]) + ';')
    rows = [(A, 'Alumno Alfa', 'student', True), (B, 'Alumno Beta', 'student', True),
            (D, 'Alumno Delta', 'student', True), (I, 'Alumno inactivo', 'student', False),
            (P, 'Profesor P', 'professor', True), (Q, 'Profesor Q', 'professor', True),
            (IP, 'Profesor inactivo', 'professor', False), (C, 'Control Escolar', 'control_escolar', True)]
    sql('insert into public.profiles(id,full_name,role,active) values ' + ','.join(
        f"('{u}','{name}','{role}',{str(active).lower()})" for u, name, role, active in rows) + ';')
    sql("alter table public.profiles add column private_fixture text not null default 'no exponer al profesor';")

    academic_seed = (ROOT/'supabase/seeds/demo_enrollments.sql').read_text()
    grade_seed = (ROOT/'supabase/seeds/demo_grades.sql').read_text()
    teaching_seed = (ROOT/'supabase/seeds/demo_teaching.sql').read_text()
    smoke = (ROOT/'supabase/tests/grade_capture_rls.sql').read_text()
    for actor in [A,B,D,I]:
        # Seeds reject inactive profiles; temporarily enable only for fixture setup.
        sql(f"update public.profiles set active=true where id='{actor}'")
        sql(academic_seed.replace('PEGA_AQUI_EL_UID',actor))
    sql(f"update public.profiles set active=false where id='{I}'")
    for actor in [A,B]: sql(grade_seed.replace('PEGA_AQUI_EL_UID',actor))
    for actor in [P,Q]:
        sql(teaching_seed.replace('STUDENT_UID_AQUI',A).replace('PROFESSOR_UID_AQUI',actor))
    def enroll(student,code):
        return sql(f"select e.id from public.enrollments e join public.subjects s on s.id=e.subject_id where e.student_id='{student}' and s.code='{code}'").stdout.strip()
    af, ah, bf, dh, inactive = enroll(A,'DEMO-FIL-101'),enroll(A,'DEMO-HIS-101'),enroll(B,'DEMO-FIL-101'),enroll(D,'DEMO-HIS-101'),enroll(I,'DEMO-FIL-101')
    pf,ph,qf = assignment(P,'DEMO-FIL-101'),assignment(P,'DEMO-HIS-101'),assignment(Q,'DEMO-FIL-101')
    # A foreign period/subject enrollment and a foreign professor assignment.
    sql("insert into public.subjects(code,name) values ('OUTSIDE','Otra materia'); insert into public.academic_periods(name,starts_on,ends_on) values ('Otro periodo','2027-01-01','2027-06-01')")
    sql(f"insert into public.enrollments(student_id,subject_id,period_id) select '{D}',s.id,p.id from public.subjects s,public.academic_periods p where s.code='OUTSIDE' and p.name='Otro periodo'")
    outside = enroll(D,'OUTSIDE')
    # F has no profile, so C's accidental assignment tests role checks.
    sql(f"insert into public.teaching_assignments(professor_id,subject_id,period_id) select '{C}',s.id,p.id from public.subjects s,public.academic_periods p where s.code='OUTSIDE' and p.name='Otro periodo'")
    cf=assignment(C,'OUTSIDE','Otro periodo')

    test('published read preserves existing score',scalar(P,output('get_teaching_grade',pf,af)),expected=None)
    assert read(P,pf,af)=={'enrollment_id':af,'published_score':85.50,'draft_score':None,'revision':0,'has_unpublished_changes':False}
    checks += 1; print('PASS published read exact contract',flush=True)
    assert read(P,ph,ah)=={'enrollment_id':ah,'published_score':None,'draft_score':72.00,'revision':0,'has_unpublished_changes':False}
    checks += 1; print('PASS legacy draft is prefilled but not ready to publish',flush=True)
    assert read(P,ph,dh)['draft_score'] is None
    checks += 1; print('PASS absent grade exact empty state',flush=True)
    test('legacy draft must be saved before publish',scalar(P,output('publish_teaching_grade',ph,ah,0)),error='Guarda un borrador')
    for name,args in [('get_teaching_grade',()),('save_teaching_grade',(80,0)),('publish_teaching_grade',(0,))]:
        for actor,a,e,label in [(P,ZERO,af,'missing assignment'),(P,qf,af,'foreign professor assignment'),(P,pf,outside,'foreign course/period'),(P,pf,inactive,'inactive student'),(A,pf,af,'student'),(C,cf,outside,'control escolar'),(IP,pf,af,'inactive professor'),(N,pf,af,'missing profile')]:
            test(name+' denies '+label,scalar(actor,output(name,a,e,*args)),error='No tienes acceso a esta calificación')
    for score in ['null',"'NaN'::numeric","'Infinity'::numeric","'-Infinity'::numeric",'-1','100.01','85.555']:
        test('save rejects score '+score,scalar(P,output('save_teaching_grade',pf,af,score,0)),error='La nota debe estar')
    for revision in ['null','-1']:
        test('save rejects revision '+revision,scalar(P,output('save_teaching_grade',pf,af,80,revision)),error='La nota debe estar')
        test('publish rejects revision '+revision,scalar(P,output('publish_teaching_grade',pf,af,revision)),error='Revisión inválida')
    test('save RPC returns new revision and scores',committed(P, f"select revision||'|'||published_score||'|'||draft_score||'|'||has_unpublished_changes from {call('save_teaching_grade',pf,af,90.25,0)}"),'1|85.50|90.25|true')
    assert read(P,pf,af)=={'enrollment_id':af,'published_score':85.50,'draft_score':90.25,'revision':1,'has_unpublished_changes':True}
    checks += 1; print('PASS saved draft state visible to professor',flush=True)
    test('student still sees old published score after draft',scalar(A,f"select score from public.enrollment_grades where enrollment_id='{af}'"),'85.50')
    test('double-click save is conflict',scalar(P,output('save_teaching_grade',pf,af,99,0)),error='PT409')
    test('stale publish is conflict',scalar(P,output('publish_teaching_grade',pf,af,0)),error='PT409')
    test('co-teacher sees same versioned draft',scalar(Q,f"select revision from {call('get_teaching_grade',qf,af)}"),1)
    test('publish RPC returns new revision and scores',committed(P, f"select revision||'|'||published_score||'|'||draft_score||'|'||has_unpublished_changes from {call('publish_teaching_grade',pf,af,1)}"),'2|90.25|90.25|false')
    assert read(P,pf,af)=={'enrollment_id':af,'published_score':90.25,'draft_score':90.25,'revision':2,'has_unpublished_changes':False}
    checks += 1; print('PASS published return and read state',flush=True)
    test('student sees newly published score',scalar(A,f"select score from public.enrollment_grades where enrollment_id='{af}'"),'90.25')
    test('replayed publish is conflict',scalar(P,output('publish_teaching_grade',pf,af,1)),error='PT409')
    test('cannot republish without new draft',scalar(P,output('publish_teaching_grade',pf,af,2)),error='Guarda un borrador')
    test('zero saved',committed(P,output('save_teaching_grade',ph,ah,0,0)))
    test('zero published',committed(P,output('publish_teaching_grade',ph,ah,1)))
    test('student sees zero as valid grade',scalar(A,f"select score from public.enrollment_grades where enrollment_id='{ah}'"),'0.00')
    test('100 saved',committed(Q,output('save_teaching_grade',qf,bf,100,0)))
    test('100 published',committed(Q,output('publish_teaching_grade',qf,bf,1)))
    test('student B sees own100 only',scalar(B,f"select score from public.enrollment_grades where enrollment_id='{bf}'"),'100.00')
    test('student A cannot read B note',scalar(A,f"select count(*) from public.enrollment_grades where enrollment_id='{bf}'"),0)

    # Audit is atomic, private, and includes previous and new values.
    test('audit preserves previous published and draft values',f"select action||'|'||coalesce(old_draft_score::text,'NULL')||'|'||coalesce(old_published_score::text,'NULL')||'|'||score::text||'|'||revision::text from public.enrollment_grade_events where enrollment_id='{af}' order by revision",'save_draft|NULL|85.50|90.25|1\npublish|90.25|85.50|90.25|2')
    test('audit records actor and assignment snapshot',f"select count(*) from public.enrollment_grade_events where enrollment_id='{af}' and actor_id='{P}' and assignment_id='{pf}'",2)
    test('only successful operations create audit events',f"select count(*) from public.enrollment_grade_events",6)
    test('stage pending note before audit publication failure',committed(P,output('save_teaching_grade',ph,dh,55,0)))
    sql("create function public.fail_audit_test() returns trigger language plpgsql as $$begin raise exception 'TEST audit failure';end;$$; create trigger fail_audit before insert on public.enrollment_grade_events for each row execute function public.fail_audit_test();")
    test('audit failure aborts save',scalar(P,output('save_teaching_grade',pf,af,50,2)),error='TEST audit failure')
    test('failed audit leaves draft unchanged',f"select score||'|'||revision from public.enrollment_grade_drafts where enrollment_id='{af}'",'90.25|2')
    test('failed audit leaves published unchanged',f"select score from public.enrollment_grades where enrollment_id='{af}'",'90.25')
    test('audit failure aborts publish',committed(P,output('publish_teaching_grade',ph,dh,1)),error='TEST audit failure')
    test('failed publication leaves public grade absent',f"select count(*) from public.enrollment_grades where enrollment_id='{dh}'",0)
    test('failed publication keeps draft pending at same revision',f"select score||'|'||revision||'|'||needs_publication from public.enrollment_grade_drafts where enrollment_id='{dh}'",'55.00|1|true')
    sql('drop trigger fail_audit on public.enrollment_grade_events; drop function public.fail_audit_test();')

    for table in ['enrollment_grade_drafts','enrollment_grade_events']:
        for actor,label in [(P,'professor'),(A,'student'),(C,'control')]:
            for statement in [f'select * from public.{table}',f'insert into public.{table} default values',f'update public.{table} set enrollment_id=enrollment_id',f'delete from public.{table}',f'truncate public.{table}']:
                test(label+' direct '+statement.split()[0]+' denied '+table,scalar(actor,statement),error='permission denied')
        test('anon has no '+table,scalar(P,f'select * from public.{table}',role='anon'),error='permission denied')
    for name,sig,args in [('get_teaching_grade','uuid,uuid',()),('save_teaching_grade','uuid,uuid,numeric,integer',(80,2)),('publish_teaching_grade','uuid,uuid,integer',(2,))]:
        test(name+' rejects anon execution',scalar(P,output(name,pf,af,*args),role='anon'),error='permission denied')
        test(name+' PUBLICexecute revoked',f"select count(*) from pg_proc p,lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where p.oid='public.{name}({sig})'::regprocedure and a.grantee=0 and a.privilege_type='EXECUTE'",0)
        test(name+' trusted definer empty searchpath',f"select prosecdef and proconfig @> array['search_path=\"\"'] from pg_proc where oid='public.{name}({sig})'::regprocedure",'t')
    test('private helper not executable',scalar(P,f"select public._lock_teaching_grade('{pf}','{af}')"),error='permission denied')
    test('professor no direct grade update',scalar(P,'update public.enrollment_grades set score=100'),error='permission denied')

    # Transactions with co-teachers serialize on the enrollment; only one wins.
    race_query = committed(P,output('save_teaching_grade',pf,enroll(D,'DEMO-FIL-101'),88,0))
    race_enrollment = enroll(D,'DEMO-FIL-101')
    race_query = race_query.replace('begin;',"set application_name='capture-race-a'; begin;").replace('; commit;', '; select pg_sleep(1); commit;')
    proc=background(race_query)
    wait_sleep('capture-race-a')
    test('concurrent co-teacher stale edit rejected',committed(Q,output('save_teaching_grade',qf,race_enrollment,99,0)),error='PT409')
    proc.wait(timeout=10)
    assert proc.returncode==0,proc.stderr.read()
    test('concurrent edits produce single draft and audit',f"select d.score||'|'||d.revision||'|'||(select count(*) from public.enrollment_grade_events a where a.enrollment_id=d.enrollment_id) from public.enrollment_grade_drafts d where d.enrollment_id='{race_enrollment}'",'88.00|1|1')

    # While a write transaction holds auth row locks, revocation waits.
    locked_query=committed(P,output('save_teaching_grade',pf,af,91,2)).replace('begin;',"set application_name='capture-auth-locks'; begin;").replace('; commit;','; select pg_sleep(1); commit;')
    proc=background(locked_query)
    wait_sleep('capture-auth-locks')
    test('professor role revocation blocked until write completes',f"set lock_timeout='100ms'; update public.profiles set role='student' where id='{P}'",error='lock timeout')
    test('student deactivation blocked until write completes',f"set lock_timeout='100ms'; update public.profiles set active=false where id='{A}'",error='lock timeout')
    test('assignment deletion blocked until write completes',f"set lock_timeout='100ms'; delete from public.teaching_assignments where id='{pf}'",error='lock timeout')
    proc.wait(timeout=10)
    assert proc.returncode==0,proc.stderr.read()
    sql(f"update public.profiles set active=false where id='{P}'")
    for name,args in [('get_teaching_grade',()),('save_teaching_grade',(80,3)),('publish_teaching_grade',(3,))]:
        test(name+' denies newly inactive professor',scalar(P,output(name,pf,af,*args)),error='No tienes acceso')
    sql(f"update public.profiles set active=true where id='{P}'")
    sql(f"update public.profiles set active=false where id='{A}'")
    test('save denies newly inactive student',scalar(P,output('save_teaching_grade',pf,af,80,3)),error='No tienes acceso')
    sql(f"update public.profiles set active=true where id='{A}'")
    sql(f"delete from public.teaching_assignments where id='{qf}'")
    test('audit does not prevent assignment revocation',scalar(Q,output('get_teaching_grade',qf,af)),error='No tienes acceso')
    test('manual capture smoke readonly',smoke.replace('PROFESSOR_UID_AQUI',P))
    for student,label in [(A,'A'),(B,'B')]:
        for filename in ['profiles_rls.sql','academics_rls.sql','grades_rls.sql']:
            test('old '+filename+' '+label,(ROOT/'supabase/tests'/filename).read_text().replace('PEGA_AQUI_EL_UID',student))
    test('old professor smoke unchanged',(ROOT/'supabase/tests/professor_rls.sql').read_text().replace('PROFESSOR_UID_AQUI',P))
    sql('grant select on public.enrollment_grade_drafts to authenticated;')
    test('smoke detects draft grant',smoke.replace('PROFESSOR_UID_AQUI',P),error='acceso directo')
    sql('revoke select on public.enrollment_grade_drafts from authenticated;')
    sql('grant execute on function public.save_teaching_grade(uuid,uuid,numeric,integer) to public;')
    test('smoke detects public writer execution',smoke.replace('PROFESSOR_UID_AQUI',P),error='permisos de ejecución')
    sql('revoke execute on function public.save_teaching_grade(uuid,uuid,numeric,integer) from public;')
    print(f'PASS {checks} grade capture PostgreSQL assertions; disposable container only; no live changes',flush=True)
finally:
    run('docker','rm','-f',NAME,check=False)
