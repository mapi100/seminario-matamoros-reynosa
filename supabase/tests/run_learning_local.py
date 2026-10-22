#!/usr/bin/env python3
"""Aula virtual en PostgreSQL desechable; sin credenciales ni tráfico a Supabase.

Requiere Python 3, Docker y postgres:17-bookworm. El contenedor no tiene red ni
puertos publicados. Auth y Storage son fixtures mínimos: estas pruebas validan
PostgreSQL/RLS/RPC, no la entrega HTTP de archivos del servicio Storage real.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
NAME = 'seminario-learning-test-' + uuid.uuid4().hex[:10]
checks = 0


def run(*args, input=None, check=True):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=check)


def sql(query, ok=True):
    result = run('docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres', '-d', 'postgres',
                 '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose',
                 input=query, check=False)
    if ok and result.returncode:
        raise AssertionError(result.stderr)
    if not ok and not result.returncode:
        raise AssertionError('Expected failure: ' + query)
    return result


def check(name, condition, details=None):
    global checks
    assert condition, (name, details)
    checks += 1
    print('PASS', name, flush=True)


def test(name, query, expected=None, error=None):
    result = sql(query, ok=error is None)
    if expected is not None:
        assert result.stdout.strip() == str(expected), (name, result.stdout, result.stderr)
    if error:
        errors = [error] if isinstance(error, str) else error
        assert any(value in result.stderr for value in errors), (name, result.stderr)
    check(name, True)
    return result.stdout.strip()


def quote(value):
    if value is None:
        return 'null'
    return "'" + str(value).replace("'", "''") + "'"


def uid(n):
    return f'20000000-0000-4000-8000-{n:012d}'


def actor(who, statement, role='authenticated', commit=False):
    claim = who or ''
    # A forged UI/user_metadata role never grants real Control Escolar access.
    claims = json.dumps({'sub': claim, 'role': role, 'user_metadata': {'role': 'control_escolar'}})
    return (f"begin; set local role {role}; set local request.jwt.claim.sub={quote(claim)}; "
            f"set local request.jwt.claims={quote(claims)}; {statement}; "
            + ('commit;' if commit else 'rollback;'))


def rquery(resource, course=None, offset=0, limit=30):
    return 'select public.portal_learning_read(' + ','.join([
        quote(resource), quote(course), str(offset) if offset is not None else 'null',
        str(limit) if limit is not None else 'null']) + ')'


def wquery(action, course, data):
    return 'select public.portal_learning_write(' + ','.join([
        quote(action), quote(course), quote(json.dumps(data)) + '::jsonb']) + ')'


def read(who, resource='course', course=None, offset=0, limit=30):
    return json.loads(sql(actor(who, rquery(resource, course, offset, limit))).stdout)


def write(who, action, course, data, *, name=None):
    result = json.loads(sql(actor(who, wquery(action, course, data), commit=True)).stdout)
    check(name or action, result.get('saved') is True and bool(result.get('id')), result)
    return result


def deny(name, who, action, course, data, error='42501'):
    return test(name, actor(who, wquery(action, course, data), commit=True), error=error)


def item(rows, item_id):
    return next(row for row in rows if row['id'] == item_id)


def background(query):
    proc = subprocess.Popen(['docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres',
                             '-d', 'postgres', '-X', '-q', '-t', '-A', '-v',
                             'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    proc.stdin.write(query)
    proc.stdin.close()
    return proc


def wait_sleep(tag):
    for _ in range(150):
        found = sql('select count(*) from pg_stat_activity where application_name=' + quote(tag)
                    + " and wait_event='PgSleep'").stdout.strip()
        if found == '1':
            return
        time.sleep(.02)
    raise AssertionError('Concurrent writer did not acquire its locks')


A, B, P, C, P2, I, IP, IC, N = [uid(n) for n in range(1, 10)]
S, S2, T = [uid(n) for n in (20, 21, 30)]
EA, EB, EB2, TA, TA2 = [uid(n) for n in (40, 41, 42, 50, 51)]
K, L = uid(60), uid(61)
ZERO = '00000000-0000-0000-0000-000000000000'
FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
AUTH = '''
create role anon nologin; create role authenticated nologin; create role service_role nologin;
create schema auth; create table auth.users(id uuid primary key,email text);
create function auth.uid() returns uuid language sql stable as $$
 select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
create function auth.role() returns text language sql stable as $$
 select coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role','') $$;
create function auth.jwt() returns jsonb language sql stable as $$
 select coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb) $$;
grant usage on schema auth to anon,authenticated,service_role;
grant execute on all functions in schema auth to anon,authenticated,service_role;
'''
STORAGE = '''
create schema storage;
create table storage.buckets(id text primary key,name text,public boolean default false,
 file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text references storage.buckets(id),
 name text,owner_id text,metadata jsonb default '{}'::jsonb,created_at timestamptz default now(),
 unique(bucket_id,name));
alter table storage.objects enable row level security;
grant usage on schema storage to authenticated;
grant select,insert,delete on storage.objects to authenticated;
create function storage.foldername(name text) returns text[] language sql immutable as $$
 select (string_to_array(name,'/'))[1:cardinality(string_to_array(name,'/'))-1] $$;
'''


def main():
    run('docker', 'run', '--rm', '-d', '--name', NAME, '--network', 'none',
        '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:17-bookworm')
    for _ in range(100):
        logs = run('docker', 'logs', NAME, check=False)
        if ('PostgreSQL init process complete' in logs.stdout + logs.stderr
                and run('docker', 'exec', NAME, 'pg_isready', '-U', 'postgres', check=False).returncode == 0):
            break
        time.sleep(.2)
    else:
        raise AssertionError('PostgreSQL did not start')
    sql(AUTH)
    paths = sorted((ROOT / 'supabase/migrations').glob('*.sql'))
    for path in paths:
        if path.name >= '20261021060000':
            break
        sql(path.read_text())
    people = [(A, 'Alumno Alfa', 'student', True), (B, 'Alumno Beta', 'student', True),
              (P, 'Profesor Historia', 'professor', True), (C, 'Control Escolar', 'control_escolar', True),
              (P2, 'Profesor Filosofía', 'professor', True), (I, 'Alumno inactivo', 'student', False),
              (IP, 'Profesor inactivo', 'professor', False), (IC, 'Control inactivo', 'control_escolar', False),
              (N, 'Alumno sin inscripción', 'student', True)]
    for who, name, role, active in people:
        sql(f"insert into auth.users values('{who}','fixture{who[-2:]}@example.invalid');"
            f"insert into public.profiles(id,full_name,role,active) values('{who}',{quote(name)},'{role}',{str(active).lower()})")
    sql(f"""
