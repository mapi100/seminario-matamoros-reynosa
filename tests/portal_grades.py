"""Functional checks for published grades, using the real SDK and a simulated API.

Uses the same Python/Playwright/Chromium prerequisites as portal_subjects.py.
Run from the repository root: python3 tests/portal_grades.py
PORTAL_TEST_ARTIFACTS optionally retains desktop/mobile screenshots.
The helper downloads the pinned SDK over HTTPS and verifies its SRI. No request
is made to the actual project and no real credentials or academic data are used.
"""
import asyncio
import os
import shutil
from playwright.async_api import async_playwright, expect
import portal_subjects as harness

checks = 0


def grade(number, score):
    return {'enrollment_id': harness.subject(number)['id'], 'score': score}


async def complete(page):
    await harness.visible(page)
    await expect(page.locator('#subjectsSection')).to_have_attribute('aria-busy', 'false')


async def finished(context, state, label):
    global checks
    assert not state['errors'], state['errors']
    assert not state['route_errors'], state['route_errors']
    assert all(method in ['GET', 'OPTIONS'] or '/auth/v1/' in url
               or (method == 'POST' and url.endswith('/rpc/portal_learning_read'))
               for method, url in state['requests']), state['requests']
    checks += 1
    print('PASS ' + label, flush=True)
    if state['enrollment_gate']:
        state['enrollment_gate'].set()
    if state['grade_gate']:
        state['grade_gate'].set()
    await context.close()


