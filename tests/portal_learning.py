"""Aula virtual: browser integration with the real pinned SDK and simulated API.

Run: python tests/portal_learning.py. Uses no live Supabase, email or student data.
PORTAL_TEST_ARTIFACTS keeps screenshots; otherwise all artifacts are temporary.
"""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect
import portal_subjects as h

COURSE = 'a1000000-0000-4000-8000-000000000001'
OTHER = 'a1000000-0000-4000-8000-000000000002'
ASSIGNMENT = 'a2000000-0000-4000-8000-000000000001'
SECOND_TASK = 'a2000000-0000-4000-8000-000000000002'
MODULE = 'a3000000-0000-4000-8000-000000000001'
TOPIC = 'a4000000-0000-4000-8000-000000000001'
ENROLLMENT = 'a5000000-0000-4000-8000-000000000001'
SUBMISSION = 'a6000000-0000-4000-8000-000000000001'
ANNOUNCEMENT = 'a7000000-0000-4000-8000-000000000001'
EVENT = 'a8000000-0000-4000-8000-000000000001'
checks = 0
OUT = None


def timestamp(days=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()


def sample_data(role):
    courses = []
    for i, (uid, name) in enumerate([(COURSE, 'Cristología'), (OTHER, 'Historia de la Iglesia')], 1):
        courses.append({'id': uid, 'subject_id': f'b1000000-0000-4000-8000-{i:012d}',
                        'period_id': 'b2000000-0000-4000-8000-000000000001',
                        'code': f'MAT-{i:03d}', 'name': name,
                        'period_name': 'Periodo de prueba 2026', 'starts_on': '2026-08-01',
                        'ends_on': '2026-12-18', 'role': role, 'final_score': 100 if role == 'student' else None})
    announcement = {'id': ANNOUNCEMENT, 'course_id': COURSE, 'course_name': 'Cristología',
                    'title': 'Bienvenidos al nuevo periodo', 'body': 'La primera sesión será en el aula de formación.',
                    'pinned': True, 'published': True, 'published_at': timestamp(-1), 'revision': 1}
    assignment = {'id': ASSIGNMENT, 'title': 'Reflexión sobre el Evangelio',
                  'instructions': 'Escribe una reflexión y relaciona la lectura con la clase.',
                  'due_at': timestamp(7), 'allow_late': True, 'published': True, 'revision': 1,
                  'submission': None, 'published_score': 100, 'published_feedback': 'Buen trabajo de prueba.',
                  'published_at': timestamp(-1)}
    second = {**copy.deepcopy(assignment), 'id': SECOND_TASK, 'title': 'Lectura del capítulo segundo',
              'due_at': timestamp(14), 'published_score': None, 'published_feedback': None, 'published_at': None}
    event = {'id': EVENT, 'course_id': COURSE, 'course_name': 'Cristología', 'title': 'Sesión de repaso',
             'body': 'Repasaremos los temas de la unidad.', 'starts_at': timestamp(), 'ends_at': timestamp(), 'revision': 1}
    course = {'course': {**courses[0], 'syllabus': 'Programa de formación: lectura, diálogo y reflexión.'},
              'can_manage': role in ('professor', 'control_escolar'),
              'announcements': [announcement], 'assignments': [assignment, second], 'events': [event],
              'modules': [{'id': MODULE, 'title': 'Introducción y materiales', 'position': 1,
                           'published': True, 'revision': 1,
                           'topics': [{'id': TOPIC, 'title': 'Presentación del curso',
                                       'body': 'Conoce el programa y prepara tu primera lectura.',
                                       'url': 'https://example.org/lectura', 'position': 1,
                                       'published': True, 'completed': False, 'revision': 1}]}]}
    grade = {'assignment_id': ASSIGNMENT, 'submission_id': SUBMISSION,
             'body': 'Reflexión de prueba entregada.', 'url': 'https://example.org/trabajo',
             'submitted_at': timestamp(-2), 'score': 82, 'feedback': 'Borrador privado del profesor.',
             'published_score': 100, 'published_feedback': 'Buen trabajo de prueba.',
             'published_at': timestamp(-1), 'revision': 2}
    empty_grade = {**copy.deepcopy(grade), 'assignment_id': SECOND_TASK, 'submission_id': None,
                   'body': None, 'url': None, 'submitted_at': None, 'score': None,
                   'feedback': '', 'published_score': None, 'published_feedback': None,
                   'published_at': None, 'revision': 0}
    return {'courses': courses, 'course': course,
            'gradebook': {'assignments': [{'id': a['id'], 'title': a['title'], 'due_at': a['due_at']} for a in [assignment, second]],
                          'students': [{'enrollment_id': ENROLLMENT, 'student_id': h.UID,
                                        'name': 'Seminarista de prueba', 'final_score': 100,
                                        'grades': [grade, empty_grade]}], 'has_more': False},
            'institutional_announcements': [], 'calls': [], 'writes': [], 'errors': [], 'read_status': {}, 'write_status': 200,
            'read_gate': None, 'read_started': asyncio.Event(), 'write_gate': None,
            'write_started': asyncio.Event(), 'overrides': {}, 'files': [], 'file_calls': []}


async def fixture(browser, role='student', *, mobile=False, route='inicio', data=None):
    profile = {'full_name': {'student': 'Seminarista de prueba', 'professor': 'Pbro. Profesor de prueba',
                            'control_escolar': 'Control Escolar de prueba'}[role], 'role': role, 'active': True}
    rows = [h.subject(1, name='Cristología'), h.subject(2, name='Historia de la Iglesia')]
    context, page, state = await h.fixture(browser, session=False, profile=profile, rows=rows,
                                          teaching=rows if role == 'professor' else [],
                                          grades=[{'enrollment_id': rows[0]['id'], 'score': 100}],
                                          start='index.html', mobile=mobile)
    data = data or sample_data(role)
    headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*',
               'Access-Control-Allow-Methods': 'POST,GET,OPTIONS', 'Content-Type': 'application/json'}

    async def api_route(route):
        request = route.request
        path = urlparse(request.url).path
        if not ('portal_learning_' in path or 'portal_content_files' in path or '/storage/v1/' in path):
            return await route.fallback()
        if request.method == 'OPTIONS':
            return await route.fulfill(status=204, headers=headers)
        try:
            if '/storage/v1/' in path:
                data['file_calls'].append((request.method, path))
                if request.method == 'GET':
                    return await route.fulfill(status=200, headers={**headers, 'Content-Type': 'application/pdf'}, body=b'%PDF-1.4\nFixture coursework\n')
                if request.method == 'POST':
                    object_path = path.split('/portal-coursework/', 1)[1]
                    assert object_path.startswith(f'{COURSE}/{ASSIGNMENT}/{h.UID}/'), object_path
                    data['uploaded_path'] = object_path
                    return await route.fulfill(status=200, headers=headers, body=json.dumps({'Key': 'portal-coursework/' + object_path, 'Id': SUBMISSION}))
                if request.method == 'DELETE':
                    return await route.fulfill(status=200, headers=headers, body='[]')
                raise AssertionError('Unexpected Storage request ' + request.method)
            args = request.post_data_json if request.method == 'POST' else {}
            if path.endswith('/portal_content_files'):
                assert args['p_action']=='list', args
                topic=next(t for m in data['course']['modules'] for t in m['topics'] if t['id']==args['p_topic'])
                return await route.fulfill(status=200,headers=headers,body=json.dumps({'items':topic.get('files',[]),'pending':[],'can_manage':state['profile']['role']!='student'}))
            if path.endswith('/portal_learning_read'):
                resource = args['p_resource']
                data['calls'].append(copy.deepcopy(args)); data['read_started'].set()
                if data['read_gate']:
                    await data['read_gate'].wait()
                status = data['read_status'].get(resource, 200)
                if status != 200:
                    return await route.fulfill(status=status, headers=headers, body=json.dumps({
                        'code': '42501' if status == 403 else 'PGRST202' if status == 404 else 'XX000',
                        'message': 'Respuesta simulada del aula'}))
                if resource in data['overrides']:
                    result = copy.deepcopy(data['overrides'][resource])
                elif resource == 'dashboard':
                    result = {'courses': copy.deepcopy(data['courses']),
                              'announcements': copy.deepcopy(data['course']['announcements']),
                              'work': [{'id': a['id'], 'course_id': COURSE, 'course_name': 'Cristología',
                                        'title': a['title'], 'due_at': a['due_at'],
                                        'status': 'submitted' if a['submission'] else 'pending',
                                        'submitted_at': a['submission']['submitted_at'] if a['submission'] else None}
                                       for a in data['course']['assignments']],
                              'events': copy.deepcopy(data['course']['events']), 'has_more_courses': False,
                              'institutional_announcements': copy.deepcopy(data['institutional_announcements'])}
                elif resource == 'course':
                    assert args.get('p_course') in [COURSE, OTHER], args
                    result = copy.deepcopy(data['course'])
                    if args['p_course'] == OTHER:
                        result['course'].update(data['courses'][1])
                    if state['profile']['role'] == 'student':
                        result['can_manage'] = False
                        result['course']['role'] = 'student'
                        result['announcements'] = [a for a in result['announcements'] if a['published']]
                        result['assignments'] = [a for a in result['assignments'] if a['published']]
                        result['modules'] = [m for m in result['modules'] if m['published']]
                        for module in result['modules']:
                            module['topics'] = [t for t in module['topics'] if t['published']]
                elif resource == 'gradebook':
                    assert state['profile']['role'] in ['professor', 'control_escolar'], args
                    result = copy.deepcopy(data['gradebook'])
                elif resource == 'participants':
                    assert state['profile']['role'] in ['professor', 'control_escolar'], args
                    result = {'items': [{'enrollment_id': ENROLLMENT, 'name': 'Seminarista de prueba'}], 'has_more': False}
                else:
                    raise AssertionError('Unknown learning resource: ' + resource)
                return await route.fulfill(status=200, headers=headers, body=json.dumps(result))
            if path.endswith('/portal_learning_write'):
                data['writes'].append(copy.deepcopy(args)); data['write_started'].set()
                if data['write_gate']:
                    await data['write_gate'].wait()
                status = data['write_status']
                if status != 200:
                    return await route.fulfill(status=status, headers=headers, body=json.dumps({
                        'code': 'PT409' if status == 409 else '42501' if status == 403 else 'XX000',
                        'message': 'Respuesta simulada de escritura'}))
                assert args.get('p_course') in [COURSE, OTHER, None], args
                action, body = args['p_action'], args['p_data']
                record_id = body.get('id') or f'c1000000-0000-4000-8000-{len(data["writes"]):012d}'
                if action in ['announcement_save', 'module_save', 'assignment_save', 'event_save']:
                    key = {'announcement_save': 'announcements', 'module_save': 'modules',
                           'assignment_save': 'assignments', 'event_save': 'events'}[action]
                    records = data['institutional_announcements'] if action == 'announcement_save' and args.get('p_course') is None else data['course'][key]
                    record = next((row for row in records if row['id'] == record_id), None)
                    if record is None:
                        record = {'id': record_id, 'revision': 0}
                        if key == 'modules': record['topics'] = []
                        if key == 'assignments':
                            record.update(submission=None, published_score=None, published_feedback=None, published_at=None)
                        records.append(record)
                    record.update(copy.deepcopy(body)); record['revision'] += 1
                    if action == 'announcement_save': record.update(published_at=timestamp() if body.get('published') else None, course_id=args.get('p_course'), course_name='Cristología' if args.get('p_course') else None)
                    if action == 'event_save': record.update(course_id=COURSE, course_name='Cristología')
                elif action == 'topic_save':
                    module = next(m for m in data['course']['modules'] if m['id'] == body['module_id'])
                    topic = next((t for t in module['topics'] if t['id'] == record_id), None)
                    if topic is None:
                        topic = {'id': record_id, 'revision': 0, 'completed': False}; module['topics'].append(topic)
                    topic.update(copy.deepcopy(body)); topic['revision'] += 1
                elif action == 'topic_complete':
                    topic = next(t for m in data['course']['modules'] for t in m['topics'] if t['id'] == body['topic_id'])
                    topic['completed'] = body['completed']; record_id = topic['id']
                elif action == 'syllabus_save':
                    data['course']['course']['syllabus'] = body['body']; record_id = COURSE
                elif action == 'submit':
                    task = next(a for a in data['course']['assignments'] if a['id'] == body['assignment_id'])
                    task['submission'] = {'id': SUBMISSION, 'body': body['body'], 'url': body['url'],
                                          'submitted_at': timestamp(), 'late': False}; record_id = SUBMISSION
                elif action in ['grade_save', 'grade_publish', 'grade_unpublish']:
                    student = next(s for s in data['gradebook']['students'] if s['enrollment_id'] == body['enrollment_id'])
                    grade = next(g for g in student['grades'] if g['assignment_id'] == body['assignment_id'])
                    assert body['revision'] == grade['revision'], (body, grade)
                    if action == 'grade_save':
                        assert 0 <= body['score'] <= 100, body
                        grade.update(score=body['score'], feedback=body.get('feedback', ''))
                    elif action == 'grade_publish':
                        grade.update(published_score=grade['score'], published_feedback=grade['feedback'], published_at=timestamp())
                    else:
                        grade.update(published_score=None, published_feedback=None, published_at=None)
                    grade['revision'] += 1; record_id = body['assignment_id']
                    task = next(a for a in data['course']['assignments'] if a['id'] == body['assignment_id'])
                    task.update(published_score=grade['published_score'], published_feedback=grade['published_feedback'], published_at=grade['published_at'])
                else:
                    raise AssertionError('Unknown learning action: ' + action)
                return await route.fulfill(status=200, headers=headers, body=json.dumps({'id': record_id, 'saved': True,
                                            'revision': grade['revision'] if action.startswith('grade_') else 1}))
            if path.endswith('/portal_learning_files'):
                data['file_calls'].append((args['p_action'], copy.deepcopy(args)))
                action = args['p_action']
                if action == 'list':
                    return await route.fulfill(status=200, headers=headers, body=json.dumps({'items': data['files'], 'can_upload': state['profile']['role'] == 'student', 'can_remove': state['profile']['role'] == 'student'}))
                if action == 'attach':
                    body = args['p_data']; assert body['object_path'] == data['uploaded_path']
                    data['files'].append({'id': 'a9000000-0000-4000-8000-000000000001', 'name': body['name'], 'size': 27, 'mimetype': 'application/pdf', 'created_at': timestamp(), 'object_path': body['object_path']})
                    task = next(a for a in data['course']['assignments'] if a['id'] == args['p_assignment'])
                    task['submission'] = task['submission'] or {'id': SUBMISSION, 'body': '', 'url': '', 'submitted_at': timestamp(), 'late': False}
                    return await route.fulfill(status=200, headers=headers, body=json.dumps({'id': data['files'][-1]['id'], 'saved': True}))
                if action == 'remove':
                    data['files'] = [f for f in data['files'] if f['id'] != args['p_data']['id']]
                    return await route.fulfill(status=200, headers=headers, body=json.dumps({'saved': True}))
                raise AssertionError('Unknown file action: ' + action)
            raise AssertionError('Unexpected learning request: ' + path)
        except Exception as exc:
            if isinstance(exc, AssertionError): data['errors'].append(str(exc))
            elif 'Target page, context or browser has been closed' not in str(exc): data['errors'].append(str(exc))
            try: await route.abort()
            except Exception: pass

    await context.route(h.API + '/**', api_route)
    await page.evaluate('(session)=>localStorage.setItem("seminario-mr-auth",JSON.stringify(session))', h.SESSION)
    await page.goto(h.BASE + '/portal/panel.html#' + route, wait_until='domcontentloaded')
    return context, page, state, data