insert into public.subjects(id,code,name) values('{S}','HIS-101','Historia'),('{S2}','FIL-101','Filosofía');
insert into public.academic_periods(id,name,starts_on,ends_on) values('{T}','Periodo de prueba','2026-08-01','2027-06-30');
insert into public.enrollments(id,student_id,subject_id,period_id) values
 ('{EA}','{A}','{S}','{T}'),('{EB}','{B}','{S}','{T}'),('{EB2}','{B}','{S2}','{T}');
insert into public.teaching_assignments(id,professor_id,subject_id,period_id) values
 ('{TA}','{P}','{S}','{T}'),('{TA2}','{P2}','{S2}','{T}');
insert into public.enrollment_grades(enrollment_id,score,published) values('{EA}',100,true);
""")
    for path in paths:
        if '20261021060000' <= path.name < '20261021090000':
            sql(path.read_text())
    sql(f"update public.course_offerings set id='{K}' where subject_id='{S}';"
        f"update public.course_offerings set id='{L}' where subject_id='{S2}'")
    test('legacy final grade remains unchanged after migration', actor(A, 'select score from public.enrollment_grades'), '100.00')

    tables = sql("select tablename from pg_tables where schemaname='public' and tablename like 'learning_%' order by tablename").stdout.split()
    check('all expected LMS tables installed', len(tables) >= 11, tables)
    for table in tables:
        test('RLS enabled ' + table, "select relrowsecurity from pg_class where oid=" + quote('public.' + table) + '::regclass', 't')
        for role in ('authenticated', 'anon'):
            test('no direct table privileges ' + role + ' ' + table,
                 f"select has_table_privilege('{role}','public.{table}','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')", 'f')
    for signature in ('portal_learning_read(text,uuid,integer,integer)', 'portal_learning_write(text,uuid,jsonb)'):
        test('public RPC requires authenticated role ' + signature,
             "select has_function_privilege('anon'," + quote('public.' + signature) + ",'EXECUTE')", 'f')
        test('security definer fixed search_path ' + signature,
             'select prosecdef and array_to_string(proconfig,\' \') like \'%search_path=%\' from pg_proc where oid='
             + quote('public.' + signature) + '::regprocedure', 't')
    for signature in ('_learning_require_actor()', '_learning_require_course(uuid,boolean)', '_learning_can_course(uuid)', '_learning_has_submission_file(uuid,uuid)'):
        test('private authorization helper ' + signature,
             "select has_function_privilege('authenticated'," + quote('public.' + signature) + ",'EXECUTE')", 'f')
    test('anonymous dashboard denied', actor(None, rquery('dashboard'), role='anon'), error='42501')
    for who in (I, IP, IC, ZERO):
        test('inactive or missing profile denied ' + who[-2:], actor(who, rquery('dashboard')), error='42501')
    check('student dashboard contains only enrolled class', [r['id'] for r in read(A, 'dashboard')['courses']] == [K])
    check('second student sees two enrolled classes', len(read(B, 'dashboard')['courses']) == 2)
    check('professor dashboard contains only assigned class', [r['id'] for r in read(P, 'dashboard')['courses']] == [K])
    check('Control Escolar can manage both active classes', len(read(C, 'dashboard')['courses']) == 2)
    check('active student without enrollment has no courses', read(N, 'dashboard')['courses'] == [])
    for who in (A, N, P):
        test('foreign course read denied ' + who[-2:], actor(who, rquery('course', L)), error='42501')
    for who in (A, B):
        for resource in ('gradebook', 'participants'):
            test('student cannot open staff ' + resource + ' ' + who[-2:], actor(who, rquery(resource, K)), error='42501')
    for offset, limit in ((-1, 30), (0, 101), (None, 30), (0, None), (0, 0), (100001, 30)):
        test('invalid read pagination ' + str((offset, limit)), actor(P, rquery('course', K, offset, limit)), error='22023')
    test('unknown read resource rejected', actor(P, rquery('raw-secret-table', K)), error='22023')
    deny('unknown write action rejected', P, 'drop_table', K, {}, '22023')
    deny('null write action rejected', P, None, K, {}, '22023')
    test('null read resource rejected', actor(P, rquery(None, K)), error='22023')
    test('non-object write rejected', actor(P, "select public.portal_learning_write('syllabus_save'," + quote(K) + ",'[]'::jsonb)"), error='22023')
    staff_actions = [
        ('syllabus_save', {'body': 'Programa de prueba'}),
        ('announcement_save', {'title': 'Aviso', 'body': 'Contenido', 'published': True}),
        ('module_save', {'title': 'Unidad', 'published': True}),
        ('topic_save', {'title': 'Tema', 'module_id': ZERO, 'published': True}),
        ('assignment_save', {'title': 'Tarea', 'published': True}),
        ('event_save', {'title': 'Evento', 'starts_at': FUTURE}),
        ('grade_save', {'assignment_id': ZERO, 'enrollment_id': EA, 'score': 100, 'revision': 0}),
        ('grade_publish', {'assignment_id': ZERO, 'enrollment_id': EA, 'revision': 0}),
    ]
    for action, data in staff_actions:
        deny('student forbidden staff write ' + action, A, action, K, data)
        deny('unassigned professor forbidden write ' + action, P2, action, K, data)
        deny('inactive control forbidden write ' + action, IC, action, K, data)
    deny('professor cannot publish institutional announcement', P, 'announcement_save', None, {'title': 'Global', 'published': True})
    deny('student cannot publish institutional event', A, 'event_save', None, {'title': 'Global', 'starts_at': FUTURE})
    institutional = write(C, 'announcement_save', None, {'title': 'Aviso institucional', 'body': 'Visible para la comunidad', 'published': True, 'pinned': True})
    write(C, 'announcement_save', None, {'title': 'Borrador institucional', 'body': 'Privado', 'published': False})
    published = write(P, 'announcement_save', K, {'title': 'Anuncio Historia', 'body': '<script>dato literal</script>', 'published': True, 'pinned': True})
    hidden = write(P, 'announcement_save', K, {'title': 'Anuncio borrador', 'body': 'Privado docente', 'published': False})
    foreign_announcement = write(P2, 'announcement_save', L, {'title': 'Anuncio Filosofía', 'body': 'Solo otro curso', 'published': True})
    da = read(A, 'dashboard')
    check('dashboard shows institutional and own published announcements only', {r['id'] for r in da['announcements']} == {institutional['id'], published['id']})
    check('student course excludes unpublished announcement', {r['id'] for r in read(A, 'course', K)['announcements']} == {published['id']})
    check('assigned professor sees own course drafts', {r['id'] for r in read(P, 'course', K)['announcements']} == {published['id'], hidden['id']})
    check('announcement body remains literal text', item(read(A, 'course', K)['announcements'], published['id'])['body'] == '<script>dato literal</script>')
    deny('stale announcement edit rejected', P, 'announcement_save', K, {'id': published['id'], 'title': 'Cambio', 'body': '', 'published': True, 'revision': 0}, 'PT409')
    deny('foreign announcement cannot be moved into own course', P, 'announcement_save', K, {'id': foreign_announcement['id'], 'title': 'Robo', 'published': True, 'revision': 1}, ('42501', 'PT409'))
    for title in ('', '   ', 'x' * 201):
        deny('invalid announcement title ' + repr(title[:10]), P, 'announcement_save', K, {'title': title, 'published': True}, '22023')
    deny('string publication flag rejected', P, 'announcement_save', K, {'title': 'Aviso', 'published': 'true'}, '22023')
    write(P, 'syllabus_save', K, {'body': 'Programa Historia\nUnidad 1: fuentes y método'})
    check('student sees course syllabus', read(A, 'course', K)['course']['syllabus'].startswith('Programa Historia'))
    deny('oversized syllabus rejected', P, 'syllabus_save', K, {'body': 'x' * 40001}, '22023')

    module = write(P, 'module_save', K, {'title': 'Unidad 1', 'position': 0, 'published': True})
    draft_module = write(P, 'module_save', K, {'title': 'Unidad borrador', 'position': 1, 'published': False})
    foreign_module = write(P2, 'module_save', L, {'title': 'Unidad de Filosofía', 'position': 0, 'published': True})
    topic = write(P, 'topic_save', K, {'title': 'Fuentes primarias', 'module_id': module['id'], 'body': 'Lectura de prueba', 'url': 'https://example.org/lectura', 'position': 0, 'published': True})
    draft_topic = write(P, 'topic_save', K, {'title': 'Tema borrador', 'module_id': module['id'], 'published': False})
    inherited_draft = write(P, 'topic_save', K, {'title': 'Tema bajo unidad oculta', 'module_id': draft_module['id'], 'published': True})
    foreign_topic = write(P2, 'topic_save', L, {'title': 'Tema extranjero', 'module_id': foreign_module['id'], 'published': True})
    student_modules = read(A, 'course', K)['modules']
    check('student sees published modules only', [r['id'] for r in student_modules] == [module['id']])
    check('student sees published topics only', [r['id'] for r in student_modules[0]['topics']] == [topic['id']])
    write(A, 'topic_complete', K, {'topic_id': topic['id'], 'completed': True, 'student_id': B})
    check('own progress visible', read(A, 'course', K)['modules'][0]['topics'][0]['completed'] is True)
    check('progress remains private to student', read(B, 'course', K)['modules'][0]['topics'][0]['completed'] is False)
    write(A, 'topic_complete', K, {'topic_id': topic['id'], 'completed': False})
    check('topic progress can be cleared', read(A, 'course', K)['modules'][0]['topics'][0]['completed'] is False)
    for forbidden_topic in (draft_topic['id'], inherited_draft['id'], foreign_topic['id']):
        deny('cannot complete hidden or foreign topic ' + forbidden_topic[-6:], A, 'topic_complete', K, {'topic_id': forbidden_topic, 'completed': True})
    deny('teacher cannot impersonate student progress', P, 'topic_complete', K, {'topic_id': topic['id'], 'completed': True})
    deny('invalid progress boolean rejected', A, 'topic_complete', K, {'topic_id': topic['id'], 'completed': 'true'}, '22023')
    deny('topic cannot attach foreign module', P, 'topic_save', K, {'title': 'Robo', 'module_id': foreign_module['id'], 'published': True})
    for unsafe in ('javascript:alert(1)', 'data:text/html,test', 'https://example.org/with space'):
        deny('unsafe resource URL rejected ' + unsafe[:15], P, 'topic_save', K, {'title': 'Liga', 'module_id': module['id'], 'url': unsafe, 'published': True}, '22023')

    task = write(P, 'assignment_save', K, {'title': 'Ensayo', 'instructions': 'Entrega tu análisis', 'due_at': FUTURE, 'allow_late': False, 'published': True})
    draft_task = write(P, 'assignment_save', K, {'title': 'Tarea borrador', 'published': False})
    closed_task = write(P, 'assignment_save', K, {'title': 'Cerrada', 'due_at': PAST, 'allow_late': False, 'published': True})
    late_task = write(P, 'assignment_save', K, {'title': 'Acepta atraso', 'due_at': PAST, 'allow_late': True, 'published': True})
    foreign_task = write(P2, 'assignment_save', L, {'title': 'Tarea Filosofía', 'due_at': FUTURE, 'published': True})
    for bad_date in ('infinity', '-infinity', 'not-a-date'):
        deny('non-finite task deadline rejected ' + bad_date, P, 'assignment_save', K, {'title': 'Fecha inválida', 'due_at': bad_date, 'published': True}, '22023')
    check('student assignment list excludes drafts', draft_task['id'] not in {r['id'] for r in read(A, 'course', K)['assignments']})
    check('teacher assignment list includes drafts', draft_task['id'] in {r['id'] for r in read(P, 'course', K)['assignments']})
    check('dashboard includes pending assignment', task['id'] in {r['id'] for r in read(A, 'dashboard')['work']})
    for assignment_id in (draft_task['id'], foreign_task['id']):
        deny('student cannot submit hidden/foreign task', A, 'submit', K, {'assignment_id': assignment_id, 'body': 'Texto'})
    deny('closed deadline blocks submission', A, 'submit', K, {'assignment_id': closed_task['id'], 'body': 'Texto'}, '22023')
    deny('empty submission rejected', A, 'submit', K, {'assignment_id': task['id'], 'body': '', 'url': ''}, '22023')
    deny('submission URL script rejected', A, 'submit', K, {'assignment_id': task['id'], 'body': 'Texto', 'url': 'javascript:alert(1)'}, '22023')
    deny('teacher cannot submit as student', P, 'submit', K, {'assignment_id': task['id'], 'body': 'Texto'})
    submission = write(A, 'submit', K, {'assignment_id': task['id'], 'body': 'Mi ensayo original', 'url': 'https://example.org/ensayo', 'enrollment_id': EB, 'student_id': B})
    own = item(read(A, 'course', K)['assignments'], task['id'])
    other = item(read(B, 'course', K)['assignments'], task['id'])
    check('student sees own submitted work', own['submission']['body'] == 'Mi ensayo original')
    check('classmate cannot read another student submission', other['submission'] is None)
    check('submitted assignment removed from pending list', task['id'] not in {r['id'] for r in read(A, 'dashboard')['work']})
    late_submission = write(A, 'submit', K, {'assignment_id': late_task['id'], 'body': 'Entrego después de la fecha'})
    check('late submission marked from server clock', item(read(A, 'course', K)['assignments'], late_task['id'])['submission']['late'] is True)
    book = read(P, 'gradebook', K)
    row = next(r for r in book['students'] if r['enrollment_id'] == EA)
    entry = next(r for r in row['grades'] if r['assignment_id'] == task['id'])
    check('teacher can inspect submitted work in own gradebook', entry['body'] == 'Mi ensayo original')
    check('unsaved grade begins revision zero', entry['revision'] == 0 and entry['score'] is None)
    check('participants returns enrolled names only', {r['name'] for r in read(P, 'participants', K)['items']} == {'Alumno Alfa', 'Alumno Beta'})
    paged = read(P, 'gradebook', K, limit=1)
    check('gradebook pagination signals next student', len(paged['students']) == 1 and paged['has_more'] is True)
    check('participants pagination returns second student', read(P, 'participants', K, offset=1, limit=1)['items'][0]['name'] == 'Alumno Beta')

    for score in (-1, 101, 95.999, None, 'NaN', 'Infinity'):
        deny('invalid task score rejected ' + str(score), P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': score, 'revision': 0}, '22023')
    deny('cannot grade enrollment from foreign class', P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EB2, 'score': 95, 'revision': 0})
    deny('cannot grade foreign assignment', P, 'grade_save', K, {'assignment_id': foreign_task['id'], 'enrollment_id': EA, 'score': 95, 'revision': 0})
    deny('cannot publish nonexistent grade', P, 'grade_publish', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'revision': 0}, '22023')
    draft = write(P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': 95.75, 'feedback': 'Borrador de revisión', 'revision': 0})
    student_entry = item(read(A, 'course', K)['assignments'], task['id'])
    check('draft score never exposed to student', student_entry['published_score'] is None and 'score' not in student_entry and 'feedback' not in student_entry)
    deny('student cannot publish own draft', A, 'grade_publish', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'revision': draft['revision']})
    deny('stale save cannot overwrite newer draft', P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': 0, 'revision': 0}, 'PT409')
    published_grade = write(P, 'grade_publish', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'revision': draft['revision']})
    student_entry = item(read(A, 'course', K)['assignments'], task['id'])
    check('published score and feedback visible to own student', student_entry['published_score'] == 95.75 and student_entry['published_feedback'] == 'Borrador de revisión')
    check('classmate never sees someone else published score', item(read(B, 'course', K)['assignments'], task['id'])['published_score'] is None)
    newer_draft = write(P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': 81, 'feedback': 'Nuevo borrador privado', 'revision': published_grade['revision'], 'published_score': 0, 'published_feedback': 'Publicación falsificada'})
    student_entry = item(read(A, 'course', K)['assignments'], task['id'])
    check('new draft leaves previous publication intact', student_entry['published_score'] == 95.75 and student_entry['published_feedback'] == 'Borrador de revisión')
    deny('stale publish cannot expose wrong draft', P, 'grade_publish', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'revision': published_grade['revision']}, 'PT409')
    replacement = write(A, 'submit', K, {'assignment_id': task['id'], 'body': 'Mi ensayo corregido', 'url': ''})
    check('resubmission retains submission identity', replacement['id'] == submission['id'])
    test('resubmission stores previous text in history', 'select body from public.learning_submission_history where submission_id=' + quote(submission['id']), 'Mi ensayo original')
    check('resubmission retains published grade', item(read(A, 'course', K)['assignments'], task['id'])['published_score'] == 95.75)
    unpublish = write(P, 'grade_unpublish', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'revision': newer_draft['revision']})
    check('withdrawn grade no longer visible to student', item(read(A, 'course', K)['assignments'], task['id'])['published_score'] is None)
    republished = write(P, 'grade_publish', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'revision': unpublish['revision']})
    check('republish displays latest saved draft', item(read(A, 'course', K)['assignments'], task['id'])['published_score'] == 81)
    test('task grades never overwrite legacy final grade', actor(A, 'select score from public.enrollment_grades'), '100.00')

    event = write(P, 'event_save', K, {'title': 'Encuentro de Historia', 'body': 'En biblioteca', 'starts_at': FUTURE, 'ends_at': None})
    global_event = write(C, 'event_save', None, {'title': 'Encuentro de comunidad', 'starts_at': FUTURE})
    foreign_event = write(P2, 'event_save', L, {'title': 'Evento Filosofía', 'starts_at': FUTURE})
    check('calendar contains own and institutional events', {r['id'] for r in read(A, 'dashboard')['events']} == {event['id'], global_event['id']})
    check('course calendar excludes other courses', [r['id'] for r in read(A, 'course', K)['events']] == [event['id']])
    for starts, ends in (('infinity', None), (FUTURE, '-infinity'), (FUTURE, PAST), (None, None)):
        deny('invalid calendar date rejected ' + str((starts, ends)), P, 'event_save', K, {'title': 'Evento', 'starts_at': starts, 'ends_at': ends}, '22023')

    # Fresh database authorization after account, class and membership changes.
    for update, restore, who, label in [
        (f"update public.profiles set active=false where id='{A}'", f"update public.profiles set active=true where id='{A}'", A, 'student account'),
        (f"update public.profiles set active=false where id='{P}'", f"update public.profiles set active=true where id='{P}'", P, 'teacher account'),
        (f"update public.enrollments set active=false where id='{EA}'", f"update public.enrollments set active=true where id='{EA}'", A, 'enrollment'),
        (f"update public.teaching_assignments set active=false where id='{TA}'", f"update public.teaching_assignments set active=true where id='{TA}'", P, 'teaching assignment'),
        (f"update public.course_offerings set active=false where id='{K}'", f"update public.course_offerings set active=true where id='{K}'", P, 'class'),
    ]:
        sql(update)
        test('revocation immediately denies course: ' + label, actor(who, rquery('course', K)), error='42501')
        if who == A:
            deny('revocation denies submission: ' + label, A, 'submit', K, {'assignment_id': task['id'], 'body': 'No autorizado'})
        else:
            deny('revocation denies grade change: ' + label, P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': 0, 'revision': republished['revision']})
        sql(restore)
    sql(f"update public.profiles set role='student' where id='{P}'")
    deny('stale professor UI cannot grade after role change', P, 'grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': 0, 'revision': republished['revision']})
    sql(f"update public.profiles set role='professor' where id='{P}'")
    test('audit records authorized learning actions', "select count(*)>20 from public.learning_audit", 't')
    writer = background("set application_name='learning-grade-lock';" + actor(P,
                        wquery('grade_save', K, {'assignment_id': task['id'], 'enrollment_id': EA, 'score': 79, 'revision': republished['revision']})
                        + ';select pg_sleep(1.5)', commit=True))
    wait_sleep('learning-grade-lock')
    deactivate = 'select public.portal_admin_write(\'class_state\',' + quote(json.dumps({'id': K, 'active': False})) + '::jsonb)'
    test('class deactivation waits for in-flight authorized grading', "set lock_timeout='150ms';" + actor(C, deactivate, commit=True), error='55P03')
    disable_person = 'select public.portal_admin_write(\'person_update\',' + quote(json.dumps({'id': A, 'revision': 0, 'full_name': 'Alumno Alfa', 'role': 'student', 'active': False})) + '::jsonb)'
    test('student deactivation waits for in-flight authorized grading', "set lock_timeout='150ms';" + actor(C, disable_person, commit=True), error='55P03')
    writer.wait(timeout=15)
    check('concurrent authorized grade transaction committed', writer.returncode == 0, writer.stderr.read())
    test('failed concurrent class removal rolls back', 'select active from public.course_offerings where id=' + quote(K), 't')

    files_path = ROOT / 'supabase/migrations/20261021090000_learning_files.sql'
    if files_path.exists():
        sql(STORAGE)
        sql(files_path.read_text())
        files_tests(task['id'], closed_task['id'], foreign_task['id'])
    else:
        print('INFO Storage migration not present; file tests not run', flush=True)
    bounds_tests(module['id'])
    print(f'PASS {checks} learning PostgreSQL assertions; no live Supabase writes', flush=True)



def bounds_tests(module_id):
    # Fill each supported course collection up to its actual authoring cap.
    # This exercises large legitimate classes without exposing an unbounded API.
    sql("insert into public.learning_announcements(course_id,author_id,title,body,published,published_at) "
        + "select " + quote(K) + ',' + quote(P) + ", 'Aviso de prueba '||n,'Texto',true,now() from generate_series(1,200-(select count(*)::integer from public.learning_announcements where course_id=" + quote(K) + ')) n')
    check('course announcements bounded to 200', len(read(P, 'course', K)['announcements']) == 200)
    dashboard = read(A, 'dashboard')
    check('dashboard announcements bounded to 50', len(dashboard['announcements']) == 50)
    check('large dashboard never mixes foreign course announcements', all(row['course_id'] in (None, K) for row in dashboard['announcements']))
    deny('authoring more than 200 announcements rejected', P, 'announcement_save', K, {'title': 'Fuera del límite', 'published': True}, '22023')
    sql("insert into public.learning_modules(course_id,title,position,published) select " + quote(K)
        + ", 'Unidad de prueba '||n,100+n,true from generate_series(1,50-(select count(*)::integer from public.learning_modules where course_id=" + quote(K) + ')) n')
    check('course modules bounded to 50', len(read(P, 'course', K)['modules']) == 50)
    deny('authoring more than 50 modules rejected', P, 'module_save', K, {'title': 'Fuera del límite', 'published': True}, '22023')
    sql("insert into public.learning_topics(course_id,module_id,title,position,published) select "
        + quote(K) + ',' + quote(module_id) + ", 'Tema de prueba '||n,100+n,true from generate_series(1,250-(select count(*)::integer from public.learning_topics where course_id=" + quote(K) + ')) n')
    check('course total topics bounded to 250', sum(len(row['topics']) for row in read(P, 'course', K)['modules']) == 250)
    deny('authoring more than 250 topics rejected', P, 'topic_save', K, {'title': 'Fuera del límite', 'module_id': module_id, 'published': True}, '22023')
    sql("insert into public.learning_assignments(course_id,title,published) select " + quote(K)
        + ", 'Tarea de prueba '||n,true from generate_series(1,100-(select count(*)::integer from public.learning_assignments where course_id=" + quote(K) + ')) n')
    check('course assignments bounded to 100', len(read(P, 'course', K)['assignments']) == 100)
    book = read(P, 'gradebook', K)
    check('gradebook assignment columns bounded to 100', len(book['assignments']) == 100)
    assignment_ids = {row['id'] for row in book['assignments']}
    check('gradebook cells match actual assignment columns', all({cell['assignment_id'] for cell in row['grades']} == assignment_ids for row in book['students']))
    deny('authoring more than 100 assignments rejected', P, 'assignment_save', K, {'title': 'Fuera del límite', 'published': True}, '22023')
    sql("insert into public.learning_events(course_id,title,starts_at,created_by) select " + quote(K)
        + ", 'Evento de prueba '||n,now()+interval '2 days'," + quote(P)
        + ' from generate_series(1,200-(select count(*)::integer from public.learning_events where course_id=' + quote(K) + ')) n')
    check('course calendar events bounded to 200', len(read(P, 'course', K)['events']) == 200)
    check('dashboard events bounded to 100', len(read(A, 'dashboard')['events']) == 100)
    deny('authoring more than 200 events rejected', P, 'event_save', K, {'title': 'Fuera del límite', 'starts_at': FUTURE}, '22023')
    page_one = read(C, 'dashboard', limit=1)
    page_two = read(C, 'dashboard', offset=1, limit=1)
    check('dashboard course pagination reports further courses', page_one['has_more_courses'] is True and len(page_one['courses']) == 1)
    check('dashboard course pagination advances without duplication', page_one['courses'][0]['id'] != page_two['courses'][0]['id'] and page_two['has_more_courses'] is False)
    test('all learning operations preserve published final grade', actor(A, 'select score from public.enrollment_grades'), '100.00')


def files_tests(assignment_id, closed_assignment_id, foreign_assignment_id):
    test('private coursework bucket installed', "select not public from storage.buckets where id='portal-coursework'", 't')
    test('coursework bucket enforces 5 MB', "select file_size_limit from storage.buckets where id='portal-coursework'", 5242880)
    test('file records have RLS', "select relrowsecurity from pg_class where oid='public.learning_submission_files'::regclass", 't')
    test('file records are not directly readable', actor(A, 'select * from public.learning_submission_files'), error='42501')
    test('anonymous file RPC denied', actor(None, fq('list', K, assignment_id), role='anon'), error='42501')
    test('null file action rejected', actor(A, fq(None, K, assignment_id)), error='22023')
    file_task = write(P, 'assignment_save', K, {'title': 'Entrega con archivos', 'due_at': FUTURE, 'allow_late': False, 'published': True})['id']
    unsafe_task = write(P, 'assignment_save', K, {'title': 'Validación de archivos', 'due_at': FUTURE, 'allow_late': False, 'published': True})['id']
    first, second, third, fourth = [object_path(file_task, A, number) for number in (1, 2, 3, 4)]
    for index, path in enumerate((first, second, third), 1):
        test('student can upload orphan object ' + str(index), actor(A, upload(path), commit=True), path)
    test('fourth orphan upload blocked by Storage RLS', actor(A, upload(fourth), commit=True), error='42501')
    info = files(A, 'list', K, file_task)
    check('upload widget reflects storage quota including orphans', info['items'] == [] and info['can_upload'] is False)
    third_file = filewrite(A, 'attach', K, file_task, {'object_path': third, 'name': 'archivo3.pdf'})
    info = files(A, 'list', K, file_task)
    check('third preuploaded object can still be registered', len(info['items']) == 1 and info['items'][0]['id'] == third_file['id'])
    own_task = item(read(A, 'course', K)['assignments'], file_task)
    check('file-only attachment creates a real submission', own_task['submission'] is not None and own_task['submission']['body'] == '')
    test('student can download own file', actor(A, object_count(third)), 1)
    test('classmate cannot download file from same course', actor(B, object_count(third)), 0)
    test('unassigned professor cannot download private file', actor(P2, object_count(third)), 0)
    test('assigned professor reads registered file', actor(P, object_count(third)), 1)
    test('assigned professor cannot read unsubmitted orphan', actor(P, object_count(first)), 0)
    test('control can read registered coursework', actor(C, object_count(third)), 1)
    test('student cannot list another enrollment files', actor(B, fq('list', K, file_task, {'enrollment_id': EA})), error='42501')
    check('teacher file list uses authorized enrollment', files(P, 'list', K, file_task, {'enrollment_id': EA})['items'][0]['name'] == 'archivo3.pdf')
    test('teacher cannot use enrollment from another course', actor(P, fq('list', K, file_task, {'enrollment_id': EB2})), error='42501')
    test('foreign task cannot be read by spoofing course', actor(A, fq('list', K, foreign_assignment_id)), error='42501')
    test('teacher cannot attach on behalf of student', actor(P, fq('attach', K, file_task, {'object_path': third, 'name': 'archivo3.pdf'}), commit=True), error='42501')
    test('classmate cannot attach someone else object', actor(B, fq('attach', K, file_task, {'object_path': third, 'name': 'archivo3.pdf'}), commit=True), error='42501')
    first_file = filewrite(A, 'attach', K, file_task, {'object_path': first, 'name': 'archivo1.pdf'})
    second_file = filewrite(A, 'attach', K, file_task, {'object_path': second, 'name': 'archivo2.pdf'})
    check('maximum three attached files returned', len(files(A, 'list', K, file_task)['items']) == 3)
    test('registered object cannot be deleted behind attachment record', actor(A, delete_object(third), commit=True), 0)
    test('registered object remains after forbidden deletion', actor(A, object_count(third)), 1)
    test('foreign user cannot remove file metadata', actor(B, fq('remove', K, file_task, {'id': third_file['id']}), commit=True), error='42501')
    filewrite(A, 'remove', K, file_task, {'id': first_file['id']})
    test('removed attachment object can be cleaned from storage', actor(A, delete_object(first), commit=True), 1)
    filewrite(A, 'remove', K, file_task, {'id': second_file['id']})
    test('cleanup second removed attachment', actor(A, delete_object(second), commit=True), 1)
    test('last file cannot leave an empty submission', actor(A, fq('remove', K, file_task, {'id': third_file['id']}), commit=True), error='22023')
    check('failed last-file removal retains attachment', len(files(A, 'list', K, file_task)['items']) == 1)
    write(A, 'submit', K, {'assignment_id': file_task, 'body': 'Entrega conservada como texto', 'url': ''})
    filewrite(A, 'remove', K, file_task, {'id': third_file['id']})
    test('last file may be cleaned when text submission remains', actor(A, delete_object(third), commit=True), 1)
    check('text remains after removing files', item(read(A, 'course', K)['assignments'], file_task)['submission']['body'] == 'Entrega conservada como texto')

    missing = object_path(unsafe_task, A, 10)
    test('cannot register nonexistent uploaded object', actor(A, fq('attach', K, unsafe_task, {'object_path': missing, 'name': 'archivo10.pdf'}), commit=True), error='22023')
    test('cannot forge object ownership on upload', actor(A, upload(missing, owner=B), commit=True), error='42501')
    for label, badpath in [
        ('foreign owner folder', object_path(unsafe_task, B, 10)),
        ('foreign course', object_path(foreign_assignment_id, A, 10, course=L)),
        ('foreign assignment under authorized course', object_path(foreign_assignment_id, A, 10)),
        ('bad random directory', K + '/' + unsafe_task + '/' + A + '/not-a-uuid/file.pdf'),
        ('nested filename', K + '/' + unsafe_task + '/' + A + '/' + uid(999) + '/nested/file.pdf'),
        ('executable extension', object_path(unsafe_task, A, 10).replace('.pdf', '.exe')),
    ]:
        test('Storage rejects ' + label, actor(A, upload(badpath), commit=True), error='42501')
    for number, size, mime, label in [(11, 0, 'application/pdf', 'empty file'),
                                    (12, 5242881, 'application/pdf', 'oversized file'),
                                    (13, 100, 'text/html', 'mismatched MIME'),
                                    (14, 'not-a-size', 'application/pdf', 'invalid size metadata')]:
        path = object_path(unsafe_task, A, number)
        # Storage normally validates this at upload; corrupted fixture metadata
        # verifies that final attachment registration validates it independently.
        test('prepare metadata fixture ' + label, actor(A, upload(path, size=size, mime=mime), commit=True), path)
        test('attachment rejects ' + label, actor(A, fq('attach', K, unsafe_task, {'object_path': path, 'name': f'archivo{number}.pdf'}), commit=True), error='22023')
        test('failed attachment can clean upload ' + label, actor(A, delete_object(path), commit=True), 1)
    good_path = object_path(unsafe_task, A, 15)
    test('prepare filename validation fixture', actor(A, upload(good_path), commit=True), good_path)
    for name in ('../secreto.pdf', 'archivo15.docx', 'nombre\\invalido.pdf', 'nombre\ncontrol.pdf'):
        test('invalid or inconsistent original filename rejected ' + repr(name), actor(A, fq('attach', K, unsafe_task, {'object_path': good_path, 'name': name}), commit=True), error='22023')
    test('student cannot rewrite server object metadata', actor(A, "update storage.objects set metadata='{}' where name=" + quote(good_path), commit=True), error='42501')
    valid_file = filewrite(A, 'attach', K, unsafe_task, {'object_path': good_path, 'name': 'archivo15.pdf'})
    test('registered file cannot be attached twice', actor(A, fq('attach', K, unsafe_task, {'object_path': good_path, 'name': 'archivo15.pdf'}), commit=True), error='PT409')

    for update, restore, who, label in [
        (f"update public.profiles set active=false where id='{A}'", f"update public.profiles set active=true where id='{A}'", A, 'student profile'),
        (f"update public.enrollments set active=false where id='{EA}'", f"update public.enrollments set active=true where id='{EA}'", A, 'student enrollment'),
        (f"update public.teaching_assignments set active=false where id='{TA}'", f"update public.teaching_assignments set active=true where id='{TA}'", P, 'teacher assignment'),
        (f"update public.course_offerings set active=false where id='{K}'", f"update public.course_offerings set active=true where id='{K}'", A, 'class'),
    ]:
        sql(update)
        test('file RPC respects revoked ' + label, actor(who, fq('list', K, unsafe_task, {'enrollment_id': EA} if who == P else {})), error='42501')
        test('Storage download respects revoked ' + label, actor(who, object_count(good_path)), 0)
        sql(restore)

    write(P, 'assignment_save', K, {'id': unsafe_task, 'title': 'Validación cerrada', 'due_at': PAST, 'allow_late': False, 'published': True, 'revision': 1})
    check('closed deadline disables file editing', files(A, 'list', K, unsafe_task)['can_upload'] is False and files(A, 'list', K, unsafe_task)['can_remove'] is False)
    test('closed deadline denies new uploads', actor(A, upload(object_path(unsafe_task, A, 16)), commit=True), error='42501')
    test('closed deadline denies attachment metadata removal', actor(A, fq('remove', K, unsafe_task, {'id': valid_file['id']}), commit=True), error='22023')
    test('closed task retains readable submitted coursework', actor(A, object_count(good_path)), 1)

    # A transaction that started while open must recheck the wall clock after
    # waiting for the authorization lock, rather than use transaction-start now().
    near_deadline = (datetime.now(timezone.utc) + timedelta(seconds=.8)).isoformat()
    near_task = write(P, 'assignment_save', K, {'title': 'Cierre durante espera', 'due_at': near_deadline, 'allow_late': False, 'published': True})['id']
    blocker = background("set application_name='learning-file-deadline';begin;select pg_advisory_xact_lock(72643219);select pg_sleep(1.5);commit;")
    wait_sleep('learning-file-deadline')
    test('upload waiting on lock observes elapsed real deadline', actor(A, upload(object_path(near_task, A, 17)), commit=True), error='42501')
    blocker.wait(timeout=15)
    check('deadline blocker released normally', blocker.returncode == 0, blocker.stderr.read())
    test('no direct file record mutation privilege', "select has_table_privilege('authenticated','public.learning_submission_files','SELECT,INSERT,UPDATE,DELETE')", 'f')


def fq(action, course, assignment, data=None):
    return 'select public.portal_learning_files(' + ','.join([quote(action), quote(course), quote(assignment), quote(json.dumps(data or {})) + '::jsonb']) + ')'


def files(who, action, course, assignment, data=None):
    return json.loads(sql(actor(who, fq(action, course, assignment, data))).stdout)


def filewrite(who, action, course, assignment, data):
    result = json.loads(sql(actor(who, fq(action, course, assignment, data), commit=True)).stdout)
    check('file ' + action, result.get('saved') is True and bool(result.get('id')), result)
    return result


def object_path(assignment, who, number, course=K):
    return '/'.join([course, assignment, who, uid(1000 + number), f'archivo{number}.pdf'])


def upload(path, *, owner=A, size=100, mime='application/pdf'):
    metadata = {'size': size, 'mimetype': mime}
    return "insert into storage.objects(bucket_id,name,owner_id,metadata) values('portal-coursework'," + quote(path) + ',' + quote(owner) + ',' + quote(json.dumps(metadata)) + '::jsonb) returning name'


def object_count(path):
    return "select count(*) from storage.objects where bucket_id='portal-coursework' and name=" + quote(path)


def delete_object(path):
    return "with removed as (delete from storage.objects where bucket_id='portal-coursework' and name=" + quote(path) + ' returning id) select count(*) from removed'



if __name__ == '__main__':
    try:
        main()
    finally:
        run('docker', 'rm', '-f', NAME, check=False)