async def main():
    async with async_playwright() as pw:
        browser_path = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        browser = await pw.chromium.launch(executable_path=browser_path, headless=True)

        context, page, state = await harness.fixture(
            browser, rows=[harness.subject(i) for i in range(1, 4)],
            grades=[grade(1, 85.5), grade(2, 0), grade(3, 100)])
        await complete(page)
        assert await page.locator('.subject-grade').all_text_contents() == [
            'Calificación publicada: 85.5 / 100',
            'Calificación publicada: 0 / 100',
            'Calificación publicada: 100 / 100']
        assert state['grade_requests'][0]['ids'] == [harness.subject(i)['id'] for i in range(1, 4)]
        await page.screenshot(path=str(harness.ARTIFACTS / 'grades-desktop.png'), full_page=True)
        before = len(state['grade_requests'])
        state['grades'] = [grade(1, 91.25)]
        await page.reload(wait_until='networkidle')
        await complete(page)
        await expect(page.locator('.subject-grade').first).to_have_text('Calificación publicada: 91.25 / 100')
        assert len(state['grade_requests']) > before
        await finished(context, state, 'published decimal, zero and100 are rendered; reload fetches updated grades')

        # RLS omits both drafts and absent rows. The frontend receives the same
        # empty result in either case and must not claim which one exists.
        context, page, state = await harness.fixture(browser, grades=[])
        await complete(page)
        assert await page.locator('.subject-grade').all_text_contents() == ['Sin calificación publicada'] * 2
        await expect(page.locator('#subjectsRetry')).to_be_hidden()
        await finished(context, state, 'absent and unpublished rows have the same generic text')

        for status in [403, 404, 500]:
            context, page, state = await harness.fixture(browser, grade_status=status)
            await complete(page)
            await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
            assert await page.locator('.subject-grade').all_text_contents() == ['No fue posible consultar la calificación.'] * 2
            await expect(page.locator('#subjectsStatus')).to_contain_text('No fue posible consultar las calificaciones.')
            await expect(page.locator('#subjectsRetry')).to_be_visible()
            before_profiles = len([url for _, url in state['requests'] if '/rest/v1/profiles' in url])
            state['grade_status'] = 200
            state['grades'] = [grade(1, 88)]
            await page.locator('#subjectsRetry').click()
            await complete(page)
            await expect(page.locator('.subject-grade').first).to_have_text('Calificación publicada: 88 / 100')
            await expect(page.locator('.subject-grade').nth(1)).to_have_text('Sin calificación publicada')
            await expect(page.locator('#subjectsRetry')).to_be_hidden()
            assert len([url for _, url in state['requests'] if '/rest/v1/profiles' in url]) > before_profiles
            await finished(context, state, f'grade HTTP{status} preserves subjects and retry revalidates access')

        invalid_responses = [
            ('negative score', [grade(1, -1)]),
            ('score above100', [grade(1, 100.01)]),
            ('null score', [grade(1, None)]),
            ('numeric string', [grade(1, '85.5')]),
            ('missing score', [{'enrollment_id': harness.subject(1)['id']}]),
            ('unrequested enrollment', [grade(999, 95)]),
            ('duplicate grade row', [grade(1, 20), grade(1, 90)]),
            ('missing enrollment identity', [{'score': 88}]),
            ('non-array body', {'score': 88}),
            ('partial invalid page', [grade(1, 85), grade(2, 150)]),
        ]
        for label, response in invalid_responses:
            context, page, state = await harness.fixture(browser, grades=response, grade_unfiltered=True)
            await complete(page)
            await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
            assert await page.locator('.subject-grade').all_text_contents() == ['No fue posible consultar la calificación.'] * 2
            await expect(page.locator('#subjectsRetry')).to_be_visible()
            assert 'Calificación publicada:' not in await page.locator('#subjectsList').inner_text()
            await finished(context, state, label + ' fails closed without losing subjects')

        for role in ['professor', 'control_escolar']:
            context, page, state = await harness.fixture(
                browser, profile={'full_name': 'Otra función', 'role': role, 'active': True}, grades=[grade(1, 100)])
            await expect(page.locator('#panelContent')).to_be_visible()
            await expect(page.locator('#subjectsSection')).to_be_hidden()
            assert not state['grade_requests'] and not state['enrollment_requests']
            await finished(context, state, role + ' does not request student grades')

        for options, label in [
            ({'session': False}, 'anonymous'),
            ({'profile': []}, 'missing profile'),
            ({'profile': {'full_name': 'Desactivado', 'role': 'student', 'active': False}}, 'inactive profile'),
            ({'user_status': 401}, 'invalid identity'),
        ]:
            context, page, state = await harness.fixture(browser, grades=[grade(1, 100)], **options)
            await expect(page).to_have_url(__import__('re').compile(r'/portal/index\.html'))
            assert not state['grade_requests'] and not state['enrollment_requests']
            await finished(context, state, label + ' never requests grades')

        context, page, state = await harness.fixture(browser, rows=[])
        await complete(page)
        await expect(page.locator('#subjectsStatus')).to_contain_text('Todavía no tienes materias inscritas.')
        assert not state['grade_requests']
        await finished(context, state, 'empty enrollments do not issue an unfiltered grade query')

        context, page, state = await harness.fixture(
            browser, rows=[harness.subject(i) for i in range(1, 24)],
            grades=[grade(i, i) for i in range(1, 24)])
        await complete(page)
        assert state['grade_requests'][0]['ids'] == [harness.subject(i)['id'] for i in range(1, 21)]
        await expect(page.locator('#subjectsMore')).to_be_visible()
        await page.locator('#subjectsMore').click()
        await complete(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(23)
        assert state['grade_requests'][1]['ids'] == [harness.subject(i)['id'] for i in range(21, 24)]
        assert await page.locator('.subject-grade').all_text_contents() == [
            f'Calificación publicada: {i} / 100' for i in range(1, 24)]
        await finished(context, state, 'grade batches include only current20 then3, excluding the lookahead row')

        context, page, state = await harness.fixture(
            browser, rows=[harness.subject(i) for i in range(1, 24)], grade_status=500)
        await complete(page)
        await expect(page.locator('#subjectsMore')).to_be_visible()
        state['grade_status'] = 200
        state['grades'] = [grade(21, 75)]
        await page.locator('#subjectsMore').click()
        await complete(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(23)
        await expect(page.locator('.subject-grade').nth(20)).to_have_text('Calificación publicada: 75 / 100')
        assert await page.locator('.subject-grade').first.text_content() == 'No fue posible consultar la calificación.'
        await expect(page.locator('#subjectsStatus')).to_contain_text('No fue posible consultar las calificaciones.')
        await expect(page.locator('#subjectsRetry')).to_be_visible()
        await finished(context, state, 'later successful page retains earlier grade error and a retry')

        gate = asyncio.Event()
        context, page, state = await harness.fixture(browser, grades=[grade(1, 95)], grade_gate=gate)
        await harness.visible(page)
        await asyncio.wait_for(state['grade_started'].wait(), 5)
        await expect(page.locator('.subject-grade').first).to_have_text('Consultando calificación…')
        await expect(page.locator('#logoutButton')).to_be_enabled()
        await page.locator('#logoutButton').click()
        await expect(page).to_have_url(harness.BASE + '/portal/index.html?estado=sesion_cerrada')
        gate.set()
        await page.wait_for_timeout(100)
        assert await page.locator('.subject-grade').count() == 0
        assert await page.evaluate('localStorage.getItem("seminario-mr-auth")') is None
        await finished(context, state, 'logout stays enabled during grade loading and rejects late result')

        gate = asyncio.Event()
        context, page, state = await harness.fixture(browser, grades=[grade(1, 95)], grade_gate=gate)
        await harness.visible(page)
        await asyncio.wait_for(state['grade_started'].wait(), 5)
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page.locator('#panelContent')).to_be_hidden()
        await expect(page.locator('.subject-grade')).to_have_count(0)
        gate.set()
        await page.wait_for_timeout(100)
        await expect(page.locator('.subject-grade')).to_have_count(0)
        state['grade_gate'] = None
        state['grades'] = [grade(1, 77)]
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await complete(page)
        await expect(page.locator('.subject-grade').first).to_have_text('Calificación publicada: 77 / 100')
        assert len(state['grade_requests']) == 2
        await finished(context, state, 'hidden tab clears grades and visible return fetches a fresh result')

        context, page, state = await harness.fixture(browser, grades=[grade(1, 10)])
        await complete(page)
        await page.evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted:true}))')
        await expect(page.locator('.subject-grade')).to_have_count(0)
        state['grades'] = [grade(1, 90)]
        await page.evaluate('window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted:true}))')
        await complete(page)
        await expect(page.locator('.subject-grade').first).to_have_text('Calificación publicada: 90 / 100')
        assert len(state['grade_requests']) == 2
        await finished(context, state, 'restored page discards old grade and rechecks access')

        context, page, state = await harness.fixture(browser, mobile=True, grades=[grade(1, 85.5)])
        await complete(page)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await expect(page.locator('.subject-grade').first).to_have_text('Calificación publicada: 85.5 / 100')
        await page.screenshot(path=str(harness.ARTIFACTS / 'grades-mobile.png'), full_page=True)
        await finished(context, state, 'grade presentation fits mobile without horizontal overflow')

        await browser.close()
        print(f'PASS {checks} grades browser scenarios; pinned SDK with simulated API; no live Supabase changes', flush=True)


if __name__ == '__main__':
    harness.prepare()
    try:
        asyncio.run(main())
        if os.environ.get('PORTAL_TEST_ARTIFACTS'):
            print('Screenshots: ' + str(harness.ARTIFACTS / 'grades-desktop.png') + ', ' + str(harness.ARTIFACTS / 'grades-mobile.png'))
    finally:
        harness.server.shutdown()
        harness.server.server_close()
        harness.TEMP.cleanup()
