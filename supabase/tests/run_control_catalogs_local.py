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
NAME = 'seminario-catalogs-test-' + uuid.uuid4().hex[:10]
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
AUTH_FIXTURE = '''create role anon nologin; create role authenticated nologin;
    create schema auth; create table auth.users (id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$
        select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
    $$;
    grant usage on schema auth to anon, authenticated;
    grant execute on function auth.uid() to anon, authenticated;'''

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
    sql(AUTH_FIXTURE)
    for name in MIGRATIONS:
        sql((ROOT / 'supabase/migrations' / name).read_text())
    sql('insert into auth.users(id) values ' + ','.join(f"('{u}')" for u in [A, B, P, C, C2, IC, I, N, F]) + ';')
    rows = [(A, 'Alumno Alfa', 'student', True), (B, 'Alumno Beta', 'student', True),
            (P, 'Profesor de prueba', 'professor', True), (C, 'Control Uno', 'control_escolar', True),
            (C2, 'Control Dos', 'control_escolar', True), (IC, 'Control inactivo', 'control_escolar', False),
            (I, 'Alumno inactivo', 'student', False)]
    sql('insert into public.profiles(id,full_name,role,active) values ' + ','.join(
        f"('{u}','{name}','{role}',{str(active).lower()})" for u, name, role, active in rows) + ';')
    test('empty catalogs visible to active Control', actor(C, 'select count(*) from public.subjects'), 0)
    seed = (ROOT/'supabase/seeds/demo_control_profile.sql').read_text()
    smoke = (ROOT/'supabase/tests/control_catalogs_rls.sql').read_text()
    profile_seed = lambda account: seed.replace('CONTROL_UID_AQUI', account)
    test('Control profile seed creates distinct account', profile_seed(F), 'Perfil de Control Escolar de prueba listo')
    test('Control profile seed is repeatable', profile_seed(F), 'Perfil de Control Escolar de prueba listo')
    sql(f"update public.profiles set full_name='Nombre conservado' where id='{F}'")
    test('Control profile seed preserves existing name', profile_seed(F), 'Perfil de Control Escolar de prueba listo')
    test('existing Control name unchanged', f"select full_name from public.profiles where id='{F}'", 'Nombre conservado')
    for label, account in [('student', A), ('professor', P), ('inactive', IC)]:
        test('profile seed rejects ' + label, profile_seed(account), error='otro rol o está inactiva')
    test('profile seed rejects missing Auth account', profile_seed(ZERO), error='Primero crea la cuenta')
    test('student role unchanged by rejected seed', f"select role from public.profiles where id='{A}'", 'student')
    test('inactive Control remains inactive', f"select active from public.profiles where id='{IC}'", 'f')

    academic_seed = (ROOT/'supabase/seeds/demo_enrollments.sql').read_text()
    grade_seed = (ROOT/'supabase/seeds/demo_grades.sql').read_text()
    for student in [A, B]:
        sql(academic_seed.replace('PEGA_AQUI_EL_UID', student))
        sql(grade_seed.replace('PEGA_AQUI_EL_UID', student))
    sql((ROOT/'supabase/seeds/demo_teaching.sql').read_text().replace('STUDENT_UID_AQUI', A).replace('PROFESSOR_UID_AQUI', P))
    sql("insert into public.subjects(code,name) values ('OUTSIDE','Catálogo sin inscripción'); insert into public.academic_periods(name,starts_on,ends_on) values ('Periodo sin alumnos','2027-01-01','2027-06-30')")
    test('Control sees all subjects including unassigned', actor(C, 'select count(*) from public.subjects'), 3)
    test('Control sees all periods including unassigned', actor(C, 'select count(*) from public.academic_periods'), 2)
    for label, account in [('Control one', C), ('Control two', C2)]:
        test(label + ' own profile only', actor(account, 'select count(*) from public.profiles'), 1)
        for table in ['enrollments', 'enrollment_grades', 'teaching_assignments']:
            test(label + ' no broadened ' + table, actor(account, f'select count(*) from public.{table}'), 0)
    for label, account in [('inactive Control', IC), ('inactive student', I), ('no profile', N), ('missing identity', None)]:
        for table in ['subjects', 'academic_periods']:
            test(label + ' cannot read catalog ' + table, actor(account, f'select count(*) from public.{table}'), 0)

    calls = [subject("' fil-new '", "'  Nueva Filosofía  '"), period("'  Semestre 2027  '")]
    test('subject RPC canonicalizes and returns row', actor(C, 'select code || \'|\' || name from ' + calls[0], commit=True), 'FIL-NEW|Nueva Filosofía')
    test('period RPC trims and returns dates', actor(C, 'select name || \'|\' || starts_on::text || \'|\' || ends_on::text from ' + calls[1], commit=True), 'Semestre 2027|2027-01-01|2027-06-30')
    test('both creations recorded once', 'select count(*) from public.catalog_events', 2)
    test('audit actor and subject details correct', f"select count(*) from public.catalog_events where actor_id='{C}' and action='subject_created' and details= jsonb_build_object('code','FIL-NEW','name','Nueva Filosofía')", 1)
    test('audit period details correct', "select count(*) from public.catalog_events where action='period_created' and details->>'name'='Semestre 2027' and details->>'starts_on'='2027-01-01' and details->>'ends_on'='2027-06-30'", 1)
    for code in ["'FIL-NEW'", "'fil-new'", "'  FiL-NeW  '"]:
        test('normalized subject duplicate denied ' + code, actor(C2, 'select * from ' + subject(code, "'No sobrescribir'"), commit=True), error='PT409')
    test('period duplicate case/spaces denied', actor(C2, 'select * from ' + period("' semestre 2027 '", "'2028-01-01'", "'2028-06-30'"), commit=True), error='PT409')
    test('duplicate cannot overwrite existing name', "select name from public.subjects where code='FIL-NEW'", 'Nueva Filosofía')
    test('duplicates produce no audit entries', 'select count(*) from public.catalog_events', 2)

    invalid_subjects = [("null", "'Nombre'"), ("''", "'Nombre'"), ("'   '", "'Nombre'"),
                        ("repeat('X',41)", "'Nombre'"), ("'VALID'", 'null'), ("'VALID'", "'  '"),
                        ("'VALID'", "repeat('N',161)"), ("E'BAD\\tCODE'", "'Nombre'"), ("'VALID'", "E'Nombre\\nOtro'")]
    for number, (code, name) in enumerate(invalid_subjects):
        test('invalid subject input ' + str(number), actor(C, 'select * from ' + subject(code, name), commit=True), error='22023')
    invalid_periods = [("null", "'2027-01-01'", "'2027-02-01'"), ("'  '", "'2027-01-01'", "'2027-02-01'"),
                       ("repeat('P',121)", "'2027-01-01'", "'2027-02-01'"), ("E'Bad\\nName'", "'2027-01-01'", "'2027-02-01'"),
                       ("'P'", 'null', "'2027-02-01'"), ("'P'", "'2027-01-01'", 'null'),
                       ("'P'", "'2027-03-01'", "'2027-02-01'"), ("'P'", "'-infinity'", "'2027-02-01'"),
                       ("'P'", "'2027-01-01'", "'infinity'"), ("'P'", "'0001-01-01 BC'", "'0001-01-01'"),
                       ("'P'", "'9999-01-01'", "'10000-01-01'")]
    for number, (name, start, end) in enumerate(invalid_periods):
        test('invalid period input ' + str(number), actor(C, 'select * from ' + period(name, start, end), commit=True), error='22023')
    for label, whitespace in [('NBSP', "U&'\\00A0'"), ('EM SPACE', "U&'\\2003'"),
                              ('BOM', "U&'\\FEFF'"), ('mixed Unicode spaces', "U&' \\00A0\\2003\\FEFF '")]:
        test('subject code rejects blank ' + label, actor(C, 'select * from ' + subject(whitespace, "'Nombre'"), commit=True), error='22023')
        test('subject name rejects blank ' + label, actor(C, 'select * from ' + subject("'UNICODE-BLANK'", whitespace), commit=True), error='22023')
        test('period name rejects blank ' + label, actor(C, 'select * from ' + period(whitespace), commit=True), error='22023')
    test('boundary same-day period allowed', actor(C, "select ends_on-starts_on from " + period("'Boundary day'", "'0001-01-01'", "'0001-01-01'")), 0)
    test('maximum supported year allowed', actor(C, "select ends_on::text from " + period("'Boundary max'", "'9999-12-31'", "'9999-12-31'")), '9999-12-31')
    test('maximum code and subject name allowed', actor(C, "select char_length(code)||'|'||char_length(name) from " + subject("repeat('X',40)", "repeat('N',160)")), '40|160')
    test('Unicode values accepted as plain text', actor(C, 'select code from ' + subject("' teología 1 '", "'Ética y formación'")), 'TEOLOGÍA 1')
    for label, account in [('student', A), ('professor', P), ('inactive Control', IC), ('no profile', N), ('missing identity', None)]:
        for index, call in enumerate([subject("'UNAUTH'", "'Nombre'"), period("'UNAUTH'")]):
            test(label + ' RPC denied ' + str(index), actor(account, 'select * from ' + call, commit=True), error='42501')
        test(label + ' invalid input still denied by authorization first', actor(account, 'select * from ' + subject('null', 'null'), commit=True), error='42501')

    for table in ['subjects', 'academic_periods', 'catalog_events']:
        for mutation in [f'insert into public.{table} default values', f'update public.{table} set id=id', f'delete from public.{table}', f'truncate public.{table}']:
            test('Control cannot direct ' + mutation.split()[0] + ' ' + table, actor(C, mutation), error='permission denied')
    for account in [A, P, C]:
        test('audit is private for ' + account, actor(account, 'select * from public.catalog_events'), error='permission denied')
    test('anon cannot read catalogs', actor(None, 'select * from public.subjects', role='anon'), error='permission denied')
    for call in [subject("'ANON'", "'Nombre'"), period("'ANON'")]:
        test('anon cannot execute create RPC', actor(None, 'select * from ' + call, role='anon'), error='permission denied')
    test('private helper not callable by Control', actor(C, 'select public._require_control_catalog_access()'), error='permission denied')
    test('private Unicode content helper not callable by Control', actor(C, "select public._catalog_text_has_content('Nombre')"), error='permission denied')
    test('Unicode helper has immutable safe configuration', "select not prosecdef and provolatile='i' and proparallel='s' and proconfig @> array['search_path=\"\"'] from pg_proc where oid='public._catalog_text_has_content(text)'::regprocedure", 't')
    for signature in ['public.create_subject(text,text)', 'public.create_academic_period(text,date,date)', 'public._require_control_catalog_access()']:
        test('no PUBLIC execute ' + signature, f"select count(*) from pg_proc p,lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where p.oid='{signature}'::regprocedure and a.grantee=0 and a.privilege_type='EXECUTE'", 0)
        test('trusted function configuration ' + signature, f"select prosecdef and provolatile='v' and proconfig @> array['search_path=\"\"'] from pg_proc where oid='{signature}'::regprocedure", 't')
    test('Control manual smoke', smoke.replace('CONTROL_UID_AQUI', C))
    for label, student in [('A', A), ('B', B)]:
        for filename in ['profiles_rls.sql', 'academics_rls.sql', 'grades_rls.sql']:
            test('previous smoke ' + filename + ' for ' + label,
                 (ROOT/'supabase/tests'/filename).read_text().replace('PEGA_AQUI_EL_UID', student))
    for filename in ['professor_rls.sql', 'grade_capture_rls.sql']:
        test('previous professor smoke ' + filename,
             (ROOT/'supabase/tests'/filename).read_text().replace('PROFESSOR_UID_AQUI', P))
    test('student catalog scope unchanged', actor(A, 'select count(*) from public.subjects'), 2)
    test('professor catalog scope unchanged', actor(P, 'select count(*) from public.subjects'), 2)
    test('student published notes unchanged', actor(A, 'select count(*) from public.enrollment_grades'), 1)

    # Audit failure must roll back catalog creation in the same transaction.
    sql("create function public._test_audit_failure() returns trigger language plpgsql as $$ begin raise exception 'TEST audit failure'; end $$; create trigger test_audit_failure before insert on public.catalog_events for each row execute function public._test_audit_failure()")
    for code, call in [('AUDIT-SUBJECT', subject("'AUDIT-SUBJECT'", "'Nombre'")), ('AUDIT-PERIOD', period("'AUDIT-PERIOD'"))]:
        test('audit failure aborts creation ' + code, actor(C, 'select * from ' + call, commit=True), error='TEST audit failure')
    test('failed subject absent', "select count(*) from public.subjects where code='AUDIT-SUBJECT'", 0)
    test('failed period absent', "select count(*) from public.academic_periods where name='AUDIT-PERIOD'", 0)
    sql('drop trigger test_audit_failure on public.catalog_events; drop function public._test_audit_failure()')

    # Two concurrent creators: normalized unique index yields one commit only.
    first = background("set application_name='catalog-duplicate';" + actor(C, "select * from " + subject("'race-code'", "'Primero'") + '; select pg_sleep(1.0)', commit=True))
    wait_sleep('catalog-duplicate')
    second = background(actor(C2, 'select * from ' + subject("' RACE-CODE '", "'Segundo'"), commit=True))
    first_result, second_result = finish(first), finish(second)
    assert first_result[0] == 0, first_result
    assert second_result[0] != 0 and 'PT409' in second_result[2], second_result
    checks += 1
    print('PASS concurrent duplicate creation has one winner', flush=True)
    test('only one concurrent subject row', "select count(*) from public.subjects where code='RACE-CODE'", 1)
    test('only one concurrent subject audit', "select count(*) from public.catalog_events where details->>'code'='RACE-CODE'", 1)

    # Actor FOR SHARE prevents revoking a role inside an authorized transaction.
    writer = background("set application_name='catalog-role-lock';" + actor(C, "select * from " + subject("'LOCKED'", "'Con bloqueo'") + '; select pg_sleep(1.0)', commit=True))
    wait_sleep('catalog-role-lock')
    test('role update waits for catalog transaction', f"set lock_timeout='150ms'; update public.profiles set role='student' where id='{C}'", error='55P03')
    result = finish(writer)
    assert result[0] == 0, result
    sql(f"update public.profiles set active=false where id='{C}'")
    test('deactivation immediately hides all catalogs', actor(C, 'select count(*) from public.subjects'), 0)
    test('deactivation immediately denies create', actor(C, 'select * from ' + subject("'AFTER-REVOKE'", "'Nombre'"), commit=True), error='42501')
    sql(f"update public.profiles set active=true,role='professor' where id='{C}'")
    test('role change denies create', actor(C, 'select * from ' + period("'AFTER-ROLE'"), commit=True), error='42501')
    sql(f"update public.profiles set role='control_escolar' where id='{C}'")

    # Read-only smoke must identify actual regressions rather than always pass.
    sql('grant insert on public.subjects to authenticated')
    test('smoke detects direct write grant', smoke.replace('CONTROL_UID_AQUI', C), error='permisos de catálogo')
    sql('revoke insert on public.subjects from authenticated; alter table public.academic_periods disable row level security')
    test('smoke detects disabled RLS', smoke.replace('CONTROL_UID_AQUI', C), error='RLS no está activado')
    sql('alter table public.academic_periods enable row level security; grant execute on function public.create_subject(text,text) to public')
    test('smoke detects default PUBLIC execution', smoke.replace('CONTROL_UID_AQUI', C), error='permisos de ejecución')
    sql('revoke execute on function public.create_subject(text,text) from public; grant select on public.catalog_events to authenticated')
    test('smoke detects private table grant', smoke.replace('CONTROL_UID_AQUI', C), error='acceso directo a tabla privada')
    sql('revoke select on public.catalog_events from authenticated')
    test('smoke clean after restoration', smoke.replace('CONTROL_UID_AQUI', C))

    # Historic normalized duplicates abort the entire migration without deletion.
    sql('create database duplicate_catalogs')
    sql('create schema auth; create table auth.users(id uuid primary key); create function auth.uid() returns uuid language sql stable as $$select null::uuid$$;', database='duplicate_catalogs')
    for filename in MIGRATIONS[:2]:
        sql((ROOT/'supabase/migrations'/filename).read_text(), database='duplicate_catalogs')
    sql("insert into public.subjects(code,name) values ('DUP','Uno'),(' dup ','Dos')", database='duplicate_catalogs')
    test('historic duplicate aborts whole migration', (ROOT/'supabase/migrations'/MIGRATIONS[-1]).read_text(), error='23505', database='duplicate_catalogs')
    test('historic duplicate rows preserved', 'select count(*) from public.subjects', 2, database='duplicate_catalogs')
    test('failed migration leaves no audit table', "select to_regclass('public.catalog_events') is null", 't', database='duplicate_catalogs')
    test('failed migration leaves no normalized index', "select to_regclass('public.subjects_code_normalized_key') is null", 't', database='duplicate_catalogs')
    print(f'PASS {checks} Control Escolar PostgreSQL assertions; disposable container only; no live Supabase changes', flush=True)
finally:
    run('docker', 'rm', '-f', NAME, check=False)
