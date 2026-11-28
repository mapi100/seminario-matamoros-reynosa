"""Filtros y avisos del portal en Chromium, con API simulada y datos ficticios."""
import asyncio
import json
import shutil
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

import portal_subjects as portal
import portal_workspace as workspace


def person(number, name, role, active=True):
    row = workspace.person(f'c0040000-0000-4000-8000-{number:012d}', name, role)
    row.update(active=active, email=f'cuenta{number}@example.invalid')
    return row


def notice(number, kind='final_corrected', name='Seminarista de prueba', actor='Profesor de prueba'):
    return {
        'id': number, 'student_name': name, 'kind': kind, 'read': False,
        'created_at': '2026-11-27T17:00:00Z',
        'subject_name': 'Catecismo I' if kind != 'personal_updated' else None,
        'period_name': 'AGO-DIC 2026' if kind != 'personal_updated' else None,
        'actor_name': name if kind == 'personal_updated' else actor
    }


async def setup(browser, mobile=False, role='control_escolar'):
    context, page, base, directory = await workspace.fixture(browser, mobile=mobile)
    base['profile']['role'] = role
    directory['people'] = [
        *[person(n, f'Seminarista {n:02d}', 'student', active=n != 36) for n in range(1, 37)],
        person(40, 'Profesor Sol', 'professor'), person(41, 'Profesor Luna', 'professor', False),
        person(42, 'Control Uno', 'control_escolar'), person(43, 'Control Dos', 'control_escolar')
    ]
    directory['events'] = [{
        'id': 'c0050000-0000-4000-8000-000000000001', 'action': 'assignment_state',
        'actor_name': 'Control de prueba', 'created_at': '2026-11-27T17:45:00Z'
    }]
    state = {
        'notes': [notice(n) for n in range(1, 22)] + [
            notice(22, actor=None),
            notice(23, actor='<img src=x onerror=alert(1)>'),
            notice(24, kind='personal_updated', name='Seminarista Dos')],
        'calls': [], 'marks': [], 'gate': None, 'started': asyncio.Event(), 'denied': False, 'mark_error': False
    }

    async def api(route):
        resource = urlparse(route.request.url).path.rsplit('/', 1)[-1]
        if resource not in ['portal_people_by_role', 'portal_control_activity_read', 'portal_control_activity_mark']:
            return await route.fallback()
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Content-Type': 'application/json'}
        if route.request.method == 'OPTIONS':
            return await route.fulfill(status=204, headers=headers)
        args = route.request.post_data_json
        state['calls'].append((resource, args))

        async def reply(body, status=200):
            if not page.is_closed():
                await route.fulfill(status=status, headers=headers, body=json.dumps(body))

        if state['denied']:
            base['profile']['role'] = 'professor'
            return await reply({'code': '42501', 'message': 'Revocado'}, 403)
        if resource == 'portal_people_by_role':
            if args['p_role'] == 'professor' and state['gate']:
                state['started'].set()
                await state['gate'].wait()
            needle = args['p_search'].casefold()
            rows = [p for p in directory['people'] if p['role'] == args['p_role'] and
                    needle in (p['full_name'] + ' ' + p['email']).casefold()]
            start = args['p_offset']
            end = start + args['p_limit']
            return await reply({'items': rows[start:end], 'has_more': len(rows) > end})
        if resource == 'portal_control_activity_mark':
            state['marks'].append(args)
            if state['mark_error']:
                return await reply({'code': 'XX000', 'message': 'Sin confirmar'}, 500)
            for item in state['notes']:
                if args['p_all'] or args['p_notice_id'] == item['id']:
                    item['read'] = True
            return await reply({'saved': True, 'unread': sum(not item['read'] for item in state['notes'])})

        cursor = args['p_before']
        rows = [item for item in reversed(state['notes']) if cursor is None or item['id'] < cursor]
        batch = [] if args['p_count_only'] else rows[:20]
        return await reply({
            'unread': sum(not item['read'] for item in state['notes']),
            'items': batch, 'next_before': batch[-1]['id'] if batch and len(rows) > 20 else None
        })

    await context.route(portal.API + '/**', api)
    await page.reload(wait_until='domcontentloaded')
    await expect(page.locator('#panelContent')).to_be_visible()
    return context, page, base, state


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=shutil.which('chromium'), headless=True)
        context, page, base, data = await setup(browser)
        bell = page.locator('#activityNoticeBell')
        badge = page.locator('#activityNoticeBadge')
        await expect(badge).to_have_text('24')
        assert any(args['p_count_only'] for name, args in data['calls'] if name == 'portal_control_activity_read')
        await page.locator('#workspaceNav [data-route="personas"]').click()
        filters = page.locator('#peopleRoleFilters')
        results = page.locator('#managementList li')
        search = page.get_by_role('searchbox', name='Buscar personas')
        await expect(filters.get_by_role('button', name='Todos', exact=True)).to_have_attribute('aria-pressed', 'true')
        await expect(results).to_have_count(30)
        await filters.get_by_role('button', name='Profesores', exact=True).click()
        await expect(results).to_have_count(2)
        await expect(results.last).to_contain_text('Inactivo')
        await search.fill('cuenta41@')
        await search.press('Enter')
        await expect(results).to_have_count(1)
        await expect(results.first).to_contain_text('Profesor Luna')
        await filters.get_by_role('button', name='Seminaristas', exact=True).click()
        await expect(page.locator('#managementMessage')).to_contain_text('No hay personas')
        await search.fill('')
        await search.press('Enter')
        await expect(results).to_have_count(30)
        await search.fill('Texto todavía no buscado')
        await page.locator('#managementMore').click()
        await expect(results).to_have_count(36)
        await expect(results.last).to_contain_text('Inactivo')
        assert data['calls'][-1][1]['p_search'] == ''
        await search.fill('')
        data['gate'] = asyncio.Event()
        await filters.get_by_role('button', name='Profesores', exact=True).click()
        await data['started'].wait()
        await filters.get_by_role('button', name='Control Escolar', exact=True).click()
        await expect(results).to_have_count(2)
        data['gate'].set()
        await expect(results.first).to_contain_text('Control Uno')
        print('PASS filtros en todo el directorio, inactivos, búsqueda, paginación y cambios rápidos de rol')

        await bell.click()
        await expect(filters).to_be_hidden()
        await expect(page.locator('#activityNoticePanel')).to_be_visible()
        await expect(page.locator('#activityHistoryTitle')).to_have_text('Historial administrativo')
        await expect(results).to_contain_text('Asignación actualizada')
        notices = page.locator('#activityNoticeList li')
        await expect(notices).to_have_count(20)
        await expect(notices.first).to_contain_text('Datos personales actualizados')
        await expect(notices.first).to_contain_text('Seminarista Dos actualizó')
        await expect(notices.nth(1)).to_contain_text('<img src=x')
        assert await notices.nth(1).locator('img').count() == 0
        await expect(notices.nth(2)).to_contain_text('Autor sin identificar')
        await expect(notices.nth(3)).to_contain_text('Cambio hecho por Profesor de prueba')
        await expect(badge).to_have_text('24')
        await notices.first.get_by_role('button', name='Marcar como leído').click()
        await expect(badge).to_have_text('23')
        await expect(notices.first).to_have_attribute('data-unread', 'false')
        await page.get_by_role('button', name='Mostrar más avisos').click()
        await expect(notices).to_have_count(24)
        await page.get_by_role('button', name='Marcar todo como leído').click()
        await expect(badge).to_be_hidden()
        await expect(notices).to_have_count(24)
        await expect(page.locator('#activityNoticeList li[data-unread="true"]')).to_have_count(0)
        await expect(page.get_by_role('button', name='Marcar todo como leído')).to_be_disabled()

        data['notes'].append(notice(25, kind='final_pending', actor='Control Uno'))
        await bell.click()
        await expect(badge).to_have_text('1')
        await expect(notices.first).to_contain_text('Calificación final devuelta a pendiente')
        await expect(notices.first).to_contain_text('Cambio hecho por Control Uno')
        data['mark_error'] = True
        await page.get_by_role('button', name='Marcar todo como leído').click()
        await expect(page.locator('#activityNoticeStatus')).to_contain_text('No se pudo confirmar')
        await expect(badge).to_have_text('1')
        await page.get_by_role('button', name='Actualizar avisos').click()
        await expect(page.locator('#activityNoticeRetry')).to_be_hidden()
        assert data['marks'][:2] == [{'p_notice_id': 24, 'p_all': False}, {'p_notice_id': None, 'p_all': True}]
        print('PASS aviso individual, marcar todo sin borrar, reintento y avisos nuevos en Actividad')
        data['denied'] = True
        await bell.click()
        await expect(bell).to_be_hidden()
        await expect(page.locator('#activityNoticeList li')).to_have_count(0)
        await expect(page.locator('#profileRole')).to_have_text('Profesor')
        assert not base['errors'] and not base['route_errors'], (base['errors'], base['route_errors'])
        await context.close()

        context, page, base, _ = await setup(browser, mobile=True)
        await page.set_viewport_size({'width': 320, 'height': 844})
        await expect(page.locator('#activityNoticeBadge')).to_have_text('24')
        await page.locator('#activityNoticeBell').click()
        await expect(page.locator('#activityNoticeList li')).to_have_count(20)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.evaluate('location.hash = "personas"')
        await expect(page.locator('#peopleRoleFilters')).to_be_visible()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not base['errors'], base['errors']
        await context.close()

        for role in ['student', 'professor']:
            context, page, base, data = await setup(browser, role=role)
            await page.evaluate('location.hash = "actividad"')
            await expect(page.locator('#activityNoticeBell')).to_be_hidden()
            await expect(page.locator('#activityNoticePanel')).to_be_hidden()
            assert not data['calls'] and not base['errors'], (data['calls'], base['errors'])
            await context.close()
        print('PASS móvil estrecho, revocación de acceso y sin avisos ni consultas para otros roles')
        await browser.close()


if __name__ == '__main__':
    portal.prepare()
    try:
        asyncio.run(main())
    finally:
        portal.server.shutdown()
        portal.server.server_close()
        portal.TEMP.cleanup()
