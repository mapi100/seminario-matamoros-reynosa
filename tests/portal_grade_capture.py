"""Teacher grade-entry browser checks with the real SDK and a simulated API.

Requires Python, Playwright and Chromium, as documented in portal_subjects.py.
Run from the repository root: python3 tests/portal_grade_capture.py
PORTAL_TEST_ARTIFACTS optionally retains screenshots. The shared helper verifies
the SDK over HTTPS/SRI. These tests exercise UI behavior, not live PostgreSQL,
Supabase Auth or actual academic records.
"""
import asyncio
import copy
import os
import shutil
from playwright.async_api import async_playwright, expect
import portal_professor as professor
import portal_subjects as harness

checks = 0


def record(number=1, *, published=85.5, draft=85.5, revision=2, pending=False):
    return {'enrollment_id': professor.student(number)['enrollment_id'],
            'published_score': published, 'draft_score': draft,
            'revision': revision, 'has_unpublished_changes': pending}


async def fixture(browser, *, capture=None, **options):
    if capture is None:
        first = record()
        capture = {'records': {first['enrollment_id']: first}}
    return await professor.fixture(browser, capture=capture, **options)


async def open_editor(page, index=0):
    await professor.courses_ready(page)
    await professor.open_roster(page)
    await page.locator('.grade-open').nth(index).click()
    await expect(page.locator('#gradeEditor')).to_be_visible()


async def editor_ready(page):
    await expect(page.locator('#gradeForm')).to_have_attribute('aria-busy', 'false')
    await expect(page.locator('#gradeScore')).to_be_enabled()


async def set_score(page, value):
    await page.locator('#gradeScore').fill(str(value))


async def save(page):
    await page.locator('#gradeSave').click()
    await editor_ready(page)


async def finished(context, state, label, *, allow_student=False):
    global checks
    assert not state['errors'], state['errors']
    assert not state['route_errors'], state['route_errors']
    if not allow_student:
        assert not state['enrollment_requests'] and not state['grade_requests']
    allowed = ['get_teaching_roster', 'get_teaching_grade',
               'save_teaching_grade', 'publish_teaching_grade']
    for method, url in state['requests']:
        assert (method in ['GET', 'OPTIONS'] or '/auth/v1/' in url
                or (method == 'POST' and any(url.endswith('/rpc/' + rpc) for rpc in allowed))), (method, url)
    checks += 1
    print('PASS ' + label, flush=True)
    for key in ['teaching_gate', 'roster_gate', 'capture_get_gate',
                'capture_save_gate', 'capture_publish_gate']:
        if state[key]:
            state[key].set()
    await context.close()


