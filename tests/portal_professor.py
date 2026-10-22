"""Professor course/roster browser checks with a real SDK and simulated API.

Uses the Python, Playwright and Chromium prerequisites of portal_subjects.py.
Run from the repository root: python3 tests/portal_professor.py
PORTAL_TEST_ARTIFACTS optionally retains screenshots. HTTPS and SRI verify the
SDK; no real project data or credentials are used. PostgreSQL/RLS is tested by
the separate local SQL runner, not by these simulated API responses.
"""
import asyncio
import copy
import os
import re
import shutil
from playwright.async_api import async_playwright, expect
import portal_subjects as harness

PROFILE = {'full_name': 'Profesor de prueba', 'role': 'professor', 'active': True}
checks = 0


def course(number):
    return harness.subject(number)


def student(number, name=None):
    return {'enrollment_id': f'33333333-3333-4333-8333-{number:012d}',
            'student_name': name or f'Alumno de ejemplo {number:02d}'}


async def fixture(browser, **options):
    options.setdefault('profile', PROFILE)
    options.setdefault('teaching', [course(1), course(2)])
    options.setdefault('rosters', {course(1)['id']: [student(1), student(2)],
                                    course(2)['id']: [student(3)]})
    return await harness.fixture(browser, **options)


async def courses_ready(page):
    await expect(page.locator('#teachingSection')).to_be_visible()
    await expect(page.locator('#teachingSection')).to_have_attribute('aria-busy', 'false')


async def open_roster(page, index=0):
    await page.locator('.teaching-open').nth(index).click()
    await expect(page.locator('#rosterSection')).to_be_visible()
    await expect(page.locator('#rosterSection')).to_have_attribute('aria-busy', 'false')


async def finished(context, state, label, *, allow_student=False):
    global checks
    assert not state['errors'], state['errors']
    assert not state['route_errors'], state['route_errors']
    if not allow_student:
        assert not state['enrollment_requests'], state['enrollment_requests']
        assert not state['grade_requests'], state['grade_requests']
    for method, url in state['requests']:
        assert (method in ['GET', 'OPTIONS'] or '/auth/v1/' in url
                or (method == 'POST' and url.endswith(('/rpc/get_teaching_roster', '/rpc/portal_learning_read')))), (method, url)
    checks += 1
    print('PASS ' + label, flush=True)
    for key in ['teaching_gate', 'roster_gate']:
        if state[key]:
            state[key].set()
    await context.close()


