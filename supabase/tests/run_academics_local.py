#!/usr/bin/env python3
"""Regresión SQL en un PostgreSQL desechable; nunca se conecta a Supabase.

Requiere Python 3, Docker y postgres:17-bookworm. Crea su propio contenedor sin
red ni puertos publicados; todas las consultas usan docker exec. Su auth.users
mínimo y auth.uid son fixtures: esta prueba verifica SQL/RLS, no Supabase Auth
ni HTTP/PostgREST. No acepta un DSN, contraseña o endpoint externo.
"""
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'seminario-academics-test-' + uuid.uuid4().hex[:10]
checks = 0

def run(*args, input=None, check=True):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=check)

def sql(query, ok=True):
    result = run('docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres', '-d', 'postgres', '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', input=query, check=False)
    if ok and result.returncode:
        raise AssertionError(result.stderr)
    if not ok and not result.returncode:
        raise AssertionError('Expected failure: ' + query)
    return result

def test(name, query, expected=None, error=None):
    global checks
    result=sql(query, ok=error is None)
    if expected is not None:
        assert result.stdout.strip() == str(expected), (name, result.stdout, result.stderr)
    if error:
        assert error in result.stderr, (name, result.stderr)
    checks += 1
    print('PASS', name, flush=True)

def as_user(uid, statement, role='authenticated'):
    return f"begin; set local role {role}; set local request.jwt.claim.sub = '{uid}'; select set_config('request.jwt.claims', '{{\"sub\":\"{uid}\",\"role\":\"{role}\"}}', true); {statement}; rollback;"

def scalar(uid, statement):
    # SET without SELECT avoids a setup result row in output.
    return f"begin; set local role authenticated; set local request.jwt.claim.sub = '{uid}'; set local request.jwt.claims = '{{\"sub\":\"{uid}\",\"role\":\"authenticated\"}}'; {statement}; rollback;"

A='10000000-0000-4000-8000-000000000001'
B='10000000-0000-4000-8000-000000000002'
I='10000000-0000-4000-8000-000000000003'
P='10000000-0000-4000-8000-000000000004'
C='10000000-0000-4000-8000-000000000005'
N='10000000-0000-4000-8000-000000000006'

def sid(n): return f'20000000-0000-4000-8000-{n:012d}'
def pid(n): return f'30000000-0000-4000-8000-{n:012d}'

