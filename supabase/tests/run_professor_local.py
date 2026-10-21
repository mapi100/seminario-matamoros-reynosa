#!/usr/bin/env python3
"""Profesor y listado académico en PostgreSQL desechable, nunca Supabase real.

Requiere Python 3, Docker y postgres:17-bookworm. Crea exclusivamente su propio
contenedor sin red ni puertos. Todas las consultas usan docker exec; no admite
DSN, endpoint ni credenciales. Auth es un fixture mínimo, no Supabase Auth real.
"""
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'seminario-professor-test-' + uuid.uuid4().hex[:10]
checks = 0


def run(*args, input=None, check=True):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=check)


def sql(query, ok=True):
    result = run('docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres', '-d',
                 'postgres', '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1',
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
                 '20261021030000_create_teaching_assignments.sql']:
        sql((ROOT / 'supabase/migrations' / name).read_text())
    sql('insert into auth.users(id) values ' + ','.join(f"('{u}')" for u in [A, B, D, I, P, Q, IP, C, N, F]) + ';')
    rows = [(A, 'Alumno Alfa', 'student', True), (B, 'Alumno Beta', 'student', True),
            (D, 'Alumno Delta', 'student', True), (I, 'Alumno inactivo', 'student', False),
            (P, 'Profesor P', 'professor', True), (Q, 'Profesor Q', 'professor', True),
            (IP, 'Profesor inactivo', 'professor', False), (C, 'Control Escolar', 'control_escolar', True)]
    sql('insert into public.profiles(id,full_name,role,active) values ' + ','.join(
        f"('{u}','{name}','{role}',{str(active).lower()})" for u, name, role, active in rows) + ';')
    sql("alter table public.profiles add column private_fixture text not null default 'no exponer al profesor';")
    academic_seed = (ROOT / 'supabase/seeds/demo_enrollments.sql').read_text()
    grade_seed = (ROOT / 'supabase/seeds/demo_grades.sql').read_text()
    profile_seed = (ROOT / 'supabase/seeds/demo_professor_profile.sql').read_text()
    teaching_seed = (ROOT / 'supabase/seeds/demo_teaching.sql').read_text()
    smoke = (ROOT / 'supabase/tests/professor_rls.sql').read_text()

    def profile_demo(u):
        return profile_seed.replace('PROFESSOR_UID_AQUI', u)

    def teaching_demo(student=A, professor=P):
        return teaching_seed.replace('STUDENT_UID_AQUI', student).replace('PROFESSOR_UID_AQUI', professor)

    test('new professor profile first run', profile_demo(F), 'Perfil de profesor de prueba listo')
    test('new professor profile rerun', profile_demo(F), 'Perfil de profesor de prueba listo')
    sql(f"update public.profiles set full_name='Nombre conservado' where id='{F}';")
    test('profile seed does not overwrite name', profile_demo(F), 'Perfil de profesor de prueba listo')
    test('existing name preserved', f"select full_name from public.profiles where id='{F}'", 'Nombre conservado')
    test('profile seed rejects missing Auth account', profile_demo(ZERO), error='Primero crea la cuenta')
    test('profile seed rejects student conversion', profile_demo(A), error='otro rol o está inactiva')
    test('profile seed rejects inactive professor', profile_demo(IP), error='otro rol o está inactiva')
    test('student role remains student', f"select role from public.profiles where id='{A}'", 'student')
    test('inactive professor remains inactive', f"select active from public.profiles where id='{IP}'", 'f')
    test('assignments require existing demo enrollments', teaching_demo(), error='Faltan las dos inscripciones DEMO')
    sql(academic_seed.replace('PEGA_AQUI_EL_UID', A))
    sql(academic_seed.replace('PEGA_AQUI_EL_UID', B))
    sql(grade_seed.replace('PEGA_AQUI_EL_UID', A))
    sql(grade_seed.replace('PEGA_AQUI_EL_UID', B))
    test('teaching demo first run', teaching_demo(), 'Dos materias DEMO asignadas al profesor de prueba')
    test('teaching demo rerun', teaching_demo(), 'Dos materias DEMO asignadas al profesor de prueba')
    test('teaching demo does not duplicate', f"select count(*) from public.teaching_assignments where professor_id='{P}'", 2)
    for label, student, professor, error in [
        ('same account', A, A, 'cuentas distintas'),
        ('inactive student', I, P, 'alumno de prueba activo'),
        ('no student profile', N, P, 'alumno de prueba activo'),
        ('student as professor', A, B, 'profesor activo con perfil'),
        ('inactive professor', A, IP, 'profesor activo con perfil'),
        ('control as professor', A, C, 'profesor activo con perfil'),
        ('no professor profile', A, N, 'profesor activo con perfil'),
        ('student without demos', D, P, 'Faltan las dos inscripciones DEMO'),
    ]:
        test('teaching seed rejects ' + label, teaching_demo(student, professor), error=error)
    sql("insert into public.academic_periods(name,starts_on,ends_on) values ('Otro periodo','2027-01-01','2027-06-01');")
    sql("insert into public.subjects(code,name) values ('FIX-EXCLUSIVE','Materia exclusiva');")
    # Same subject but another period belongs to Q, never to P.
    sql(f"insert into public.enrollments(student_id,subject_id,period_id) "
        f"select '{D}',s.id,p.id from public.subjects s cross join public.academic_periods p "
        "where s.code='DEMO-FIL-101' and p.name='Otro periodo';")
    sql(f"insert into public.teaching_assignments(professor_id,subject_id,period_id) "
        f"select '{Q}',s.id,p.id from public.subjects s cross join public.academic_periods p "
        "where s.code='DEMO-FIL-101' and p.name='Otro periodo';")
    # Co-teaching is allowed but assignment IDs still belong to each professor.
    sql(f"insert into public.teaching_assignments(professor_id,subject_id,period_id) "
        f"select '{Q}',s.id,p.id from public.subjects s cross join public.academic_periods p "
        "where s.code='DEMO-HIS-101' and p.name='DEMO 2026 — semestre de prueba';")
    # Administrator mistakes must not make other profile roles eligible.
    for wrong in [IP, A, C]:
        sql(f"insert into public.teaching_assignments(professor_id,subject_id,period_id) "
            f"select '{wrong}',s.id,p.id from public.subjects s cross join public.academic_periods p "
            "where s.code='DEMO-FIL-101' and p.name='DEMO 2026 — semestre de prueba';")
    for wrong_student in [I, P, C]:
        sql(f"insert into public.enrollments(student_id,subject_id,period_id) "
            f"select '{wrong_student}',s.id,p.id from public.subjects s cross join public.academic_periods p "
            "where s.code='DEMO-FIL-101' and p.name='DEMO 2026 — semestre de prueba';")
    pf, ph = assignment(P, 'DEMO-FIL-101'), assignment(P, 'DEMO-HIS-101')
    qf, qh = assignment(Q, 'DEMO-FIL-101', 'Otro periodo'), assignment(Q, 'DEMO-HIS-101')
    ipf = assignment(IP, 'DEMO-FIL-101')
    af, cf = assignment(A, 'DEMO-FIL-101'), assignment(C, 'DEMO-FIL-101')
    function = 'public.get_teaching_roster(uuid,integer,integer)'
    test('function has only two output columns', f"select pg_get_function_result('{function}'::regprocedure)", 'TABLE(enrollment_id uuid, student_name text)')
    test('function is stable definer with empty search path', f"select prosecdef and provolatile='s' and proconfig @> array['search_path=\"\"'] from pg_proc where oid='{function}'::regprocedure", 't')
    test('PUBLIC does not have function EXECUTE', f"select count(*) from pg_proc p,lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where p.oid='{function}'::regprocedure and a.grantee=0 and a.privilege_type='EXECUTE'", 0)
    test('active professor sees own assignments', scalar(P, 'select count(*) from public.teaching_assignments'), 2)
    test('other professor sees only own assignments', scalar(Q, 'select count(*) from public.teaching_assignments'), 2)
    test('P cannot query Q assignment table row', scalar(P, f"select count(*) from public.teaching_assignments where id='{qf}'"), 0)
    test('P sees assigned subjects only', scalar(P, 'select count(*) from public.subjects'), 2)
    test('P sees assigned period only', scalar(P, 'select count(*) from public.academic_periods'), 1)
    test('Q sees two assigned periods', scalar(Q, 'select count(*) from public.academic_periods'), 2)
    test('P never sees exclusive catalog', scalar(P, "select count(*) from public.subjects where code='FIX-EXCLUSIVE'"), 0)
    test('P assignment/catalog join works without recursion', scalar(P, 'select count(*) from public.teaching_assignments t join public.subjects s on s.id=t.subject_id join public.academic_periods p on p.id=t.period_id'), 2)
    test('P sees active enrolled students only', scalar(P, f"select string_agg(student_name,'|') from {roster(pf)}"), 'Alumno Alfa|Alumno Beta')
    test('P other assigned subject sees same enrolled students', scalar(P, f"select count(*) from {roster(ph)}"), 2)
    test('Q same subject different period sees Delta only', scalar(Q, f"select string_agg(student_name,'|') from {roster(qf)}"), 'Alumno Delta')
    test('Q co-taught course sees authorized roster', scalar(Q, f"select count(*) from {roster(qh)}"), 2)
    test('offset page one stable sorted order', scalar(P, f"select student_name from {roster(pf, '0', '1')}"), 'Alumno Alfa')
    test('offset page two stable sorted order', scalar(P, f"select student_name from {roster(pf, '1', '1')}"), 'Alumno Beta')
    test('offset beyond rows gives empty page', scalar(P, f"select count(*) from {roster(pf, '2', '1')}"), 0)
    test('maximum allowed pagination accepted', scalar(P, f"select count(*) from {roster(pf, '100000', '100')}"), 0)
    test('default pagination parameters work', scalar(P, f"select count(*) from public.get_teaching_roster('{pf}')"), 2)
    test('RPC returns no student UUID or private field', scalar(P, f"select array_to_string(array(select jsonb_object_keys(to_jsonb(r)) order by 1),',') from {roster(pf,'0','1')} r"), 'enrollment_id,student_name')
    for label, actor, assignment_id in [('P foreign period', P, qf), ('P co-teacher assignment ID', P, qh),
                                       ('Q foreign assignment ID', Q, pf), ('student actor', A, af),
                                       ('control actor', C, cf), ('inactive professor', IP, ipf),
                                       ('unassigned professor', F, pf), ('no profile', N, pf),
                                       ('missing JWT identity', None, pf), ('missing assignment', P, ZERO)]:
        test('RPC denies ' + label, scalar(actor, f"select * from {roster(assignment_id)}"), error='No tienes acceso a esta lista')
    test('RPC denies NULL assignment', scalar(P, 'select * from public.get_teaching_roster(null,0,20)'), error='No tienes acceso a esta lista')
    for offset, limit in [('null', '20'), ('-1', '20'), ('100001', '20'), ('0', 'null'), ('0', '0'), ('0', '-1'), ('0', '101')]:
        test('RPC rejects invalid pagination ' + offset + '/' + limit, scalar(P, f'select * from {roster(pf, offset, limit)}'), error='Paginación inválida')
    for actor, label in [(P, 'professor'), (Q, 'other professor'), (C, 'control'), (N, 'no profile')]:
        test(label + ' cannot read students directly', scalar(actor, f"select count(*) from public.profiles where id in ('{A}','{B}','{D}')"), 0)
        test(label + ' cannot read enrollments directly', scalar(actor, 'select count(*) from public.enrollments'), 0)
        test(label + ' cannot read grades directly', scalar(actor, 'select count(*) from public.enrollment_grades'), 0)
    for actor, label in [(A, 'student'), (I, 'inactive student'), (IP, 'inactive professor'), (C, 'control'), (N, 'no profile')]:
        test(label + ' reads no assignments', scalar(actor, 'select count(*) from public.teaching_assignments'), 0)
    test('anon cannot read assignments', scalar(P, 'select * from public.teaching_assignments', role='anon'), error='permission denied')
    test('anon cannot execute roster function', scalar(P, f'select * from {roster(pf)}', role='anon'), error='permission denied')
    for actor, label in [(A, 'student'), (P, 'professor'), (C, 'control')]:
        for mutation in ['insert into public.teaching_assignments default values',
                         'update public.teaching_assignments set professor_id=professor_id',
                         'delete from public.teaching_assignments', 'truncate public.teaching_assignments']:
            test(label + ' cannot ' + mutation.split()[0] + ' assignments', scalar(actor, mutation), error='permission denied')
    test('student enrollments unchanged', scalar(A, 'select count(*) from public.enrollments'), 2)
    test('student catalogs unchanged', scalar(A, 'select count(*) from public.subjects'), 2)
    test('student published grade unchanged', scalar(A, 'select count(*) from public.enrollment_grades'), 1)
    test('student profile privacy unchanged', scalar(A, 'select count(*) from public.profiles'), 1)
    for student, label in [(A, 'A'), (B, 'B')]:
        for filename in ['profiles_rls.sql', 'academics_rls.sql', 'grades_rls.sql']:
            previous_smoke = (ROOT / 'supabase/tests' / filename).read_text()
            test('existing ' + filename + ' after new policies for ' + label,
                 previous_smoke.replace('PEGA_AQUI_EL_UID', student))
    test('professor manual smoke', smoke.replace('PROFESSOR_UID_AQUI', P))
    test('other professor manual smoke', smoke.replace('PROFESSOR_UID_AQUI', Q))
    sql(f"update public.profiles set active=false where id='{A}';")
    test('student deactivation immediately leaves roster', scalar(P, f"select string_agg(student_name,'|') from {roster(pf)}"), 'Alumno Beta')
    sql(f"update public.profiles set active=true,role='control_escolar' where id='{A}';")
    test('student role change immediately leaves roster', scalar(P, f"select count(*) from {roster(pf)}"), 1)
    sql(f"update public.profiles set role='student' where id='{A}'; update public.profiles set active=false where id='{P}';")
    test('professor deactivation hides assignments', scalar(P, 'select count(*) from public.teaching_assignments'), 0)
    test('professor deactivation hides catalogs', scalar(P, 'select count(*) from public.subjects'), 0)
    test('professor deactivation denies RPC', scalar(P, f'select * from {roster(pf)}'), error='No tienes acceso a esta lista')
    sql(f"update public.profiles set active=true,role='control_escolar' where id='{P}';")
    test('professor role change hides assignments', scalar(P, 'select count(*) from public.teaching_assignments'), 0)
    test('professor role change denies RPC', scalar(P, f'select * from {roster(pf)}'), error='No tienes acceso a esta lista')
    sql(f"update public.profiles set role='professor' where id='{P}';")
    test('assigned professor deletion protected', f"delete from auth.users where id='{P}'", error='foreign key')
    test('duplicate assignment rejected', f"insert into public.teaching_assignments(professor_id,subject_id,period_id) select professor_id,subject_id,period_id from public.teaching_assignments where id='{pf}'", error='duplicate key')
    test('missing professor FK rejected', f"insert into public.teaching_assignments(professor_id,subject_id,period_id) select '{ZERO}',subject_id,period_id from public.teaching_assignments where id='{pf}'", error='foreign key')
    sql(f"delete from public.teaching_assignments where id='{qf}';")
    test('removed assignment immediately denies RPC', scalar(Q, f'select * from {roster(qf)}'), error='No tienes acceso a esta lista')
    # RPC authorization remains explicit even if a future SELECT policy is broadened.
    sql('create policy "TEST broad assignments" on public.teaching_assignments for select to authenticated using (true);')
    test('broader assignment SELECT cannot authorize foreign RPC', scalar(Q, f'select * from {roster(pf)}'), error='No tienes acceso a esta lista')
    test('smoke detects broad assignment visibility', smoke.replace('PROFESSOR_UID_AQUI', P), error='asignaciones ajenas')
    sql('drop policy "TEST broad assignments" on public.teaching_assignments;')
    sql('grant execute on function public.get_teaching_roster(uuid,integer,integer) to public;')
    test('smoke detects default/public execution', smoke.replace('PROFESSOR_UID_AQUI', P), error='permisos de ejecución')
    sql('revoke execute on function public.get_teaching_roster(uuid,integer,integer) from public; alter table public.teaching_assignments disable row level security;')
    test('smoke detects disabled assignment RLS', smoke.replace('PROFESSOR_UID_AQUI', P), error='RLS no está activado')
    sql('alter table public.teaching_assignments enable row level security; grant update on public.teaching_assignments to authenticated;')
    test('smoke detects assignment write grant', smoke.replace('PROFESSOR_UID_AQUI', P), error='permisos de asignaciones')
    sql('revoke update on public.teaching_assignments from authenticated; create policy "TEST broad profiles" on public.profiles for select to authenticated using (true);')
    test('smoke detects student profile exposure', smoke.replace('PROFESSOR_UID_AQUI', P), error='solo su perfil visible')
    sql('drop policy "TEST broad profiles" on public.profiles;')
    print(f'PASS {checks} professor PostgreSQL assertions; disposable container only; no live Supabase changes', flush=True)
finally:
    run('docker', 'rm', '-f', NAME, check=False)