async def main():
    async with async_playwright() as pw:
        browser_path = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        browser = await pw.chromium.launch(executable_path=browser_path, headless=True)

        context, page, state = await fixture(browser)
        await courses_ready(page)
        await expect(page.locator('#panelTitle')).to_have_text('Panel de profesor')
        await expect(page.locator('#subjectsSection')).to_be_hidden()
        await expect(page.locator('#teachingLink')).to_be_visible()
        await expect(page.locator('.teaching-card')).to_have_count(2)
        await expect(page.locator('#rosterSection')).to_be_hidden()
        assert state['teaching_requests'][0]['query']['order'] == ['created_at.desc,id.asc']
        assert state['teaching_requests'][0]['query'].get('offset') == ['0']
        assert state['teaching_requests'][0]['query'].get('limit') == ['21']
        assert not state['roster_requests']
        await open_roster(page)
        assert await page.locator('.roster-student').all_text_contents() == [student(1)['student_name'], student(2)['student_name']]
        assert state['roster_requests'] == [{'p_assignment_id': course(1)['id'], 'p_offset': 0, 'p_limit': 21}]
        await page.screenshot(path=str(harness.ARTIFACTS/'professor-desktop.png'), full_page=True)
        before = len(state['teaching_requests'])
        await page.reload(wait_until='networkidle')
        await courses_ready(page)
        await expect(page.locator('#rosterSection')).to_be_hidden()
        await expect(page.locator('.roster-student')).to_have_count(0)
        assert len(state['teaching_requests']) > before
        await finished(context, state, 'professor sees assigned courses; roster is selected explicitly and reload clears names')

        context, page, state = await fixture(browser, teaching=[])
        await courses_ready(page)
        await expect(page.locator('#teachingStatus')).to_contain_text('Todavía no tienes materias asignadas')
        await expect(page.locator('.teaching-card')).to_have_count(0)
        await expect(page.locator('#teachingMore')).to_be_hidden()
        assert not state['roster_requests']
        await finished(context, state, 'empty assignment list is distinct from failure')

        for status in [403, 404, 500]:
            context, page, state = await fixture(browser, teaching_status=status)
            await courses_ready(page)
            await expect(page.locator('#teachingRetry')).to_be_visible()
            await expect(page.locator('.teaching-card')).to_have_count(0)
            await expect(page.locator('#teachingStatus')).not_to_contain_text('Todavía no tienes materias asignadas')
            before = len([url for _, url in state['requests'] if '/rest/v1/profiles' in url])
            state['teaching_status'] = 200
            await page.locator('#teachingRetry').click()
            await courses_ready(page)
            await expect(page.locator('.teaching-card')).to_have_count(2)
            assert len([url for _, url in state['requests'] if '/rest/v1/profiles' in url]) > before
            await finished(context, state, f'assignment HTTP{status} error and retry revalidates profile')

        for role in ['student', 'control_escolar']:
            context, page, state = await fixture(browser, profile={'full_name': 'Otro rol', 'role': role, 'active': True})
            await expect(page.locator('#panelContent')).to_be_visible()
            await expect(page.locator('#teachingSection')).to_be_hidden()
            assert not state['teaching_requests'] and not state['roster_requests']
            # Student queries are expected here; this check concerns professor data.
            assert not state['errors'] and not state['route_errors']
            await finished(context, state, f'no teacher requests for {role}', allow_student=role == 'student')

        for options, label in [({'session': False}, 'anonymous'), ({'profile': []}, 'missing profile'),
                               ({'profile': {'full_name': 'Inactivo', 'role': 'professor', 'active': False}}, 'inactive'),
                               ({'user_status': 401}, 'invalid identity')]:
            context, page, state = await fixture(browser, **options)
            await expect(page).to_have_url(re.compile(r'/portal/index\.html'))
            assert not state['teaching_requests'] and not state['roster_requests']
            await finished(context, state, f'denied {label} cannot query teacher data')

        context, page, state = await fixture(browser, teaching=[course(i) for i in range(1, 24)])
        await courses_ready(page)
        await expect(page.locator('.teaching-card')).to_have_count(20)
        await expect(page.locator('#teachingMore')).to_be_visible()
        await page.locator('#teachingMore').click()
        await expect(page.locator('.teaching-card')).to_have_count(23)
        await courses_ready(page)
        assert state['teaching_requests'][1]['query']['offset'] == ['20']
        await expect(page.locator('#teachingMore')).to_be_hidden()
        assert await page.locator('.teaching-name').all_text_contents() == [course(i)['subjects']['name'] for i in range(1, 24)]
        await finished(context, state, 'course pages show20 then3 with no repeated sentinel')

        first, second = course(1), course(2)
        second['subjects'] = copy.deepcopy(first['subjects'])
        second['academic_periods']['name'] = 'Otro periodo 2027'
        second['academic_periods']['starts_on'] = '2027-01-01'
        second['academic_periods']['ends_on'] = '2027-06-30'
        context, page, state = await fixture(browser, teaching=[first, second])
        await courses_ready(page)
        await open_roster(page)
        await expect(page.locator('.roster-student')).to_have_count(2)
        await open_roster(page, 1)
        await expect(page.locator('.roster-student')).to_have_count(1)
        await expect(page.locator('#rosterPeriod')).to_contain_text('Otro periodo 2027')
        assert await page.locator('.roster-student').all_text_contents() == [student(3)['student_name']]
        assert state['roster_requests'][-1]['p_assignment_id'] == second['id']
        await finished(context, state, 'same subject in different period selects assignment ID and replaces roster')

        bad_courses = []
        item = course(1); item['id'] = 'invalid'; bad_courses.append(item)
        item = course(1); item['subjects'] = None; bad_courses.append(item)
        item = course(1); item['subjects']['name'] = ' '; bad_courses.append(item)
        item = course(1); item['academic_periods']['name'] = ' '; bad_courses.append(item)
        for index, bad in enumerate(bad_courses):
            context, page, state = await fixture(browser, teaching=[bad])
            await courses_ready(page)
            await expect(page.locator('#teachingRetry')).to_be_visible()
            await expect(page.locator('.teaching-card')).to_have_count(0)
            await finished(context, state, f'malformed assignment {index+1} fails without partial cards')

        context, page, state = await fixture(browser, rosters={})
        await courses_ready(page)
        await open_roster(page)
        await expect(page.locator('.roster-student')).to_have_count(0)
        await expect(page.locator('#rosterStatus')).to_contain_text('No hay alumnos activos')
        await expect(page.locator('#rosterRetry')).to_be_hidden()
        await finished(context, state, 'roster valid empty state')

        for status in [403, 404, 500]:
            context, page, state = await fixture(browser, roster_status=status)
            await courses_ready(page)
            await open_roster(page)
            await expect(page.locator('.roster-student')).to_have_count(0)
            await expect(page.locator('#rosterRetry')).to_be_visible()
            await expect(page.locator('#rosterStatus')).not_to_contain_text('No hay alumnos activos')
            await expect(page.locator('.teaching-card')).to_have_count(2)
            before = len([url for _, url in state['requests'] if '/rest/v1/profiles' in url])
            state['roster_status'] = 200
            await page.locator('#rosterRetry').click()
            await courses_ready(page)
            await expect(page.locator('#rosterSection')).to_be_hidden()
            assert len([url for _, url in state['requests'] if '/rest/v1/profiles' in url]) > before
            await open_roster(page)
            await expect(page.locator('.roster-student')).to_have_count(2)
            await finished(context, state, f'roster HTTP{status} does not erase courses; retry refreshes authorization')

        bad_rosters = [[{'enrollment_id': 'invalid', 'student_name': 'Nombre'}],
                       [{'enrollment_id': student(1)['enrollment_id'], 'student_name': ' '}],
                       [student(1), student(1)], [None], {'unexpected': 'shape'}]
        for index, rows in enumerate(bad_rosters):
            context, page, state = await fixture(browser, rosters={course(1)['id']: rows})
            await courses_ready(page)
            await open_roster(page)
            await expect(page.locator('.roster-student')).to_have_count(0)
            await expect(page.locator('#rosterRetry')).to_be_visible()
            await finished(context, state, f'malformed roster {index+1} never exposes partial names')

        context, page, state = await fixture(browser, rosters={course(1)['id']: [student(i) for i in range(1, 24)]})
        await courses_ready(page)
        await open_roster(page)
        await expect(page.locator('.roster-student')).to_have_count(20)
        await page.locator('#rosterMore').click()
        await expect(page.locator('.roster-student')).to_have_count(23)
        await expect(page.locator('#rosterSection')).to_have_attribute('aria-busy', 'false')
        await expect(page.locator('#rosterMore')).to_be_hidden()
        assert state['roster_requests'][-1] == {'p_assignment_id': course(1)['id'], 'p_offset': 20, 'p_limit': 21}
        assert await page.locator('.roster-student').all_text_contents() == [student(i)['student_name'] for i in range(1, 24)]
        await finished(context, state, 'roster pages20 plus3 without duplicate sentinel')

        context, page, state = await fixture(browser, rosters={course(1)['id']: [student(i) for i in range(1, 24)]})
        await courses_ready(page)
        await open_roster(page)
        await expect(page.locator('.roster-student')).to_have_count(20)
        state['roster_status'] = 403
        await page.locator('#rosterMore').click()
        await expect(page.locator('#rosterRetry')).to_be_visible()
        await expect(page.locator('.roster-student')).to_have_count(0)
        await finished(context, state, 'failed roster page removes previously visible names after possible revocation')

        gate = asyncio.Event()
        context, page, state = await fixture(browser, teaching=[course(i) for i in range(1, 24)], roster_gate=gate)
        await courses_ready(page)
        await page.locator('.teaching-open').first.click()
        await asyncio.wait_for(state['roster_started'].wait(), 5)
        await page.locator('#teachingMore').click()
        await courses_ready(page)
        await expect(page.locator('.teaching-card')).to_have_count(23)
        gate.set()
        await expect(page.locator('#rosterSection')).to_have_attribute('aria-busy', 'false')
        await expect(page.locator('.roster-student')).to_have_count(2)
        await finished(context, state, 'course pagination does not invalidate an independent pending roster')

        context, page, state = await fixture(browser, teaching=[course(i) for i in range(1, 24)])
        await courses_ready(page)
        await open_roster(page)
        await expect(page.locator('.roster-student')).to_have_count(2)
        state['teaching_status'] = 403
        await page.locator('#teachingMore').click()
        await courses_ready(page)
        await expect(page.locator('#teachingRetry')).to_be_visible()
        await expect(page.locator('.teaching-card')).to_have_count(20)
        await expect(page.locator('.roster-student')).to_have_count(0)
        await expect(page.locator('#rosterSection')).to_be_hidden()
        await finished(context, state, 'assignment page failure retains course labels but removes old roster')

        context, page, state = await fixture(browser)
        await courses_ready(page)
        await open_roster(page)
        before = len(state['teaching_requests'])
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')
        state['profile'] = {'full_name': 'Ahora alumno', 'role': 'student', 'active': True}
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page.locator('#panelTitle')).to_have_text('Panel de alumno')
        await expect(page.locator('#teachingSection')).to_be_hidden()
        await expect(page.locator('.roster-student')).to_have_count(0)
        assert len(state['teaching_requests']) == before
        await finished(context, state, 'changed role on return removes teacher UI and issues no new teacher query', allow_student=True)

        malicious = course(1)
        malicious['subjects']['name'] = '<img src=x onerror=alert(1)>'
        malicious['subjects']['code'] = '<svg onload=alert(2)>'
        malicious['academic_periods']['name'] = '<script>alert(3)</script>'
        context, page, state = await fixture(browser, mobile=True, teaching=[malicious],
                                            rosters={malicious['id']: [student(1, '<img src=x onerror=alert(4)>')]})
        await courses_ready(page)
        await open_roster(page)
        await expect(page.locator('.teaching-name')).to_have_text(malicious['subjects']['name'])
        await expect(page.locator('.roster-student')).to_have_text('<img src=x onerror=alert(4)>')
        assert await page.locator('#teachingList img, #teachingList svg, #teachingList script, #rosterList img').count() == 0
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(harness.ARTIFACTS/'professor-mobile.png'), full_page=True)
        await finished(context, state, 'names remain literal text and mobile professor layout has no overflow')

        gate = asyncio.Event()
        context, page, state = await fixture(browser, roster_gate=gate)
        await courses_ready(page)
        await page.locator('.teaching-open').first.click()
        await asyncio.wait_for(state['roster_started'].wait(), 5)
        await expect(page.locator('#logoutButton')).to_be_enabled()
        await page.locator('#logoutButton').click()
        await expect(page).to_have_url(harness.BASE+'/portal/index.html?estado=sesion_cerrada')
        gate.set()
        await page.wait_for_timeout(100)
        assert await page.locator('#rosterList').count() == 0
        assert await page.evaluate('localStorage.getItem("seminario-mr-auth")') is None
        await finished(context, state, 'logout during roster request clears session and rejects delayed names')

        gate = asyncio.Event()
        context, page, state = await fixture(browser, roster_gate=gate)
        await courses_ready(page)
        await page.locator('.teaching-open').first.click()
        await asyncio.wait_for(state['roster_started'].wait(), 5)
        state['roster_gate'] = None
        await open_roster(page, 1)
        await expect(page.locator('.roster-student')).to_have_text(student(3)['student_name'])
        gate.set()
        await page.wait_for_timeout(100)
        await expect(page.locator('.roster-student')).to_have_text(student(3)['student_name'])
        await finished(context, state, 'switching selected assignment discards delayed previous roster')

        gate = asyncio.Event()
        context, page, state = await fixture(browser, roster_gate=gate)
        await courses_ready(page)
        await page.locator('.teaching-open').first.click()
        await asyncio.wait_for(state['roster_started'].wait(), 5)
        await page.locator('#rosterClose').click()
        gate.set()
        await page.wait_for_timeout(100)
        await expect(page.locator('#rosterSection')).to_be_hidden()
        await expect(page.locator('.roster-student')).to_have_count(0)
        await finished(context, state, 'closing roster removes names and discards pending result')

        gate = asyncio.Event()
        context, page, state = await fixture(browser, roster_gate=gate)
        await courses_ready(page)
        await page.locator('.teaching-open').first.click()
        await asyncio.wait_for(state['roster_started'].wait(), 5)
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')
        gate.set()
        await page.wait_for_timeout(100)
        await expect(page.locator('.roster-student')).to_have_count(0)
        await expect(page.locator('.teaching-card')).to_have_count(0)
        state['profile'] = []
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page).to_have_url(harness.BASE+'/portal/index.html?estado=sin_acceso')
        await finished(context, state, 'hidden tab erases professor data and rechecks revoked profile on return')

        context, page, state = await fixture(browser)
        await courses_ready(page)
        await open_roster(page)
        await page.evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide",{persisted:true}))')
        await expect(page.locator('.roster-student')).to_have_count(0)
        state['teaching'] = [course(3)]
        await page.evaluate('window.dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}))')
        await courses_ready(page)
        await expect(page.locator('.teaching-card')).to_have_count(1)
        await expect(page.locator('.teaching-name')).to_have_text(course(3)['subjects']['name'])
        await expect(page.locator('#rosterSection')).to_be_hidden()
        await finished(context, state, 'restored cached page refetches assignments without restoring old roster')

        context, page, state = await fixture(browser, initial_hidden=True)
        await expect(page.locator('#panelContent')).to_be_hidden()
        await page.wait_for_timeout(100)
        assert not state['requests']
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await courses_ready(page)
        await expect(page.locator('.teaching-card')).to_have_count(2)
        await finished(context, state, 'initial hidden professor page waits for visible access verification')

        await browser.close()
        print(f'PASS {checks} professor browser scenarios; real SDK, simulated API, no real data modified', flush=True)


if __name__ == '__main__':
    harness.prepare()
    try:
        asyncio.run(main())
        if os.environ.get('PORTAL_TEST_ARTIFACTS'):
            print('Professor screenshots: '+str(harness.ARTIFACTS))
    finally:
        harness.server.shutdown()
        harness.server.server_close()
        harness.TEMP.cleanup()
