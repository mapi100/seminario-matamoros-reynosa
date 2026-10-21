#!/usr/bin/env python3
"""Regresión de calificaciones: PostgreSQL desechable, nunca Supabase real.

Requiere Python 3, Docker y postgres:17-bookworm. Solo usa docker exec sobre su
propio contenedor sin red ni puertos; no admite DSN ni credenciales externas.
auth.users y auth.uid() son fixtures mínimos. Se comprueba SQL/RLS, no HTTP,
PostgREST ni Supabase Auth. Ejecutar: python3 supabase/tests/run_grades_local.py.
"""
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'seminario-grades-test-' + uuid.uuid4().hex[:10]
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
    return (f"begin; set local role {role}; set local request.jwt.claim.sub = '{uid}'; "
            f"set local request.jwt.claims = '{{\"sub\":\"{uid}\",\"role\":\"{role}\"}}'; "
            f'{statement}; rollback;')


A = '10000000-0000-4000-8000-000000000001'
B = '10000000-0000-4000-8000-000000000002'
I = '10000000-0000-4000-8000-000000000003'
P = '10000000-0000-4000-8000-000000000004'
C = '10000000-0000-4000-8000-000000000005'
N = '10000000-0000-4000-8000-000000000006'


def enrollment(uid, code):
    return sql(f"select e.id from public.enrollments e join public.subjects s "
               f"on s.id=e.subject_id where e.student_id='{uid}' and s.code='{code}'").stdout.strip()


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
                 '20261021020000_create_enrollment_grades.sql']:
        sql((ROOT / 'supabase/migrations' / name).read_text())
    sql('insert into auth.users(id) values ' + ','.join(f"('{u}')" for u in [A, B, I, P, C, N]) + ';')
    sql(f"insert into public.profiles(id,full_name,role,active) values "
        f"('{A}','Alumno A','student',true),('{B}','Alumno B','student',true),"
        f"('{I}','Inactivo','student',false),('{P}','Profesor','professor',true),"
        f"('{C}','Control','control_escolar',true);")
    academic_seed = (ROOT / 'supabase/seeds/demo_enrollments.sql').read_text()
    seed = (ROOT / 'supabase/seeds/demo_grades.sql').read_text()
    smoke = (ROOT / 'supabase/tests/grades_rls.sql').read_text()
    test('grade seed requires existing DEMO enrollments', seed.replace('PEGA_AQUI_EL_UID', A),
         error='Faltan las dos inscripciones DEMO')
    sql(academic_seed.replace('PEGA_AQUI_EL_UID', A))
    sql(academic_seed.replace('PEGA_AQUI_EL_UID', B))
    test('grade seed first run', seed.replace('PEGA_AQUI_EL_UID', A),
         expected='Calificaciones DEMO listas: Filosofía publicada e Historia sin publicar')
    test('grade seed rerun', seed.replace('PEGA_AQUI_EL_UID', A),
         expected='Calificaciones DEMO listas: Filosofía publicada e Historia sin publicar')
    test('seed stays duplicate-free', 'select count(*) from public.enrollment_grades', 2)
    for label, uid in [('inactive', I), ('professor', P), ('control', C), ('missing profile', N)]:
        test('seed rejects ' + label, seed.replace('PEGA_AQUI_EL_UID', uid), error='Se requiere el UID')
    af = enrollment(A, 'DEMO-FIL-101')
    ah = enrollment(A, 'DEMO-HIS-101')
    bf = enrollment(B, 'DEMO-FIL-101')
    bh = enrollment(B, 'DEMO-HIS-101')
    sql(f"insert into public.enrollment_grades(enrollment_id,score,published) values "
        f"('{bf}',98,true),('{bh}',81,false);")
    sql("insert into public.subjects(code,name) values ('FIX-ZERO','Nota cero'),"
        "('FIX-MAX','Nota cien'),('FIX-EMPTY','Sin nota');")
    sql(f"insert into public.enrollments(student_id,subject_id,period_id) "
        f"select '{A}',s.id,p.id from public.subjects s cross join public.academic_periods p "
        "where s.code like 'FIX-%';")
    az = enrollment(A, 'FIX-ZERO')
    am = enrollment(A, 'FIX-MAX')
    ae = enrollment(A, 'FIX-EMPTY')
    sql(f"insert into public.enrollment_grades(enrollment_id,score,published) values "
        f"('{az}',0,true),('{am}',100,true);")
    for uid in [I, P, C]:
        sql(f"insert into public.enrollments(student_id,subject_id,period_id) "
            f"select '{uid}',s.id,p.id from public.subjects s cross join public.academic_periods p "
            "where s.code='DEMO-FIL-101';")
        eid = enrollment(uid, 'DEMO-FIL-101')
        sql(f"insert into public.enrollment_grades(enrollment_id,score,published) values ('{eid}',90,true)")
    for label, uid, count in [('A', A, 3), ('B', B, 1), ('inactive', I, 0),
                              ('professor', P, 0), ('control', C, 0), ('no profile', N, 0)]:
        test(label + ' reads only own published grades', scalar(uid, 'select count(*) from public.enrollment_grades'), count)
    test('A cannot directly filter B grade', scalar(A, f"select count(*) from public.enrollment_grades where enrollment_id='{bf}'"), 0)
    test('B cannot directly filter A grade', scalar(B, f"select count(*) from public.enrollment_grades where enrollment_id='{af}'"), 0)
    test('A draft hidden by direct filter', scalar(A, f"select count(*) from public.enrollment_grades where enrollment_id='{ah}'"), 0)
    test('B draft hidden by direct filter', scalar(B, f"select count(*) from public.enrollment_grades where enrollment_id='{bh}'"), 0)
    test('published=false filter cannot reveal drafts', scalar(A, 'select count(*) from public.enrollment_grades where not published'), 0)
    test('grade page IN filter cannot broaden access', scalar(A, f"select count(*) from public.enrollment_grades where enrollment_id in ('{af}','{ah}','{bf}')"), 1)
    test('absent grade remains absent', scalar(A, f"select count(*) from public.enrollment_grades where enrollment_id='{ae}'"), 0)
    test('zero is a visible valid score', scalar(A, f"select score from public.enrollment_grades where enrollment_id='{az}'"), '0.00')
    test('hundred is a visible valid score', scalar(A, f"select score from public.enrollment_grades where enrollment_id='{am}'"), '100.00')
    test('grade joins expose only own complete rows', scalar(A, 'select count(*) from public.enrollment_grades g join public.enrollments e on e.id=g.enrollment_id join public.subjects s on s.id=e.subject_id'), 3)
    test('manual grade smoke A', smoke.replace('PEGA_AQUI_EL_UID', A))
    test('manual grade smoke B', smoke.replace('PEGA_AQUI_EL_UID', B))
    test('anon cannot select', scalar(A, 'select * from public.enrollment_grades', role='anon'), error='permission denied')
    for uid, label in [(A, 'student'), (P, 'professor'), (C, 'control')]:
        for verb, mutation in [('insert', 'insert into public.enrollment_grades default values'),
                               ('update', 'update public.enrollment_grades set score=100'),
                               ('delete', 'delete from public.enrollment_grades'),
                               ('truncate', 'truncate public.enrollment_grades')]:
            test(label + ' cannot ' + verb, scalar(uid, mutation), error='permission denied')
    sql(f"update public.profiles set active=false where id='{A}';")
    test('deactivation immediately hides published grades', scalar(A, 'select count(*) from public.enrollment_grades'), 0)
    sql(f"update public.profiles set active=true,role='professor' where id='{A}';")
    test('role change immediately hides published grades', scalar(A, 'select count(*) from public.enrollment_grades'), 0)
    sql(f"update public.profiles set role='student' where id='{A}';")
    test('duplicate grade rejected', f"insert into public.enrollment_grades(enrollment_id,score) values ('{af}',90)", error='duplicate key')
    test('missing enrollment rejected', "insert into public.enrollment_grades(enrollment_id,score) values ('00000000-0000-0000-0000-000000000000',90)", error='foreign key')
    test('null score rejected', f"insert into public.enrollment_grades(enrollment_id,score) values ('{ae}',null)", error='not-null constraint')
    for score in ['-0.01', '100.01', "'NaN'"]:
        test('invalid score rejected ' + score, f"insert into public.enrollment_grades(enrollment_id,score) values ('{ae}',{score})", error='check constraint')
    for score in ["'Infinity'", "'-Infinity'"]:
        test('infinite score rejected ' + score, f"insert into public.enrollment_grades(enrollment_id,score) values ('{ae}',{score})", error='numeric field overflow')
    test('grade prevents accidental enrollment deletion', f"delete from public.enrollments where id='{af}'", error='foreign key')
    test('grade prevents cascading account deletion', f"delete from auth.users where id='{A}'", error='foreign key')
    test('new grade defaults unpublished', f"insert into public.enrollment_grades(enrollment_id,score) values ('{ae}',50); select published from public.enrollment_grades where enrollment_id='{ae}'", 'f')
    test('default draft invisible', scalar(A, f"select count(*) from public.enrollment_grades where enrollment_id='{ae}'"), 0)
    sql(f"delete from public.enrollment_grades where enrollment_id='{ae}'")
    # Conflict must roll back even a missing DEMO grade inserted before detection.
    sql(f"delete from public.enrollment_grades where enrollment_id='{af}'; update public.enrollment_grades set score=73 where enrollment_id='{ah}'")
    test('seed refuses conflicting score', seed.replace('PEGA_AQUI_EL_UID', A), error='no se sobrescribió')
    test('seed conflict rolls back attempted insertion', f"select count(*) from public.enrollment_grades where enrollment_id='{af}'", 0)
    test('seed conflict preserves existing score', f"select score from public.enrollment_grades where enrollment_id='{ah}'", '73.00')
    sql(f"update public.enrollment_grades set score=72 where enrollment_id='{ah}';")
    sql(seed.replace('PEGA_AQUI_EL_UID', A))
    sql(f"update public.enrollment_grades set published=true where enrollment_id='{ah}'")
    test('seed refuses conflicting publication', seed.replace('PEGA_AQUI_EL_UID', A), error='no se sobrescribió')
    sql(f"update public.enrollment_grades set published=false where enrollment_id='{ah}'")
    # Future expansion of enrollment/profile RLS must not expose grades by itself.
    sql('create policy "TEST broad enrollments" on public.enrollments for select to authenticated using (true);')
    test('broader enrollment RLS still denies another student grade', scalar(A, f"select count(*) from public.enrollment_grades where enrollment_id='{bf}'"), 0)
    test('broader enrollment RLS still denies professor grade', scalar(P, 'select count(*) from public.enrollment_grades'), 0)
    sql('create policy "TEST broad profiles" on public.profiles for select to authenticated using (true);')
    test('broader profile RLS still denies professor grade', scalar(P, 'select count(*) from public.enrollment_grades'), 0)
    test('broader profile RLS still denies inactive grade', scalar(I, 'select count(*) from public.enrollment_grades'), 0)
    sql('drop policy "TEST broad profiles" on public.profiles; drop policy "TEST broad enrollments" on public.enrollments;')
    # The shipped read-only smoke must detect deliberately broken safeguards.
    sql('alter table public.enrollment_grades disable row level security;')
    test('smoke detects disabled RLS', smoke.replace('PEGA_AQUI_EL_UID', A), error='RLS no está activado')
    sql('alter table public.enrollment_grades enable row level security;')
    sql('create policy "TEST broad grades" on public.enrollment_grades for select to authenticated using (true);')
    test('smoke detects broad grades policy', smoke.replace('PEGA_AQUI_EL_UID', A), error='ajenas o sin publicar')
    sql('drop policy "TEST broad grades" on public.enrollment_grades;')
    sql('grant update on public.enrollment_grades to authenticated;')
    test('smoke detects write grant', smoke.replace('PEGA_AQUI_EL_UID', A), error='conserva escritura')
    sql('revoke update on public.enrollment_grades from authenticated; grant select on public.enrollment_grades to anon;')
    test('smoke detects anonymous grant', smoke.replace('PEGA_AQUI_EL_UID', A), error='anon conserva permisos')
    sql('revoke select on public.enrollment_grades from anon;')
    print(f'PASS {checks} grade PostgreSQL assertions; disposable container only; no live Supabase changes', flush=True)
finally:
    run('docker', 'rm', '-f', NAME, check=False)
