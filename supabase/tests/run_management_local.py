#!/usr/bin/env python3
"""Catálogos de Control Escolar en PostgreSQL desechable; nunca Supabase real.

Requiere Python 3, Docker y postgres:17-bookworm. Solo usa docker exec sobre su
propio contenedor sin red ni puertos; no admite DSN ni credenciales externas.
Auth es un fixture mínimo. Se comprueba SQL/RLS, no Supabase Auth ni PostgREST.
"""
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'seminario-management-test-' + uuid.uuid4().hex[:10]
checks = 0


def run(*args, input=None, check=True):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=check)


def sql(query, ok=True, database='postgres'):
    result = run('docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres', '-d', database,
                 '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose',
                 input=query, check=False)
    if ok and result.returncode:
        raise AssertionError(result.stderr)
    if not ok and not result.returncode:
        raise AssertionError('Expected failure: ' + query)
    return result


def test(name, query, expected=None, error=None, database='postgres'):
    global checks
    result = sql(query, ok=error is None, database=database)
    if expected is not None:
        assert result.stdout.strip() == str(expected), (name, result.stdout, result.stderr)
    if error:
        assert error in result.stderr, (name, result.stderr)
    checks += 1
    print('PASS', name, flush=True)


def actor(uid, statement, role='authenticated', commit=False):
    claim = uid or ''
    return (f"begin; set local role {role}; set local request.jwt.claim.sub = '{claim}'; "
            f"set local request.jwt.claims = '{{\"sub\":\"{claim}\",\"role\":\"{role}\"}}'; "
            f"{statement}; {'commit' if commit else 'rollback'};")


def uid(n):
    return f'10000000-0000-4000-8000-{n:012d}'


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def subject(code, name):
    return f'public.create_subject({code},{name})'


def period(name, start="'2027-01-01'", end="'2027-06-30'"):
    return f'public.create_academic_period({name},{start},{end})'