try:
    run('docker','run','--rm','-d','--name',NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
    for _ in range(100):
        logs = run('docker','logs',NAME,check=False)
        if 'PostgreSQL init process complete' in logs.stdout + logs.stderr and run('docker','exec',NAME,'pg_isready','-U','postgres',check=False).returncode==0:
            break
        time.sleep(.2)
    else: raise AssertionError('PostgreSQL did not start')
    sql('''create role anon nologin; create role authenticated nologin;
        create schema auth; create table auth.users (id uuid primary key);
        create function auth.uid() returns uuid language sql stable as $$
            select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
        $$;
        grant usage on schema auth to anon, authenticated;
        grant execute on function auth.uid() to anon, authenticated;''')
    sql((ROOT/'supabase/migrations/20261021000000_create_profiles.sql').read_text())
    sql((ROOT/'supabase/migrations/20261021010000_create_academics.sql').read_text())
    sql('insert into auth.users(id) values ' + ','.join(f"('{u}')" for u in [A,B,I,P,C,N]) + ';')
    sql(f"insert into public.profiles(id,full_name,role,active) values ('{A}','Alumno A','student',true),('{B}','Alumno B','student',true),('{I}','Inactivo','student',false),('{P}','Profesor','professor',true),('{C}','Control','control_escolar',true);")
    seed=(ROOT/'supabase/seeds/demo_enrollments.sql').read_text()
    smoke=(ROOT/'supabase/tests/academics_rls.sql').read_text()
    test('demo seed first run',seed.replace('PEGA_AQUI_EL_UID',A),expected='Datos de ejemplo listos: dos inscripciones DEMO para la cuenta elegida')
    test('demo seed rerun',seed.replace('PEGA_AQUI_EL_UID',A),expected='Datos de ejemplo listos: dos inscripciones DEMO para la cuenta elegida')
    test('seed stays duplicate-free','select count(*) from public.enrollments',2)
    for label,uid in [('inactive',I),('professor',P),('control',C),('missing profile',N)]:
        test('seed rejects '+label,seed.replace('PEGA_AQUI_EL_UID',uid),error='Se requiere el UID')
    sql('insert into public.subjects(id,code,name) values '+','.join(f"('{sid(n)}','FIX-{n}','Materia {n}')" for n in range(1,5))+';')
    sql('insert into public.academic_periods(id,name,starts_on,ends_on) values '+','.join(f"('{pid(n)}','Periodo {n}','2026-01-01','2026-06-01')" for n in range(1,5))+';')
    enrollments=[(A,1,1),(A,2,2),(B,1,1),(B,3,3),(I,1,1),(P,1,1),(C,1,1)]
    sql('insert into public.enrollments(student_id,subject_id,period_id) values '+','.join(f"('{u}','{sid(s)}','{pid(p)}')" for u,s,p in enrollments)+';')
    for label,uid,count_s,count_p,count_e in [('A',A,4,3,4),('B',B,2,2,2),('inactive',I,0,0,0),('professor',P,0,0,0),('control',C,0,0,0),('missing profile',N,0,0,0)]:
        for table,count in [('subjects',count_s),('academic_periods',count_p),('enrollments',count_e)]:
            test(label+' read '+table,scalar(uid,f'select count(*) from public.{table}'),count)
    test('A cannot filter B enrollments',scalar(A,f"select count(*) from public.enrollments where student_id='{B}'"),0)
    test('B cannot filter A enrollments',scalar(B,f"select count(*) from public.enrollments where student_id='{A}'"),0)
    test('A cannot read B exclusive subject',scalar(A,f"select count(*) from public.subjects where id='{sid(3)}'"),0)
    test('B cannot read A exclusive subject',scalar(B,f"select count(*) from public.subjects where id='{sid(2)}'"),0)
    test('A cannot read B exclusive period',scalar(A,f"select count(*) from public.academic_periods where id='{pid(3)}'"),0)
    test('B cannot read A exclusive period',scalar(B,f"select count(*) from public.academic_periods where id='{pid(2)}'"),0)
    test('shared subject does not expose other student',scalar(A,f"select count(*) from public.enrollments where subject_id='{sid(1)}'"),1)
    test('FK joins expose own complete rows',scalar(A,'select count(*) from public.enrollments e join public.subjects s on s.id=e.subject_id join public.academic_periods p on p.id=e.period_id'),4)
    test('manual smoke A',smoke.replace('PEGA_AQUI_EL_UID',A),expected=None)
    test('manual smoke B',smoke.replace('PEGA_AQUI_EL_UID',B),expected=None)
    for table in ['subjects','academic_periods','enrollments']:
        test('anon cannot select '+table,f'begin; set local role anon; select * from public.{table}; rollback;',error='permission denied')
        for mutation in [f'insert into public.{table} default values',f'update public.{table} set id=id',f'delete from public.{table}',f'truncate public.{table}']:
            test('authenticated cannot '+mutation.split()[0]+' '+table,scalar(A,mutation),error='permission denied')
    sql(f"update public.profiles set active=false where id='{A}';")
    for table in ['subjects','academic_periods','enrollments']:
        test('deactivation immediately hides '+table,scalar(A,f'select count(*) from public.{table}'),0)
    sql(f"update public.profiles set active=true,role='professor' where id='{A}';")
    for table in ['subjects','academic_periods','enrollments']:
        test('role change immediately hides '+table,scalar(A,f'select count(*) from public.{table}'),0)
    sql(f"update public.profiles set role='student' where id='{A}';")
    test('duplicate enrollment rejected',f"insert into public.enrollments(student_id,subject_id,period_id) values ('{A}','{sid(1)}','{pid(1)}')",error='duplicate key')
    test('unknown student rejected',f"insert into public.enrollments(student_id,subject_id,period_id) values ('{N}','{sid(1)}','{pid(1)}')",error='foreign key')
    test('unknown subject rejected',f"insert into public.enrollments(student_id,subject_id,period_id) values ('{A}','{sid(99)}','{pid(1)}')",error='foreign key')
    test('unknown period rejected',f"insert into public.enrollments(student_id,subject_id,period_id) values ('{A}','{sid(1)}','{pid(99)}')",error='foreign key')
    test('blank subject code rejected',"insert into public.subjects(code,name) values ('  ','Nombre')",error='check constraint')
    test('blank subject name rejected',"insert into public.subjects(code,name) values ('BLANK','  ')",error='check constraint')
    test('blank period name rejected',"insert into public.academic_periods(name,starts_on,ends_on) values ('  ','2026-01-01','2026-06-01')",error='check constraint')
    test('inverted period dates rejected',"insert into public.academic_periods(name,starts_on,ends_on) values ('INVERTED','2026-06-01','2026-01-01')",error='check constraint')
    test('unique code enforced',"insert into public.subjects(code,name) values ('FIX-1','Otro nombre')",error='duplicate key')
    test('unique period name enforced',"insert into public.academic_periods(name,starts_on,ends_on) values ('Periodo 1','2026-01-01','2026-06-01')",error='duplicate key')
    sql("update public.subjects set name='Nombre modificado' where code='DEMO-FIL-101';")
    test('seed rejects name conflict without overwrite',seed.replace('PEGA_AQUI_EL_UID',A),error='Ya existe un código DEMO')
    test('seed leaves existing name unchanged',"select name from public.subjects where code='DEMO-FIL-101'",'Nombre modificado')
    sql("update public.subjects set name='Filosofía — ejemplo' where code='DEMO-FIL-101';")
    sql("update public.academic_periods set ends_on='2026-12-19' where name='DEMO 2026 — semestre de prueba';")
    test('seed rejects period conflict',seed.replace('PEGA_AQUI_EL_UID',A),error='Ya existe el periodo DEMO')
    # Fault injection: the shipped read-only smoke must detect actual regressions.
    sql('alter table public.enrollments disable row level security;')
    test('smoke detects disabled RLS',smoke.replace('PEGA_AQUI_EL_UID',A),error='RLS no está activado')
    sql('alter table public.enrollments enable row level security;')
    sql('create policy "TEST broad subjects" on public.subjects for select to authenticated using (true);')
    test('smoke detects broad catalog policy',smoke.replace('PEGA_AQUI_EL_UID',A),error='catálogo no vinculado')
    sql('drop policy "TEST broad subjects" on public.subjects;')
    sql('create policy "TEST broad enrollments" on public.enrollments for select to authenticated using (true);')
    test('smoke detects broad enrollment policy',smoke.replace('PEGA_AQUI_EL_UID',A),error='inscripciones ajenas')
    sql('drop policy "TEST broad enrollments" on public.enrollments;')
    sql('grant update on public.enrollments to authenticated;')
    test('smoke detects write privilege',smoke.replace('PEGA_AQUI_EL_UID',A),error='conserva escritura')
    sql('revoke update on public.enrollments from authenticated;')
    print(f'PASS {checks} PostgreSQL assertions; disposable container only; no live Supabase changes',flush=True)
finally:
    run('docker','rm','-f',NAME,check=False)
