"""Clases por bloques: SDK real, API simulada; ninguna escritura en producción."""
import asyncio
import copy
import json
import shutil
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect
import portal_subjects as h
import portal_workspace as w
import portal_course_organizer as o

checks = 0


async def enter(page):
    await page.evaluate("location.hash='clases'")
    await expect(page.locator('#classDirectory')).to_be_visible()


async def done(context, state, label):
    global checks
    assert not state['errors'], state['errors']
    assert not state['route_errors'], state['route_errors']
    checks += 1
    print('PASS ' + label, flush=True)
    await context.close()


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=shutil.which('chromium'), headless=True)

        context, page, state, admin, data = await o.fixture(browser)
        old_calls = []

        async def broken_legacy(route):
            if urlparse(route.request.url).path.endswith('portal_course_classes_read'):
                old_calls.append(route.request.post_data_json)
                return await route.fulfill(status=500, content_type='application/json', body=json.dumps({'code': 'XX000', 'message': 'Old RPC fails'}))
            await route.fallback()

        await context.route(h.API + '/**', broken_legacy)
        await enter(page)
        await expect(page.locator('#classDirectoryGroups [data-course]')).to_have_count(16)
        await expect(page.locator('#managementSection')).to_be_hidden()
        await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(0)
        await page.locator('#classDirectoryAll').click()
        await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(134)
        assert not old_calls
        await page.locator('#classDirectoryGroups [data-course="CI-2"]').click()
        await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(9)
        # Una clase posterior a las primeras 50: se conserva exactamente su UUID.
        chosen = data['classes'][129]
        await page.locator('#classDirectorySearch').fill('130')
        await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(1)
        await page.get_by_role('button', name='Inscribir alumno', exact=True).click()
        await expect(page.locator('.class-selection-summary')).to_contain_text(chosen['name'])
        await expect(page.locator('#managementFields input[name=class_id]')).to_have_value(chosen['id'])
        await expect(page.locator('#classPickerPeriod')).to_have_count(0)
        await w.select_ready(page, 'person_id', w.A)
        await page.locator('#managementSave').click()
        await expect(page.locator('#classDirectoryStatus')).to_contain_text('Alumno inscrito')
        assert admin['enrollments'][-1]['class_id'] == chosen['id']
        writes = [body for action, body in admin['calls'] if action == 'write']
        assert writes[-1] == {'p_action': 'enroll', 'p_data': {'class_id': chosen['id'], 'person_id': w.A}}
        admin['people'].append(w.person(h.UID, 'Control Escolar de prueba', 'control_escolar'))
        await page.get_by_role('button', name='Asignar profesor', exact=True).click()
        await expect(page.locator('#admin-person_id')).to_contain_text('Control Escolar de prueba (Control Escolar)')
        await w.select_ready(page, 'person_id', h.UID)
        await page.locator('#managementSave').click()
        await expect(page.locator('#classDirectoryStatus')).to_contain_text('Profesor asignado')
        assert admin['assignments'][-1]['class_id'] == chosen['id']
        assert admin['people'][-1]['role'] == 'control_escolar'
        assert not old_calls
        await done(context, state, '134 clases disponibles aunque falle la RPC anterior; inscripción y docente de Control Escolar conservan clase y rol')

        for mobile in [False, True]:
            context, page, state, admin, data = await o.fixture(browser, mobile)
            spring = copy.deepcopy(data['classes'][1])
            spring.update(id='dc000000-0000-4000-8000-000000009998', period_id=o.PER2, period_name='Ene-May 2027')
            inactive = copy.deepcopy(spring)
            inactive.update(id='dc000000-0000-4000-8000-000000009997', group_code='1F-1', active=False)
            data['classes'].extend([spring, inactive])
            await enter(page)
            await expect(page.locator('#classDirectoryPeriod option')).to_have_count(2)
            tile = page.locator('#classDirectoryGroups [data-course="CI-1"]')
            await expect(tile).to_contain_text('9 clases')
            await tile.focus()
            await page.keyboard.press('Enter')
            await expect(page.locator('#classDirectoryListTitle')).to_have_text('Clases de CI-1')
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.evaluate('scrollTo(0,0)')
            await page.screenshot(path=str(h.ARTIFACTS / f'clases-bloques-{mobile}.png'), full_page=True)
            await page.get_by_role('button', name='Inscribir alumno', exact=True).first.click()
            await expect(page.locator('#admin-person_id')).to_be_enabled()
            assert await page.locator('#managementDialog').evaluate('(d)=>d.scrollWidth<=d.clientWidth && d.getBoundingClientRect().height<=innerHeight')
            await page.screenshot(path=str(h.ARTIFACTS / f'clase-inscribir-{mobile}.png'))
            await page.keyboard.press('Escape')
            await expect(page.locator('#managementDialog')).not_to_be_visible()
            await page.locator('#classDirectoryPeriod').select_option(o.PER2)
            await expect(page.locator('#classDirectoryListTitle')).to_have_text('Elige un curso para ver sus clases')
            await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(0)
            await expect(page.locator('#classDirectoryGroups [data-course="CI-2"]')).to_contain_text('1 clase')
            await page.locator('#classDirectoryGroups [data-course="CI-2"]').click()
            await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(1)
            await expect(page.locator('#classDirectoryList')).to_contain_text('Ene-May 2027')
            await page.locator('#classDirectorySearch').fill('No existe')
            await expect(page.locator('#classDirectoryCount')).to_have_text('0 clases')
            await expect(page.locator('#classDirectoryList')).to_contain_text('búsqueda')
            await page.locator('#classDirectorySearch').fill('')
            await page.locator('#classDirectoryGroups [data-course="1F-1"]').click()
            await expect(page.locator('#classDirectoryCount')).to_have_text('0 clases')
            await page.locator('#classDirectoryInactive').check()
            await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(1)
            await expect(page.get_by_role('button', name='Inscribir alumno', exact=True)).to_be_disabled()
            await expect(page.get_by_role('button', name='Asignar profesor', exact=True)).to_be_disabled()
            await page.locator('#classDirectoryList summary').click()
            await page.get_by_role('button', name='Reactivar clase', exact=True).click()
            await page.locator('#managementSave').click()
            await expect(page.locator('#classDirectoryStatus')).to_contain_text('Estado actualizado')
            await expect(page.get_by_role('button', name='Inscribir alumno', exact=True)).to_be_enabled()
            assert len([call for call in admin['calls'] if call[0] == 'write']) == 1
            await done(context, state, ('Móvil' if mobile else 'Escritorio') + ': bloques con teclado, periodos separados, búsqueda, diálogo, inactivas y reactivación')

        context, page, state, admin, data = await o.fixture(browser)
        data['status'] = 503
        await enter(page)
        await expect(page.locator('#classDirectoryStatus')).to_contain_text('No se pudieron cargar')
        await expect(page.locator('#classDirectoryCreate')).to_be_disabled()
        await expect(page.locator('#classDirectoryCount')).to_have_text('')
        data['status'] = 200
        await page.locator('#classDirectoryRefresh').click()
        await expect(page.locator('#classDirectoryGroups [data-course="CI-1"]')).to_contain_text('9 clases')
        await done(context, state, 'Error de lectura distinguido de una lista vacía y recuperación con Actualizar')

        context, page, state, admin, data = await o.fixture(browser)
        data['gate'] = asyncio.Event()
        await enter(page)
        await data['started'].wait()
        await page.evaluate("location.hash='inicio'")
        data['gate'].set()
        await expect(page.locator('#classDirectory')).to_be_hidden()
        await expect(page.locator('#classDirectoryGroups')).to_be_empty()
        await expect(page.locator('#classDirectoryList')).to_be_empty()
        await done(context, state, 'Navegar descarta respuestas tardías y limpia las clases de pantalla')

        context, page, state, admin, data = await o.fixture(browser)
        await enter(page)
        await expect(page.locator('#classDirectoryAll')).to_be_enabled()
        await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
        await page.get_by_role('button', name='Inscribir alumno', exact=True).first.click()
        await w.select_ready(page, 'person_id', w.A)
        admin['write_status'] = 500
        await page.locator('#managementSave').click()
        await expect(page.locator('#managementFormMessage')).to_contain_text('No se pudo confirmar')
        await expect(page.locator('#managementSave')).to_be_disabled()
        assert len([call for call in admin['calls'] if call[0] == 'write']) == 1
        assert not admin['enrollments']
        await page.locator('#managementCancel').click()
        await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(9)
        await done(context, state, 'Respuesta incierta no reenvía la inscripción ni muestra un éxito falso')

        context, page, state, admin, data = await o.fixture(browser)
        data['classes'][0]['name'] = '<img src=x onerror=alert(1)>'
        await enter(page)
        await expect(page.locator('#classDirectoryAll')).to_be_enabled()
        await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
        await expect(page.locator('#classDirectoryList')).to_contain_text('<img src=x onerror=alert(1)>')
        await expect(page.locator('#classDirectoryList img')).to_have_count(0)
        await done(context, state, 'Los nombres de clases se muestran como texto sin interpretar HTML')

        context, page, state, admin, data = await o.fixture(browser)
        data['status'] = 403
        state['profile'] = {'full_name': 'Profesor de prueba', 'role': 'professor', 'active': True}
        await page.evaluate("location.hash='clases'")
        await expect(page.locator('#profileRole')).to_have_text('Profesor')
        await expect(page.locator('#classDirectory')).to_be_hidden()
        await expect(page.locator('#classDirectoryGroups')).to_be_empty()
        await expect(page.locator('#classDirectoryList')).to_be_empty()
        await done(context, state, 'Acceso denegado vuelve a verificar el rol y retira datos administrativos')

        for role in ['student', 'professor']:
            context, page, state = await h.fixture(browser, profile={'full_name': 'Usuario de prueba', 'role': role, 'active': True})
            await expect(page.locator('#panelContent')).to_be_visible()
            await page.evaluate("location.hash='clases'; PortalClassDirectory.openRoute()")
            await expect(page.locator('#classDirectory')).to_be_hidden()
            assert not any('/rpc/portal_course_board_read' in url for method, url in state['requests'])
            await done(context, state, role + ': la sección administrativa no se abre ni consulta clases')

        await browser.close()
    print(f'PASS {checks} escenarios de Clases por curso.', flush=True)


if __name__ == '__main__':
    h.prepare()
    try:
        asyncio.run(main())
    finally:
        h.server.shutdown()
        h.server.server_close()
        h.TEMP.cleanup()