async def done(context, state, data, label):
    global checks
    assert not state['errors'], state['errors']
    assert not state['route_errors'], state['route_errors']
    assert not data['errors'], data['errors']
    checks += 1
    print('PASS ' + label, flush=True)
    await context.close()


async def nav(page, tab):
    await page.evaluate('(route)=>location.hash=route', f'curso/{COURSE}/{tab}')
    await expect(page.locator('#learningCourseTitle')).to_have_text('Cristología')


async def field(page, name, value):
    await page.locator('#learning-field-' + name).fill(value)


async def save_dialog(page):
    await page.locator('#learningSave').click()
    await expect(page.locator('#learningDialog')).not_to_be_visible()


async def screenshot(page, name):
    await page.evaluate("document.activeElement?.blur(); window.scrollTo({top:0,behavior:'instant'});")
    await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    await page.screenshot(path=str(OUT / name), full_page=True, animations='disabled')


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=shutil.which('chromium'), headless=True)
        # The UI is implemented concurrently; each assertion checks rendered behavior, not source text.
        context, page, state, data = await fixture(browser)
        await expect(page.locator('#learningAnnouncements')).to_contain_text('Bienvenidos al nuevo periodo')
        await expect(page.locator('#learningWork')).to_contain_text('Reflexión sobre el Evangelio')
        await expect(page.locator('#learningCalendar')).to_contain_text('Calendario')
        await page.locator('#learningCalendar .has-events').first.click()
        await expect(page.locator('#learningDialog')).to_contain_text('Sesión de repaso')
        await page.keyboard.press('Escape')
        assert any(c['p_resource'] == 'dashboard' for c in data['calls'])
        await screenshot(page, 'seminario-aula-inicio.png')
        await page.locator('#subjectsList').get_by_role('button', name=re.compile('Entrar al curso')).first.click()
        await expect(page).to_have_url(re.compile(r'#curso/' + COURSE))
        await expect(page.locator('#learningCourseTitle')).to_have_text('Cristología')
        await screenshot(page, 'seminario-aula-curso-alumno.png')
        await done(context, state, data, 'Home shows real announcements, due work and calendar; student enters the selected course')

        context, page, state, data = await fixture(browser, route=f'curso/{COURSE}/contenido')
        await expect(page.locator('#learningContent')).to_contain_text('Presentación del curso')
        await page.locator('#learningContent summary').first.click()
        await page.locator('#learningContent').get_by_role('checkbox').first.check()
        await data['write_started'].wait()
        await expect(page.locator('#learningContent').get_by_role('checkbox').first).to_be_checked()
        assert any(w['p_action'] == 'topic_complete' for w in data['writes'])
        await done(context, state, data, 'Student marks only their own topic progress')

        context, page, state, data = await fixture(browser, route=f'curso/{COURSE}/tareas/{ASSIGNMENT}')
        await expect(page.locator('#learningContent')).to_contain_text('Reflexión sobre el Evangelio')
        await page.get_by_role('button', name='Entregar tarea', exact=True).click()
        await field(page, 'body', 'Mi reflexión de prueba sobre la lectura del curso.')
        await field(page, 'url', 'https://example.org/mi-reflexion')
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Mi reflexión de prueba sobre la lectura del curso.')
        assert data['writes'][-1]['p_action'] == 'submit'
        await done(context, state, data, 'Student submits a text response and valid link for the selected assignment')

        context, page, state, data = await fixture(browser, route=f'curso/{COURSE}/mis-notas')
        await expect(page.locator('#learningContent')).to_contain_text('100')
        await expect(page.locator('#learningContent')).to_contain_text('Buen trabajo de prueba.')
        await expect(page.locator('#learningContent')).not_to_contain_text('Borrador privado del profesor.')
        assert await page.locator('#learningContent input[type=number]').count() == 0
        assert await page.locator('#learningCourseNav').get_by_role('link', name='Calificaciones', exact=True).count() == 0
        await nav(page, 'calificaciones')
        assert not any(c['p_resource'] == 'gradebook' for c in data['calls'])
        await done(context, state, data, 'Student reads their published grades but never sees staff gradebook or draft feedback')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/anuncios')
        await page.get_by_role('button', name='Nuevo anuncio', exact=True).click()
        await field(page, 'title', 'Anuncio creado desde el aula')
        await field(page, 'body', 'El martes revisaremos las reflexiones en clase.')
        await page.locator('#learning-field-published').check()
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Anuncio creado desde el aula')
        assert data['writes'][-1]['p_course'] == COURSE
        await done(context, state, data, 'Assigned professor publishes a course announcement')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/contenido')
        await page.get_by_role('button', name='Nueva unidad', exact=True).click()
        await field(page, 'title', 'Unidad de estudio nueva')
        await page.locator('#learning-field-published').check()
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Unidad de estudio nueva')
        await page.get_by_role('button', name='Agregar contenido', exact=True).first.click()
        await field(page, 'title', 'Lectura complementaria')
        await field(page, 'body', 'Material preparado para la siguiente sesión.')
        await field(page, 'url', 'https://example.org/lectura-complementaria')
        await page.locator('#learning-field-published').check()
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Lectura complementaria')
        await done(context, state, data, 'Professor creates a published module and topic linked to the correct course')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/tareas')
        await page.get_by_role('button', name='Nueva tarea', exact=True).click()
        await field(page, 'title', 'Trabajo de síntesis')
        await field(page, 'instructions', 'Redacta una síntesis con tus conclusiones.')
        await field(page, 'due_at', (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%dT%H:%M'))
        await page.locator('#learning-field-published').check()
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Trabajo de síntesis')
        assert data['writes'][-1]['p_data']['due_at']
        await done(context, state, data, 'Professor creates a real assignment with a deadline')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/calendario')
        await page.get_by_role('button', name='Nuevo evento', exact=True).click()
        await field(page, 'title', 'Encuentro de formación')
        await field(page, 'body', 'Revisión conjunta de los materiales.')
        await field(page, 'starts_at', (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'))
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Encuentro de formación')
        await done(context, state, data, 'Professor creates an event shown in the course calendar')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/programa')
        await page.get_by_role('button', name='Editar programa', exact=True).click()
        await field(page, 'body', 'Programa actualizado por el profesor del curso.')
        await save_dialog(page)
        await expect(page.locator('#learningContent')).to_contain_text('Programa actualizado por el profesor del curso.')
        await done(context, state, data, 'Professor edits the syllabus from the course workspace')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/calificaciones')
        await expect(page.locator('#learningGradebook')).to_contain_text('Seminarista de prueba')
        score = page.locator(f'#learningGradebook input[data-enrollment="{ENROLLMENT}"][data-assignment="{ASSIGNMENT}"]')
        await score.fill('95')
        await page.get_by_role('button', name='Guardar borradores', exact=True).click()
        await expect(page.locator('#learningStatus')).to_contain_text(re.compile('guardad', re.I))
        first = data['gradebook']['students'][0]['grades'][0]
        assert first['score'] == 95 and first['published_score'] == 100
        await page.get_by_role('button', name='Publicar calificaciones', exact=True).click()
        await expect(page.locator('#learningStatus')).to_contain_text(re.compile('publicad', re.I))
        assert first['published_score'] == 95
        assert any(w['p_action'] == 'grade_save' for w in data['writes'])
        assert any(w['p_action'] == 'grade_publish' for w in data['writes'])
        await screenshot(page, 'seminario-aula-calificaciones.png')
        await done(context, state, data, 'Teacher gradebook saves drafts separately then publishes score snapshots')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/calificaciones')
        await expect(page.locator('#learningGradebook')).to_be_visible()
        data['write_status'] = 409
        score = page.locator(f'#learningGradebook input[data-enrollment="{ENROLLMENT}"][data-assignment="{ASSIGNMENT}"]')
        await score.fill('90')
        await page.get_by_role('button', name='Guardar borradores', exact=True).click()
        await expect(page.locator('#learningStatus')).to_contain_text(re.compile('cambi|actualiz|conflic', re.I))
        assert data['gradebook']['students'][0]['grades'][0]['score'] == 82
        await done(context, state, data, 'Optimistic grade conflict is reported without overwriting another revision')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/participantes')
        await expect(page.locator('#learningContent')).to_contain_text('Seminarista de prueba')
        await done(context, state, data, 'Assigned professor can read the participant list')

        injected = sample_data('student')
        injected['course']['announcements'][0]['title'] = '<img src=x onerror="window.fixtureAttack=true">'
        injected['course']['modules'][0]['topics'][0]['url'] = 'javascript:window.fixtureAttack=true'
        context, page, state, data = await fixture(browser, route=f'curso/{COURSE}/contenido', data=injected)
        await expect(page.locator('#learningContent')).to_contain_text('Presentación del curso')
        assert await page.locator('#learningContent a[href^="javascript:"]').count() == 0
        await nav(page, 'anuncios')
        await expect(page.locator('#learningContent')).to_contain_text('<img src=x')
        assert not await page.evaluate('Boolean(window.fixtureAttack)')
        await done(context, state, data, 'Course text stays literal and unsafe external URL schemes are not rendered')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/anuncios')
        await expect(page.locator('#learningContent')).to_contain_text('Bienvenidos al nuevo periodo')
        state['profile'] = {**state['profile'], 'active': False}
        data['read_status']['course'] = 403
        await page.get_by_role('button', name='Actualizar curso', exact=True).click()
        await expect(page).to_have_url(re.compile('index.html'))
        assert await page.locator('#learningContent').count() == 0
        await done(context, state, data, 'Database access revocation clears the course and returns to authentication')

        missing = sample_data('student'); missing['read_status']['dashboard'] = 404
        context, page, state, data = await fixture(browser, data=missing)
        await expect(page.locator('#learningAnnouncements')).to_contain_text(re.compile('instal|configur|disponible|prepar', re.I))
        await expect(page.locator('#subjectsList')).to_contain_text('Cristología')
        await done(context, state, data, 'Uninstalled learning migration reports setup issue while existing course cards still work')

        context, page, state, data = await fixture(browser, role='professor', route=f'curso/{COURSE}/anuncios')
        await expect(page.locator('#learningContent')).to_contain_text('Bienvenidos al nuevo periodo')
        data['read_gate'] = asyncio.Event(); data['read_started'].clear()
        await page.get_by_role('button', name='Actualizar curso', exact=True).click()
        await data['read_started'].wait()
        await page.locator('#logoutButton').click()
        data['read_gate'].set()
        await expect(page).to_have_url(re.compile('index.html'))
        assert await page.locator('#learningContent').count() == 0
        await done(context, state, data, 'Signout clears course content and late reads cannot restore private data')

        context, page, state, data = await fixture(browser, mobile=True)
        await expect(page.locator('#learningWork')).to_contain_text('Reflexión sobre el Evangelio')
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await screenshot(page, 'seminario-aula-movil-inicio.png')
        await nav(page, 'tareas/' + ASSIGNMENT)
        await page.get_by_role('button', name='Entregar tarea', exact=True).click()
        await expect(page.locator('#learningDialog')).to_be_visible()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert await page.locator('#learningDialog').evaluate('(d)=>d.contains(document.activeElement)')
        await page.keyboard.press('Escape')
        await expect(page.locator('#learningDialog')).not_to_be_visible()
        await expect(page.locator('.learning-files h4')).to_have_text('Archivos de la entrega')
        await screenshot(page, 'seminario-aula-movil-curso.png')
        await done(context, state, data, 'Mobile home, course and assignment dialog fit the screen with focus and Escape support')

        context, page, state, data = await fixture(browser, route=f'curso/{COURSE}/tareas/{ASSIGNMENT}')
        await expect(page.locator('.learning-file-upload')).to_be_visible()
        await page.locator('.learning-files input[type=file]').set_input_files({'name': 'reflexion.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4\nFixture coursework\n'})
        await page.get_by_role('button', name='Subir y entregar archivo', exact=True).click()
        await expect(page.locator('.learning-file-list')).to_contain_text('reflexion.pdf')
        assert any(call[0] == 'attach' for call in data['file_calls'])
        async with page.expect_download() as pending:
            await page.locator('.learning-file-list').get_by_role('button', name='Descargar', exact=True).click()
        download = await pending.value
        assert download.suggested_filename == 'reflexion.pdf'
        assert Path(await download.path()).read_bytes() == b'%PDF-1.4\nFixture coursework\n'
        assert not any('/object/sign/' in str(call) for call in data['file_calls'])
        await done(context, state, data, 'Student uploads a private assignment file and downloads it through authenticated Storage')

        admin = sample_data('control_escolar')
        admin['institutional_announcements'] = [{'id': 'a7000000-0000-4000-8000-000000000002', 'course_id': None, 'course_name': None, 'title': 'Aviso institucional en borrador', 'body': 'Mensaje preparado por Control Escolar.', 'pinned': False, 'published': False, 'published_at': None, 'revision': 1}]
        context, page, state, data = await fixture(browser, role='control_escolar', data=admin)
        await expect(page.locator('#learningAnnouncements')).to_contain_text('Aviso institucional en borrador')
        await page.locator('#learningAnnouncements').get_by_role('button', name='Editar anuncio', exact=True).click()
        await field(page, 'title', 'Aviso institucional publicado')
        await page.locator('#learning-field-published').check()
        await save_dialog(page)
        await expect(page.locator('#learningAnnouncements')).to_contain_text('Aviso institucional publicado')
        assert data['writes'][-1]['p_course'] is None
        data['gradebook']['students'][0]['name'] = '=FORMULA DE PRUEBA'
        await nav(page, 'calificaciones')
        await expect(page.locator('#learningGradebook')).to_contain_text('=FORMULA DE PRUEBA')
        async with page.expect_download() as pending:
            await page.get_by_role('button', name='Exportar alumnos mostrados', exact=True).click()
        download = await pending.value
        import csv, io
        exported = list(csv.reader(io.StringIO(Path(await download.path()).read_text(encoding='utf-8-sig'))))
        assert exported[1][0] == "'=FORMULA DE PRUEBA"
        assert data['gradebook']['students'][0]['name'] == '=FORMULA DE PRUEBA'
        await done(context, state, data, 'Control Escolar edits institutional drafts, opens gradebook and exports CSV with spreadsheet formula neutralized')

        await browser.close()
        print(f'PASS {checks} learning browser integration scenarios; simulated API only', flush=True)


if __name__ == '__main__':
    h.prepare()
    OUT = h.ARTIFACTS
    try:
        asyncio.run(main())
    finally:
        h.server.shutdown(); h.server.server_close(); h.TEMP.cleanup()