def background(query):
    proc = subprocess.Popen(['docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres',
                             '-d', 'postgres', '-X', '-q', '-t', '-A', '-v',
                             'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    proc.stdin.write(query)
    proc.stdin.close()
    return proc


def finish(proc):
    proc.wait(timeout=15)
    return proc.returncode, proc.stdout.read(), proc.stderr.read()


def wait_sleep(tag):
    for _ in range(100):
        if sql(f"select count(*) from pg_stat_activity where application_name='{tag}' and wait_event='PgSleep'").stdout.strip() == '1':
            return
        time.sleep(.02)
    raise AssertionError('Concurrent transaction did not acquire its locks')


A, B, P, C, C2, IC, I, N, F = [uid(n) for n in range(1, 10)]
ZERO = '00000000-0000-0000-0000-000000000000'
MIGRATIONS = [
    '20261021000000_create_profiles.sql',
    '20261021010000_create_academics.sql',
    '20261021020000_create_enrollment_grades.sql',
    '20261021030000_create_teaching_assignments.sql',
    '20261021040000_enable_grade_capture.sql',
    '20261021050000_control_catalogs.sql',
]
AUTH_FIXTURE = '''create role anon nologin; create role authenticated nologin; create role service_role nologin;
    create schema auth; create table auth.users (id uuid primary key,email text);
    create function auth.uid() returns uuid language sql stable as $$
        select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
    $$;
    grant usage on schema auth to anon, authenticated;
    grant execute on function auth.uid() to anon, authenticated;'''


def write(action,data,who=None,commit=True):
    import json
    return actor(who or C,"select public.portal_admin_write("+quote(action)+","+quote(json.dumps(data))+"::jsonb)->>'saved'",commit=commit)

def read(resource,who=None,suffix="->'items'",search=''):
    return actor(who or C,"select public.portal_admin_read("+quote(resource)+","+quote(search)+",0,30)"+suffix)

try:
    run('docker','run','--rm','-d','--name',NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
    for _ in range(100):
        logs=run('docker','logs',NAME,check=False)
        if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and run('docker','exec',NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
        time.sleep(.2)
    else:raise AssertionError('PostgreSQL did not start')
    sql(AUTH_FIXTURE)
    for name in MIGRATIONS:sql((ROOT/'supabase/migrations'/name).read_text())
    users=[(A,'Alumno Alfa','student',True),(B,'Alumno Beta','student',True),(P,'Profesor','professor',True),(C,'Control Uno','control_escolar',True),(C2,'Control Dos','control_escolar',True),(IC,'Inactivo','control_escolar',False)]
    for user,name,role,active in users:
        sql(f"insert into auth.users values('{user}','{user[:8]}{user[-2:]}@example.invalid');insert into public.profiles(id,full_name,role,active) values('{user}',{quote(name)},'{role}',{str(active).lower()})")
    S,T,E,TA,S2,T2=[uid(n) for n in range(20,26)]
    sql(f"insert into public.subjects(id,code,name) values('{S}','HIS','Historia'),('{S2}','FIL','Filosofía');insert into public.academic_periods(id,name,starts_on,ends_on) values('{T}','Semestre 2026','2026-08-01','2026-12-18'),('{T2}','Semestre 2027','2027-01-01','2027-06-30');insert into public.enrollments(id,student_id,subject_id,period_id) values('{E}','{A}','{S}','{T}');insert into public.teaching_assignments(id,professor_id,subject_id,period_id) values('{TA}','{P}','{S}','{T}');insert into public.enrollment_grades(enrollment_id,score,published) values('{E}',100,true)")
    sql((ROOT/'supabase/migrations/20261021060000_portal_management.sql').read_text())
    sql((ROOT/'supabase/migrations/20261021070000_portal_invitations.sql').read_text())
    test('historical class imported exactly once','select count(*) from public.course_offerings',1)
    test('historical grade preserved',actor(A,'select score from public.enrollment_grades'),'100.00')
    for table in ['course_offerings','management_events','portal_invitations']:
        test('RLS '+table,f"select relrowsecurity from pg_class where oid='public.{table}'::regclass",'t')
        for who in [A,P,C]:test('no direct read '+table+' '+who[-2:],actor(who,'select * from public.'+table),error='42501')
    for who in [A,P,IC]:
        for resource in ['people','classes','enrollments','assignments','events']:
            test('unauthorized read '+resource+' '+who[-2:],read(resource,who),error='42501')
        test('unauthorized write '+who[-2:],write('class_create',{'subject_id':S2,'period_id':T2},who),error='42501')
    test('anonymous read denied',actor(None,"select public.portal_admin_read('people')",role='anon'),error='42501')
    test('staff directory includes all users',read('people',suffix="->'items'->0->>'full_name'"),'Alumno Alfa')
    test('directory search is literal',read('people',search="%' or true --",suffix="->'items'"),'[]')
    test('student picker only active students',read('students',suffix="->'items'->0->>'role'"),'student')
    test('professor picker only professors',read('professors',suffix="->'items'->0->>'role'"),'professor')
    for args in ["'people','',-1,30","'people','',0,101","'people','',null,30","'people',repeat('x',161),0,30","'invalid','',0,30"]:
        test('invalid pagination/resource '+args,actor(C,'select public.portal_admin_read('+args+')'),error='22023')
    test('class creation',write('class_create',{'subject_id':S2,'period_id':T2}),'true')
    CL=sql(f"select id from public.course_offerings where subject_id='{S2}'").stdout.strip()
    OLD=sql(f"select id from public.course_offerings where subject_id='{S}'").stdout.strip()
    test('duplicate class rejected',write('class_create',{'subject_id':S2,'period_id':T2}),error='PT409')
    for action,person in [('enroll',P),('assign',A)]:test('wrong person role '+action,write(action,{'class_id':CL,'person_id':person}),error='22023')
    test('student enrollment',write('enroll',{'class_id':CL,'person_id':B}),'true')
    test('professor assignment',write('assign',{'class_id':CL,'person_id':P}),'true')
    test('duplicate enrollment',write('enroll',{'class_id':CL,'person_id':B}),error='PT409')
    test('duplicate assignment',write('assign',{'class_id':CL,'person_id':P}),error='PT409')
    test('assignment visible to professor',actor(P,'select count(*) from public.teaching_assignments'),2)
    test('control table permissions still private',actor(C,'select count(*) from public.enrollments'),0)
    for table in ['profiles','enrollments','teaching_assignments']:
        test('no direct writes '+table,actor(C,f'update public.{table} set active=false'),error='42501')
    test('enrollment deactivated',write('enrollment_state',{'id':E,'active':False}),'true')
    test('deactivated enrollment hidden',actor(A,'select count(*) from public.enrollments'),0)
    test('deactivated grade hidden',actor(A,'select count(*) from public.enrollment_grades'),0)
    test('deactivated roster hidden',actor(P,f"select count(*) from public.get_teaching_roster('{TA}')"),0)
    for fn in [f"get_teaching_grade('{TA}','{E}')",f"save_teaching_grade('{TA}','{E}',99,0)",f"publish_teaching_grade('{TA}','{E}',0)"]:
        test('deactivated enrollment denies '+fn,actor(P,'select * from public.'+fn),error='42501')
    test('reenrollment restores existing identity',write('enroll',{'class_id':OLD,'person_id':A}),'true')
    test('published grade retained after reenrollment',actor(A,'select score from public.enrollment_grades'),'100.00')
    test('teaching assignment disabled',write('assignment_state',{'id':TA,'active':False}),'true')
    test('disabled teacher assignment hidden',actor(P,f"select count(*) from public.teaching_assignments where id='{TA}'"),0)
    test('disabled assignment roster denied',actor(P,f"select * from public.get_teaching_roster('{TA}')"),error='42501')
    test('disabled assignment save denied',actor(P,f"select * from public.save_teaching_grade('{TA}','{E}',99,0)"),error='42501')
    test('reassign same teacher',write('assign',{'class_id':OLD,'person_id':P}),'true')
    test('class archived',write('class_state',{'id':OLD,'active':False}),'true')
    test('archived class hides student enrollment',actor(A,'select count(*) from public.enrollments'),0)
    test('archived class rejects new enrollment',write('enroll',{'class_id':OLD,'person_id':B}),error='22023')
    test('archived class denies read grade',actor(P,f"select * from public.get_teaching_grade('{TA}','{E}')"),error='42501')
    test('archived class denies save grade',actor(P,f"select * from public.save_teaching_grade('{TA}','{E}',99,0)"),error='42501')
    test('restore class',write('class_state',{'id':OLD,'active':True}),'true')
    test('professor still can save draft',actor(P,f"select draft_score from public.save_teaching_grade('{TA}','{E}',98,0)",commit=True),'98.00')
    test('draft not published to student',actor(A,'select score from public.enrollment_grades'),'100.00')
    test('professor still can publish',actor(P,f"select published_score from public.publish_teaching_grade('{TA}','{E}',1)",commit=True),'98.00')
    person={'id':A,'revision':0,'full_name':'Alumno actualizado','role':'student','active':False}
    test('person disabled',write('person_update',person),'true')
    test('disabled own profile invisible',actor(A,'select count(*) from public.profiles'),0)
    test('stale profile edit blocked',write('person_update',person),error='PT409')
    person.update(revision=1,active=True)
    test('person enabled',write('person_update',person),'true')
    person.update(revision=2,role='professor')
    test('role with academic history immutable',write('person_update',person),error='22023')
    for active,role in [(False,'control_escolar'),(True,'student')]:
        test('self removal prevented '+str(active),write('person_update',{'id':C,'revision':0,'full_name':'Control','role':role,'active':active}),error='22023')
    test('subject edited',write('subject_update',{'id':S,'code':' HIS-1 ','name':'Historia actualizada'}),'true')
    test('subject edit retains enrollment',actor(A,"select count(*) from public.subjects where code='HIS-1'"),1)
    test('period edited',write('period_update',{'id':T,'name':'Semestre actualizado','starts_on':'2026-08-01','ends_on':'2026-12-20'}),'true')
    for action,data in [('period_update',{'id':T,'name':'x','starts_on':'infinity','ends_on':'infinity'}),('class_state',{'id':OLD,'active':'false'}),('class_create',{}),('bogus',{})]:
        test('bad write '+action,write(action,data),error='22023')
    test('events contain edits',read('events',suffix="->'items'->0->>'action'"),'period_update')
    for who in ['authenticated','anon']:
        for fn in ['portal_prepare_invite(uuid,uuid,text,text,text)','portal_finish_invite(uuid,uuid,uuid)','portal_fail_invite(uuid,uuid,text)']:
            test('private invite RPC '+who+' '+fn,f"select has_function_privilege('{who}','public.{fn}','EXECUTE')",'f')
    ID=uid(50);NEW=uid(51)
    prepare=lambda who,req=ID,email='new@example.org',name='Nueva Persona',role='professor':"select public.portal_prepare_invite('"+who+"','"+req+"',"+quote(email)+","+quote(name)+","+quote(role)+")->>'state'"
    test('inactive inviter denied',prepare(IC),error='42501')
    test('student inviter denied',prepare(A),error='42501')
    test('invitation claim',prepare(C),'claimed')
    test('duplicate request cannot send twice',prepare(C),'busy')
    test('same request different role denied',prepare(C,role='control_escolar'),error='PT409')
    test('second request same email denied',prepare(C,req=uid(52)),error='PT409')
    test('cannot finish incorrect identity',f"select public.portal_finish_invite('{C}','{ID}','{A}')",error='22023')
    sql(f"insert into auth.users values('{NEW}','new@example.org')")
    test('finish invitation creates profile',f"select public.portal_finish_invite('{C}','{ID}','{NEW}')->>'sent'",'true')
    test('invited role came from control request',f"select role from public.profiles where id='{NEW}'",'professor')
    test('finished request idempotent',prepare(C),'sent')
    test('cannot finish twice',f"select public.portal_finish_invite('{C}','{ID}','{NEW}')",error='PT409')
    test('existing auth account cannot be invited anew',prepare(C,req=uid(53)),error='PT409')
    test('invalid email denied',prepare(C,req=uid(54),email='not-an-email'),error='22023')
    # Permission snapshots: role is checked again at finalization, not trusted from the HTTP request.
    ID2=uid(60);NEW2=uid(61)
    test('second inviter claim',prepare(C2,req=ID2,email='revoked@example.org'),'claimed')
    sql(f"insert into auth.users values('{NEW2}','revoked@example.org');update public.profiles set active=false where id='{C2}'")
    test('revocation blocks finalization',f"select public.portal_finish_invite('{C2}','{ID2}','{NEW2}')",error='42501')
    test('revoked inviter created no profile',f"select count(*) from public.profiles where id='{NEW2}'",0)
    test('Control can consult published notes',read('enrollments',search='actualizado',suffix="->'items'->0->>'published_score'"),'98.00')
    sql("update public.profiles set active=true where id='"+C2+"'")
    writer=background("set application_name='campus-grade-lock';"+actor(P,f"select * from public.save_teaching_grade('{TA}','{E}',97,2);select pg_sleep(1.5)",commit=True))
    wait_sleep('campus-grade-lock')
    test('class deactivation waits for authorized grade write',"set lock_timeout='150ms';"+write('class_state',{'id':OLD,'active':False}),error='55P03')
    test('student deactivation waits for authorized grade write',"set lock_timeout='150ms';"+write('person_update',{'id':A,'revision':2,'full_name':'Alumno actualizado','role':'student','active':False}),error='55P03')
    code,out,err=finish(writer)
    assert code==0,(out,err)
    test('failed concurrent deactivation rolled back',f"select active from public.course_offerings where id='{OLD}'",'t')
    test('authorized draft committed once',f"select revision from public.enrollment_grade_drafts where enrollment_id='{E}'",3)
    print(f'PASS {checks} management/invitation PostgreSQL assertions; no live Supabase writes',flush=True)
finally:
    run('docker','rm','-f',NAME,check=False)
