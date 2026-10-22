"""Control Escolar catalog browser checks with the real SDK and a simulated API.

Run: python3 tests/portal_control_catalogs.py
Uses Python/Playwright/Chromium and the HTTPS/SRI helper in portal_subjects.py.
PORTAL_TEST_ARTIFACTS optionally retains screenshots. No request is sent to the
real Supabase project; backend authorization is tested separately in PostgreSQL.
"""
import asyncio
import copy
import os
import re
import shutil
from playwright.async_api import async_playwright, expect
import portal_subjects as harness

checks = 0
CONTROL_PROFILE = {'full_name': 'Control Escolar de prueba', 'role': 'control_escolar', 'active': True}


def subject(number, name=None):
    return {'id': f'66666666-6666-4666-8666-{number:012d}', 'code': f'CAT-{number:03d}',
            'name': name or f'Materia de catálogo {number}', 'created_at': '2026-10-21T12:00:00+00:00'}


def period(number, name=None):
    return {'id': f'77777777-7777-4777-8777-{number:012d}',
            'name': name or f'Periodo de catálogo {number}', 'starts_on': f'{2020 + number:04d}-01-01',
            'ends_on': f'{2020 + number:04d}-06-30', 'created_at': '2026-10-21T12:00:00+00:00'}


async def fixture(browser, *, catalog=None, **options):
    options.setdefault('profile', copy.deepcopy(CONTROL_PROFILE))
    return await harness.fixture(browser, catalog=catalog, **options)


async def ready(page):
    await expect(page.locator('#controlSection')).to_be_visible()
    await expect(page.locator('#subjectCode')).to_be_enabled()
    await expect(page.locator('#periodName')).to_be_enabled()


async def fill_subject(page, code='FIL-201', name='Filosofía del conocimiento'):
    await page.locator('#subjectCode').fill(code)
    await page.locator('#subjectName').fill(name)


async def fill_period(page, name='Semestre de prueba 2027', start='2027-01-10', end='2027-06-30'):
    await page.locator('#periodName').fill(name)
    await page.locator('#periodStart').fill(start)
    await page.locator('#periodEnd').fill(end)


async def hide(page):
    await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')


async def unhide(page):
    await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')


async def finished(context, state, label):
    global checks
    assert not state['errors'], state['errors']
    assert not state['route_errors'], state['route_errors']
    for method, url in state['requests']:
        assert (method in ['GET', 'OPTIONS'] or '/auth/v1/' in url or
                (method == 'POST' and url.endswith(('/rpc/create_subject', '/rpc/create_academic_period', '/rpc/portal_learning_read')))), (method, url)
    checks += 1
    print('PASS ' + label, flush=True)
    for kind in ['subjects', 'periods']:
        for suffix in ['_gate', '_create_gate']:
            if state['catalog_' + kind + suffix]:
                state['catalog_' + kind + suffix].set()
    await context.close()