async def main():
    async with async_playwright() as pw:
        browser_path = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        browser = await pw.chromium.launch(executable_path=browser_path, headless=True)

        # Opening the editor must remain read-only, even while a slow GET waits.
        gate = asyncio.Event()
        context, page, state = await fixture(browser, capture={'get_gate': gate})
        await open_editor(page)
        await state['capture_get_started'].wait()
        await expect(page.locator('#gradeScore')).to_be_disabled()
        await expect(page.locator('#gradeSave')).to_be_disabled()
        await expect(page.locator('#gradePublish')).to_be_disabled()
        assert await page.locator('#gradeForm').get_attribute('method') == 'post'
        assert await page.locator('#gradeScore').get_attribute('min') == '0'
        assert await page.locator('#gradeScore').get_attribute('max') == '100'
        assert await page.locator('#gradeScore').get_attribute('step') == '0.01'
        assert not state['capture_save_requests'] and not state['capture_publish_requests']
        gate.set()
        await editor_ready(page)
        await finished(context, state, 'Calificar opens a read-only editor; controls wait for server state')

        first = record(published=85.5, draft=90, revision=3, pending=True)
        context, page, state = await fixture(browser, capture={'records': {first['enrollment_id']: first}})
        await open_editor(page)
        await editor_ready(page)
        await expect(page.locator('#gradePublished')).to_have_text('Publicada: 85.5 / 100')
        await expect(page.locator('#gradeScore')).to_have_value('90')
        await expect(page.locator('#gradePublish')).to_be_enabled()
        await set_score(page, 95.25)
        await expect(page.locator('#gradePublish')).to_be_disabled()
        await save(page)
        await expect(page.locator('#gradePublished')).to_have_text('Publicada: 85.5 / 100')
        await expect(page.locator('#gradePublish')).to_be_enabled()
        assert state['capture_save_requests'] == [{
            'p_assignment_id': professor.course(1)['id'],
            'p_enrollment_id': first['enrollment_id'],
            'p_score': 95.25, 'p_expected_revision': 3}]
        await page.locator('#gradePublish').click()
        await editor_ready(page)
        await expect(page.locator('#gradePublished')).to_have_text('Publicada: 95.25 / 100')
        await expect(page.locator('#gradePublish')).to_be_disabled()
        assert state['capture_publish_requests'] == [{
            'p_assignment_id': professor.course(1)['id'],
            'p_enrollment_id': first['enrollment_id'], 'p_expected_revision': 4}]
        assert state['capture_audit'] == [('save_draft', first['enrollment_id'], 95.25),
                                           ('publish', first['enrollment_id'], 95.25)]
        await page.screenshot(path=str(harness.ARTIFACTS / 'grade-capture-desktop.png'), full_page=True)
        await finished(context, state, 'save preserves published grade; explicit Publish sends only saved revision')

        for score in [0, 100]:
            first = record(published=None, draft=None, revision=0)
            context, page, state = await fixture(browser, capture={'records': {first['enrollment_id']: first}})
            await open_editor(page)
            await editor_ready(page)
            await set_score(page, score)
            await save(page)
            await page.locator('#gradePublish').click()
            await editor_ready(page)
            await expect(page.locator('#gradePublished')).to_have_text(f'Publicada: {score} / 100')
            assert state['capture_publish_requests'][0]['p_expected_revision'] == 1
            await finished(context, state, f'valid boundary grade {score} saves and publishes')

        first = record(published=None, draft=72, revision=0, pending=False)
        context, page, state = await fixture(browser, capture={'records': {first['enrollment_id']: first}})
        await open_editor(page)
        await editor_ready(page)
        await expect(page.locator('#gradeScore')).to_have_value('72')
        await expect(page.locator('#gradePublished')).to_have_text('Sin calificación publicada')
        await expect(page.locator('#gradePublish')).to_be_disabled()
        await save(page)
        await expect(page.locator('#gradePublish')).to_be_enabled()
        assert state['capture_save_requests'][0]['p_expected_revision'] == 0
        await finished(context, state, 'legacy unpublished note requires Save before Publish')

        for bad_value in ['', '-1', '100.01', '100.001', '85.555']:
            context, page, state = await fixture(browser)
            await open_editor(page)
            await editor_ready(page)
            await set_score(page, bad_value)
            await page.locator('#gradeForm').dispatch_event('submit')
            await page.wait_for_timeout(50)
            assert not state['capture_save_requests'] and not state['capture_publish_requests']
            await expect(page.locator('#gradePublish')).to_be_disabled()
            await finished(context, state, 'invalid or empty score sends no write: ' + repr(bad_value))

        # A held acknowledgement must not allow another submit, and the mock
        # commits before releasing the reply to mirror a real network boundary.
        gate = asyncio.Event()
        context, page, state = await fixture(browser, capture={'save_gate': gate})
        await open_editor(page)
        await editor_ready(page)
        await set_score(page, 81)
        await page.locator('#gradeForm').dispatch_event('submit')
        await state['capture_save_started'].wait()
        await page.locator('#gradeForm').dispatch_event('submit')
        await expect(page.locator('#gradeSave')).to_be_disabled()
        await expect(page.locator('#gradePublish')).to_be_disabled()
        assert len(state['capture_save_requests']) == 1
        gate.set()
        await editor_ready(page)
        await finished(context, state, 'double submit makes one save RPC while acknowledgement is pending')

        gate = asyncio.Event()
        first = record(draft=87, revision=3, pending=True)
        context, page, state = await fixture(browser, capture={
            'records': {first['enrollment_id']: first}, 'publish_gate': gate})
        await open_editor(page)
        await editor_ready(page)
        await page.locator('#gradePublish').click()
        await state['capture_publish_started'].wait()
        await page.locator('#gradePublish').dispatch_event('click')
        assert len(state['capture_publish_requests']) == 1
        gate.set()
        await editor_ready(page)
        await finished(context, state, 'double Publish makes one RPC and cannot submit a free score')

        for action, http_status in [('save', 409), ('save', 500), ('publish', 409), ('publish', 500)]:
            first = record(draft=90, revision=3, pending=True)
            context, page, state = await fixture(browser, capture={
                'records': {first['enrollment_id']: first}, action + '_status': http_status})
            await open_editor(page)
            await editor_ready(page)
            if action == 'save':
                await set_score(page, 91)
                await page.locator('#gradeSave').click()
            else:
                await page.locator('#gradePublish').click()
            await expect(page.locator('#gradeReload')).to_be_visible()
            await expect(page.locator('#gradeSave')).to_be_disabled()
            await expect(page.locator('#gradePublish')).to_be_disabled()
            assert len(state['capture_' + action + '_requests']) == 1
            state['capture_' + action + '_status'] = 200
            await page.locator('#gradeReload').click()
            await editor_ready(page)
            assert len(state['capture_get_requests']) == 2
            assert state['capture_calls'][-1][0] == 'get'
            await finished(context, state, f'{action} HTTP{http_status} blocks writes until explicit state reload')

        context, page, state = await fixture(browser, capture={'commit_then_abort': True})
        await open_editor(page)
        await editor_ready(page)
        await set_score(page, 93)
        await page.locator('#gradeSave').click()
        await expect(page.locator('#gradeReload')).to_be_visible()
        await expect(page.locator('#gradeSave')).to_be_disabled()
        await expect(page.locator('#gradePublish')).to_be_disabled()
        assert len(state['capture_save_requests']) == 1
        state['capture_commit_then_abort'] = False
        await page.locator('#gradeReload').click()
        await editor_ready(page)
        await expect(page.locator('#gradeScore')).to_have_value('93')
        await expect(page.locator('#gradePublish')).to_be_enabled()
        assert len(state['capture_save_requests']) == 1
        await finished(context, state, 'uncertain network outcome never auto-retries a write; GET recovers committed draft')

        for http_status in [404, 500]:
            context, page, state = await fixture(browser, capture={'get_status': http_status})
            await open_editor(page)
            await expect(page.locator('#gradeReload')).to_be_visible()
            await expect(page.locator('#gradeScore')).to_be_disabled()
            await expect(page.locator('#gradeSave')).to_be_disabled()
            await expect(page.locator('#gradePublish')).to_be_disabled()
            state['capture_get_status'] = 200
            await page.locator('#gradeReload').click()
            await editor_ready(page)
            assert not state['capture_save_requests'] and not state['capture_publish_requests']
            await finished(context, state, f'grade GET HTTP{http_status} fails closed and reload only reads')

        context, page, state = await fixture(browser, capture={'get_status': 403})
        await professor.courses_ready(page)
        await professor.open_roster(page)
        before_profiles = len([url for _, url in state['requests'] if '/rest/v1/profiles' in url])
        await page.locator('.grade-open').first.click()
        await state['capture_get_started'].wait()
        await expect(page.locator('#gradeEditor')).to_be_hidden()
        await professor.courses_ready(page)
        assert len([url for _, url in state['requests'] if '/rest/v1/profiles' in url]) > before_profiles
        assert not state['capture_save_requests'] and not state['capture_publish_requests']
        await finished(context, state, 'forbidden grade read closes editor and revalidates professor access')

        invalid_states = []
        invalid_states.append(('empty result', []))
        invalid_states.append(('duplicate result', [record(), record()]))
        invalid_states.append(('wrong enrollment', [record(999)]))
        for key, value in [('published_score', 100.01), ('draft_score', -1),
                           ('draft_score', '85.5'), ('revision', -1),
                           ('revision', 1.5), ('has_unpublished_changes', 'true')]:
            bad = record(); bad[key] = value
            invalid_states.append((key + '=' + repr(value), [bad]))
        for label, body in invalid_states:
            context, page, state = await fixture(browser, capture={'get_override': body})
            await open_editor(page)
            await expect(page.locator('#gradeReload')).to_be_visible()
            await expect(page.locator('#gradeScore')).to_be_disabled()
            await expect(page.locator('#gradeSave')).to_be_disabled()
            await expect(page.locator('#gradePublish')).to_be_disabled()
            assert not state['capture_save_requests'] and not state['capture_publish_requests']
            await finished(context, state, 'malformed grade response fails closed: ' + label)

        context, page, state = await fixture(browser, capture={'save_override': [record(999)]})
        await open_editor(page)
        await editor_ready(page)
        await set_score(page, 81)
        await page.locator('#gradeSave').click()
        await expect(page.locator('#gradeReload')).to_be_visible()
        await expect(page.locator('#gradeSave')).to_be_disabled()
        await expect(page.locator('#gradePublish')).to_be_disabled()
        state['capture_save_override'] = None
        await page.locator('#gradeReload').click()
        await editor_ready(page)
        await expect(page.locator('#gradeScore')).to_have_value('81')
        await finished(context, state, 'malformed save acknowledgement requires GET before another write')

        # Old responses from a different student must never overwrite the editor
        # selected later, even if the old HTTP request finishes afterwards.
        gate = asyncio.Event()
        first = record(1, published=11, draft=11)
        second = record(2, published=88, draft=88)
        context, page, state = await fixture(browser, capture={
            'records': {first['enrollment_id']: first, second['enrollment_id']: second}, 'get_gate': gate})
        await open_editor(page)
        await state['capture_get_started'].wait()
        state['capture_get_gate'] = None
        await page.locator('.grade-open').nth(1).click()
        await editor_ready(page)
        await expect(page.locator('#gradePublished')).to_have_text('Publicada: 88 / 100')
        gate.set()
        await page.wait_for_timeout(100)
        await expect(page.locator('#gradePublished')).to_have_text('Publicada: 88 / 100')
        await finished(context, state, 'switching students rejects the previous delayed GET')

        for close_action in ['editor', 'roster', 'course', 'hidden', 'logout']:
            gate = asyncio.Event()
            context, page, state = await fixture(browser, capture={'save_gate': gate})
            await open_editor(page)
            await editor_ready(page)
            await set_score(page, 82)
            await page.locator('#gradeSave').click()
            await state['capture_save_started'].wait()
            if close_action == 'editor':
                await page.locator('#gradeCancel').click()
            elif close_action == 'roster':
                await page.locator('#rosterClose').click()
            elif close_action == 'course':
                await page.locator('.teaching-open').nth(1).click()
            elif close_action == 'hidden':
                await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')
            else:
                await page.locator('#logoutButton').click()
                await expect(page).to_have_url(harness.BASE + '/portal/index.html?estado=sesion_cerrada')
            if close_action != 'logout':
                await expect(page.locator('#gradeEditor')).to_be_hidden()
                await expect(page.locator('#gradeScore')).to_have_value('')
            gate.set()
            await page.wait_for_timeout(100)
            if close_action != 'logout':
                await expect(page.locator('#gradeEditor')).to_be_hidden()
                await expect(page.locator('#gradeScore')).to_have_value('')
            assert len(state['capture_save_requests']) == 1
            assert not state['capture_publish_requests']
            await finished(context, state, 'pending save cannot repopulate editor after ' + close_action)

        context, page, state = await fixture(browser, mobile=True,
            rosters={professor.course(1)['id']: [professor.student(1, '<img src=x onerror=alert(1)>')]})
        await open_editor(page)
        await editor_ready(page)
        await expect(page.locator('#gradeEditorTitle')).to_contain_text('<img src=x onerror=alert(1)>')
        assert await page.locator('#gradeEditor img, #gradeEditor svg, #gradeEditor script').count() == 0
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(harness.ARTIFACTS / 'grade-capture-mobile.png'), full_page=True)
        await finished(context, state, 'grade editor renders names as text and fits mobile')

        for role in ['student', 'control_escolar']:
            context, page, state = await fixture(browser, profile={'full_name': 'Otro rol', 'role': role, 'active': True})
            await expect(page.locator('#panelContent')).to_be_visible()
            await expect(page.locator('#gradeEditor')).to_be_hidden()
            assert not state['capture_calls']
            assert not state['errors'] and not state['route_errors']
            checks_label = 'other profile role cannot open grade editor: ' + role
            await finished(context, state, checks_label, allow_student=role == 'student')

        await browser.close()
        print(f'PASS {checks} grade capture browser scenarios; real pinned SDK, simulated API; no live writes', flush=True)


if __name__ == '__main__':
    harness.prepare()
    try:
        asyncio.run(main())
        if os.environ.get('PORTAL_TEST_ARTIFACTS'):
            print('Screenshots: ' + str(harness.ARTIFACTS))
    finally:
        harness.server.shutdown()
        harness.server.server_close()
        harness.TEMP.cleanup()