async def main():
    async with async_playwright() as pw:
        browser_path = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        browser = await pw.chromium.launch(executable_path=browser_path, headless=True)

        subject_gate, period_gate = asyncio.Event(), asyncio.Event()
        context, page, state = await fixture(browser, catalog={
            'subjects': [subject(1)], 'periods': [period(1)],
            'subjects_gate': subject_gate, 'periods_gate': period_gate})
        await state['catalog_subjects_started'].wait()
        await state['catalog_periods_started'].wait()
        await expect(page.locator('#subjectCreate')).to_be_disabled()
        await expect(page.locator('#periodCreate')).to_be_disabled()
        assert await page.locator('#subjectForm').get_attribute('method') == 'post'
        assert await page.locator('#periodForm').get_attribute('method') == 'post'
        assert not state['catalog_subjects_create_requests'] and not state['catalog_periods_create_requests']
        subject_gate.set()
        await expect(page.locator('#subjectCode')).to_be_enabled()
        await expect(page.locator('#periodName')).to_be_disabled()
        period_gate.set()
        await ready(page)
        await expect(page.locator('#subjectList .catalog-subject')).to_have_count(1)
        await expect(page.locator('#periodList .period-item')).to_have_count(1)
        assert state['catalog_subjects_requests'][0]['order'] == ['code.asc,id.asc']
        assert state['catalog_periods_requests'][0]['order'] == ['starts_on.desc,id.asc']
        await page.screenshot(path=str(harness.ARTIFACTS / 'control-desktop.png'), full_page=True)
        await finished(context, state, 'catalog reads are independent; creation waits for successful first lists')

        context, page, state = await fixture(browser)
        await ready(page)
        await expect(page.locator('#subjectList .catalog-subject')).to_have_count(0)
        await expect(page.locator('#periodList .period-item')).to_have_count(0)
        await fill_subject(page, ' fil-201 ', ' Filosofía del conocimiento ')
        await page.locator('#subjectCreate').click()
        await expect(page.locator('#subjectList .catalog-subject')).to_have_count(1)
        await expect(page.locator('#subjectList .subject-code')).to_have_text('FIL-201')
        await expect(page.locator('#subjectList .subject-name')).to_have_text('Filosofía del conocimiento')
        await expect(page.locator('#subjectCode')).to_have_value('')
        assert state['catalog_subjects_create_requests'] == [{'p_code': 'fil-201', 'p_name': 'Filosofía del conocimiento'}]
        assert len(state['catalog_subjects_requests']) == 2
        assert len(state['catalog_audit']) == 1
        assert not state['catalog_periods_create_requests']
        await expect(page.locator('#subjectMessage')).to_contain_text(re.compile('cread', re.I))
        await finished(context, state, 'empty catalogs allow one subject create; canonical response refreshes list and clears form')

        context, page, state = await fixture(browser)
        await ready(page)
        await fill_subject(page, 'BORRADOR', 'Materia aún sin enviar')
        await fill_period(page, ' Semestre de prueba 2027 ')
        await page.locator('#periodCreate').click()
        await expect(page.locator('#periodList .period-item')).to_have_count(1)
        await expect(page.locator('#periodList .period-name')).to_have_text('Semestre de prueba 2027')
        await expect(page.locator('#periodName')).to_have_value('')
        await expect(page.locator('#subjectCode')).to_have_value('BORRADOR')
        await expect(page.locator('#subjectName')).to_have_value('Materia aún sin enviar')
        assert state['catalog_periods_create_requests'] == [{'p_name': 'Semestre de prueba 2027', 'p_starts_on': '2027-01-10', 'p_ends_on': '2027-06-30'}]
        assert not state['catalog_subjects_create_requests']
        await finished(context, state, 'period creation refreshes only periods and preserves unsent subject fields')

        for kind in ['subjects', 'periods']:
            gate = asyncio.Event()
            context, page, state = await fixture(browser, catalog={kind + '_create_gate': gate})
            await ready(page)
            if kind == 'subjects': await fill_subject(page)
            else: await fill_period(page)
            form_id = '#subjectForm' if kind == 'subjects' else '#periodForm'
            await page.locator(form_id).dispatch_event('submit')
            await state['catalog_' + kind + '_create_started'].wait()
            await page.locator(form_id).dispatch_event('submit')
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            await expect(page.locator('#subjectCreate' if kind == 'subjects' else '#periodCreate')).to_be_disabled()
            gate.set()
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_enabled()
            assert len(state['catalog_audit']) == 1
            await finished(context, state, 'rapid repeated submit sends one ' + kind + ' creation')

        for values in [('', 'Nombre'), ('  ', 'Nombre'), ('FIL-101', ''), ('FIL-101', '   '), ('FIL-101', 'Nombre\tcon tab')]:
            context, page, state = await fixture(browser)
            await ready(page)
            await fill_subject(page, *values)
            await page.locator('#subjectForm').dispatch_event('submit')
            await page.wait_for_timeout(60)
            assert not state['catalog_subjects_create_requests']
            await finished(context, state, 'invalid subject input sends no write: ' + repr(values))

        for values in [('', '2027-01-01', '2027-06-30'), ('   ', '2027-01-01', '2027-06-30'),
                       ('Periodo', '', '2027-06-30'), ('Periodo', '2027-07-01', '2027-06-30')]:
            context, page, state = await fixture(browser)
            await ready(page)
            await fill_period(page, *values)
            await page.locator('#periodForm').dispatch_event('submit')
            await page.wait_for_timeout(60)
            assert not state['catalog_periods_create_requests']
            await finished(context, state, 'invalid period input sends no write: ' + repr(values))

        for kind in ['subjects', 'periods']:
            existing = subject(1) if kind == 'subjects' else period(1)
            context, page, state = await fixture(browser, catalog={kind: [existing]})
            await ready(page)
            if kind == 'subjects':
                await fill_subject(page, 'cat-001', 'Nombre diferente')
                await page.locator('#subjectCreate').click()
            else:
                await fill_period(page, existing['name'].upper())
                await page.locator('#periodCreate').click()
            message = '#subjectMessage' if kind == 'subjects' else '#periodMessage'
            await expect(page.locator(message)).to_contain_text(re.compile('existe|duplicad', re.I))
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_enabled()
            assert not state['catalog_audit']
            assert len(state['catalog_' + kind]) == 1
            await finished(context, state, 'known duplicate ' + kind + ' keeps form editable without overwrite or false success')

        for kind in ['subjects', 'periods']:
            gate = asyncio.Event()
            context, page, state = await fixture(browser, catalog={kind + '_create_gate': gate})
            await ready(page)
            if kind == 'subjects': await fill_subject(page)
            else: await fill_period(page)
            await page.locator('#subjectCreate' if kind == 'subjects' else '#periodCreate').click()
            await state['catalog_' + kind + '_create_started'].wait()
            state['catalog_' + kind + '_status'] = 500
            gate.set()
            await expect(page.locator('#subjectMessage' if kind == 'subjects' else '#periodMessage')).to_contain_text(re.compile('cread', re.I))
            await expect(page.locator('#subjectListStatus' if kind == 'subjects' else '#periodListStatus')).to_contain_text(re.compile('posible|error|fall', re.I))
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_disabled()
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            assert len(state['catalog_audit']) == 1
            state['catalog_' + kind + '_status'] = 200
            await page.locator('#subjectRefresh' if kind == 'subjects' else '#periodRefresh').click()
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_enabled()
            await expect(page.locator('#subjectList .catalog-subject' if kind == 'subjects' else '#periodList .period-item')).to_have_count(1)
            await finished(context, state, 'acknowledged ' + kind + ' creation remains successful if subsequent list refresh fails')

        for kind in ['subjects', 'periods']:
            context, page, state = await fixture(browser, catalog={kind + '_create_status': 500})
            await ready(page)
            if kind == 'subjects': await fill_subject(page)
            else: await fill_period(page)
            form_id = '#subjectForm' if kind == 'subjects' else '#periodForm'
            await page.locator(form_id).dispatch_event('submit')
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_disabled()
            await expect(page.locator('#subjectMessage' if kind == 'subjects' else '#periodMessage')).to_contain_text(re.compile('consult|actualiz|confirm', re.I))
            await page.locator(form_id).dispatch_event('submit')
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            await page.locator('#subjectRefresh' if kind == 'subjects' else '#periodRefresh').click()
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_enabled()
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            await finished(context, state, 'uncertain ' + kind + ' create blocks another write until manual list refresh')

        for kind in ['subjects', 'periods']:
            context, page, state = await fixture(browser, catalog={kind + '_commit_then_abort': True})
            await ready(page)
            if kind == 'subjects': await fill_subject(page)
            else: await fill_period(page)
            await page.locator('#subjectCreate' if kind == 'subjects' else '#periodCreate').click()
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_disabled()
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            assert len(state['catalog_audit']) == 1
            state['catalog_' + kind + '_commit_then_abort'] = False
            await page.locator('#subjectRefresh' if kind == 'subjects' else '#periodRefresh').click()
            await expect(page.locator('#subjectList .catalog-subject' if kind == 'subjects' else '#periodList .period-item')).to_have_count(1)
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_enabled()
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            await finished(context, state, 'committed but lost ' + kind + ' reply is read back without automatic write retry')

        for kind in ['subjects', 'periods']:
            for http_status in [404, 500]:
                context, page, state = await fixture(browser, catalog={kind + '_status': http_status})
                await expect(page.locator('#controlSection')).to_be_visible()
                await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_disabled()
                await expect(page.locator('#subjectListStatus' if kind == 'subjects' else '#periodListStatus')).to_contain_text(re.compile('posible|error|fall', re.I))
                state['catalog_' + kind + '_status'] = 200
                await page.locator('#subjectRefresh' if kind == 'subjects' else '#periodRefresh').click()
                await ready(page)
                assert not state['catalog_subjects_create_requests'] and not state['catalog_periods_create_requests']
                await finished(context, state, 'list failure ' + str(http_status) + ' ' + kind + ' differs from empty and recovers through refresh')

        for kind, malformed in [('subjects', [{'id': 'not-a-uuid', 'code': 'A', 'name': 'Nombre', 'created_at': '2026-01-01'}]),
                                ('periods', [{'id': period(1)['id'], 'name': 'Periodo', 'starts_on': 'bad', 'ends_on': '2027-01-01', 'created_at': '2026-01-01'}])]:
            context, page, state = await fixture(browser, catalog={kind: malformed})
            await expect(page.locator('#subjectListStatus' if kind == 'subjects' else '#periodListStatus')).to_contain_text(re.compile('posible|error|fall', re.I))
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_disabled()
            assert not state['catalog_subjects_create_requests'] and not state['catalog_periods_create_requests']
            await finished(context, state, 'malformed ' + kind + ' list fails closed')

        for kind in ['subjects', 'periods']:
            context, page, state = await fixture(browser, catalog={kind + '_create_override': []})
            await ready(page)
            if kind == 'subjects': await fill_subject(page)
            else: await fill_period(page)
            await page.locator('#subjectCreate' if kind == 'subjects' else '#periodCreate').click()
            await expect(page.locator('#subjectCode' if kind == 'subjects' else '#periodName')).to_be_disabled()
            await expect(page.locator('#subjectMessage' if kind == 'subjects' else '#periodMessage')).to_contain_text(re.compile('confirm|consult|actualiz', re.I))
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            await finished(context, state, 'malformed creation acknowledgement ' + kind + ' blocks another write')

        context, page, state = await fixture(browser, catalog={
            'subjects': [subject(i) for i in range(1, 24)], 'periods': [period(i) for i in range(1, 24)]})
        await ready(page)
        await expect(page.locator('#subjectList .catalog-subject')).to_have_count(20)
        await expect(page.locator('#periodList .period-item')).to_have_count(20)
        await page.locator('#subjectMore').click()
        await expect(page.locator('#subjectList .catalog-subject')).to_have_count(23)
        await expect(page.locator('#periodList .period-item')).to_have_count(20)
        await page.locator('#periodMore').click()
        await expect(page.locator('#periodList .period-item')).to_have_count(23)
        assert state['catalog_subjects_requests'][1]['offset'] == ['20']
        assert state['catalog_periods_requests'][1]['offset'] == ['20']
        assert await page.locator('#subjectList .subject-code').all_text_contents() == [f'CAT-{i:03d}' for i in range(1, 24)]
        await finished(context, state, 'catalog pagination20 plus3 is independent and never duplicates the sentinel')

        for role in ['student', 'professor']:
            context, page, state = await fixture(browser, profile={'full_name': 'Otra función', 'role': role, 'active': True})
            await expect(page.locator('#panelContent')).to_be_visible()
            await expect(page.locator('#controlSection')).to_be_hidden()
            assert not state['catalog_calls']
            await finished(context, state, 'role ' + role + ' cannot trigger Control Escolar queries')

        for options, label in [({'session': False}, 'anonymous'), ({'profile': []}, 'missing profile'),
                               ({'profile': {'full_name': 'Inactivo', 'role': 'control_escolar', 'active': False}}, 'inactive'),
                               ({'user_status': 401}, 'invalid identity')]:
            context, page, state = await fixture(browser, **options)
            await expect(page).to_have_url(re.compile('/portal/index.html'))
            assert not state['catalog_calls']
            await finished(context, state, 'denied ' + label + ' never requests catalogs')

        malicious_subject = subject(1, '<img src=x onerror=alert(1)>')
        malicious_subject['code'] = '<svg onload=alert(2)>'
        malicious_period = period(1, '<script>alert(3)</script>')
        context, page, state = await fixture(browser, mobile=True, catalog={
            'subjects': [malicious_subject], 'periods': [malicious_period]})
        await ready(page)
        await expect(page.locator('#subjectList .subject-name')).to_have_text('<img src=x onerror=alert(1)>')
        await expect(page.locator('#periodList .period-name')).to_have_text('<script>alert(3)</script>')
        assert await page.locator('#controlSection img, #controlSection svg, #controlSection script').count() == 0
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(harness.ARTIFACTS / 'control-mobile.png'), full_page=True)
        await finished(context, state, 'catalog names are literal text and mobile layout does not overflow')

        # A reply from the previous visible epoch cannot repopulate cleared lists.
        gate = asyncio.Event()
        context, page, state = await fixture(browser, catalog={'subjects': [subject(1)], 'subjects_gate': gate})
        await state['catalog_subjects_started'].wait()
        await hide(page)
        gate.set()
        await expect(page.locator('#controlSection')).to_be_hidden()
        await expect(page.locator('#subjectList .catalog-subject')).to_have_count(0)
        state['catalog_subjects_gate'] = None
        state['catalog_subjects'] = [subject(2)]
        await unhide(page)
        await ready(page)
        await expect(page.locator('#subjectList .subject-code')).to_have_text('CAT-002')
        await finished(context, state, 'hidden pending catalog read cannot repopulate old data; returning revalidates')

        for kind in ['subjects', 'periods']:
            gate = asyncio.Event()
            context, page, state = await fixture(browser, catalog={kind + '_create_gate': gate})
            await ready(page)
            if kind == 'subjects': await fill_subject(page)
            else: await fill_period(page)
            await page.locator('#subjectCreate' if kind == 'subjects' else '#periodCreate').click()
            await state['catalog_' + kind + '_create_started'].wait()
            await hide(page)
            gate.set()
            await expect(page.locator('#controlSection')).to_be_hidden()
            await expect(page.locator('#subjectCode')).to_have_value('')
            await expect(page.locator('#periodName')).to_have_value('')
            assert len(state['catalog_' + kind + '_create_requests']) == 1
            state['catalog_' + kind + '_create_gate'] = None
            await unhide(page)
            await ready(page)
            await expect(page.locator('#subjectList .catalog-subject' if kind == 'subjects' else '#periodList .period-item')).to_have_count(1)
            await finished(context, state, 'late ' + kind + ' creation acknowledgement stays hidden and is read after return')

        gate = asyncio.Event()
        context, page, state = await fixture(browser, catalog={'subjects_create_gate': gate})
        await ready(page)
        await fill_subject(page)
        await page.locator('#subjectCreate').click()
        await state['catalog_subjects_create_started'].wait()
        await page.locator('#logoutButton').click()
        await expect(page).to_have_url(re.compile('/portal/index.html'))
        gate.set()
        assert await page.evaluate('localStorage.getItem("seminario-mr-auth")') is None
        assert len(state['catalog_subjects_create_requests']) == 1
        await finished(context, state, 'logout during a write clears forms and ignores the late acknowledgement')

        context, page, state = await fixture(browser)
        await ready(page)
        await fill_subject(page)
        state['profile'] = {'full_name': 'Rol cambiado', 'role': 'student', 'active': True}
        await page.locator('#subjectCreate').click()
        await expect(page.locator('#controlSection')).to_be_hidden()
        await expect(page.locator('#subjectsSection')).to_be_visible()
        assert not state['catalog_audit']
        await finished(context, state, 'revoked role denies create and fresh access check removes Control Escolar UI')

        await browser.close()
        print(f'PASS {checks} Control Escolar browser scenarios; real SDK/simulated API, no live data modified', flush=True)


if __name__ == '__main__':
    harness.prepare()
    try:
        asyncio.run(main())
    finally:
        harness.server.shutdown()
        harness.server.server_close()
        harness.TEMP.cleanup()
