"""Flujo por grupo en Chromium, con API simulada y un Excel real."""
import asyncio
import copy
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook
from playwright.async_api import async_playwright, expect

import portal_kardex as kardex
import portal_subjects as portal

PERIOD = 'b0000000-0000-4000-8000-000000000001'
OTHER_PERIOD = 'b0000000-0000-4000-8000-000000000002'
STUDENTS = [kardex.STUDENT, 'b0010000-0000-4000-8000-000000000002', 'b0010000-0000-4000-8000-000000000003']
COURSES = ['b0020000-0000-4000-8000-000000000001', 'b0020000-0000-4000-8000-000000000002']
ENROLLMENTS = ['b0030000-0000-4000-8000-' + str(i).zfill(12) for i in range(1, 5)]


def sample():
    return {
        'period_id': PERIOD, 'group_code': 'CI-1', 'token': 'a' * 32, 'outside_count': 1,
        'students': [
            {'id': STUDENTS[0], 'name': 'Seminarista Alfa', 'student_number': '0001', 'editable': True},
            {'id': STUDENTS[1], 'name': '=2+3', 'student_number': '0002', 'editable': False},
            {'id': STUDENTS[2], 'name': 'José de prueba', 'student_number': None, 'editable': True}
        ],
        'courses': [
            {'id': COURSES[0], 'name': 'Catecismo I', 'active': True},
            {'id': COURSES[1], 'name': 'Introducción a la Biblia', 'active': True}
        ],
        'cells': [
            {'enrollment_id': enrollment, 'student_id': STUDENTS[i // 2], 'course_id': COURSES[i % 2],
             'score': value, 'editable': i < 2, 'requires_reason': value is not None}
            for i, (enrollment, value) in enumerate(zip(ENROLLMENTS, [90, None, 65, 80]))
        ]
    }


async def fixture(browser, role='control_escolar', mobile=False):
    context, page, state, individual = await kardex.fixture(browser, role=role, mobile=mobile)
    data = {'calls': [], 'writes': [], 'snapshot': sample(), 'conflict': False, 'deny': False}
    async def api(route):
        uri = urlparse(route.request.url).path
        resource = uri.rsplit('/', 1)[-1]
        if resource not in ['portal_group_final_grades_read', 'portal_group_final_grades_save']:
            return await route.fallback()
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Content-Type': 'application/json'}
        if route.request.method == 'OPTIONS':
            return await route.fulfill(status=204, headers=headers)
        args = route.request.post_data_json
        data['calls'].append((resource, args))
        async def reply(body, status=200):
            await route.fulfill(status=status, headers=headers, body=json.dumps(body))
        if data['deny']:
            state['profile']['role'] = 'professor'
            return await reply({'code': '42501', 'message': 'Acceso revocado'}, 403)
        if resource.endswith('_save'):
            data['writes'].append(args)
            if data['conflict']:
                data['snapshot']['cells'][0]['score'] = 96
                data['snapshot']['token'] = 'e' * 32
                return await reply({'code': 'PT409', 'message': 'El grupo o sus notas cambiaron. Actualiza.'}, 409)
            assert args['p_token'] == data['snapshot']['token'] and args['p_confirmed'] is True
            for change in args['p_items']:
                cell = next(x for x in data['snapshot']['cells'] if x['enrollment_id'] == change['enrollment_id'])
                cell.update(score=change['score'], requires_reason=True)
            data['snapshot']['token'] = 'b' * 32
            return await reply({'saved': True, 'snapshot': data['snapshot'], 'changed': len(args['p_items'])})

        chosen = args['p_period'] or PERIOD
        groups = [{'code': 'CI-1', 'stage': 'Introductorio'}, {'code': 'CI-2', 'stage': 'Introductorio'}] if chosen == PERIOD else []
        snapshot = copy.deepcopy(data['snapshot']) if groups else None
        if snapshot and args['p_group'] == 'CI-2':
            snapshot.update(group_code='CI-2', students=[], cells=[], outside_count=0, token='c' * 32)
        return await reply({'periods': [{'id': PERIOD, 'name': 'AGO-DIC 2026'}, {'id': OTHER_PERIOD, 'name': 'ENE-MAY 2027'}],
                            'period_id': chosen, 'groups': groups, 'snapshot': snapshot})
    await context.route(portal.API + '/**', api)
    return context, page, state, individual, data


async def open_group(page):
    await page.locator('#workspaceNav [data-route="kardex"]').click()
    await expect(page.locator('#kardexByGroup')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('#groupFinalTable tbody tr')).to_have_count(3)


async def export_check(page):
    async with page.expect_download() as pending:
        await page.get_by_role('button', name='Descargar Excel', exact=True).click()
    download = await pending.value
    assert download.suggested_filename == 'Calificaciones_CI-1_AGO-DIC_2026.xlsx'
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / download.suggested_filename
        await download.save_as(path)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
        wb = load_workbook(path)
        assert wb.sheetnames == ['Calificaciones', 'Estadísticas']
        sheet = wb['Calificaciones']
        assert sheet.freeze_panes == 'C4' and sheet.auto_filter.ref == 'A3:E6'
        assert list(sheet.values)[3:] == [
            ('Seminarista Alfa', '0001', 9, 'Pendiente', 'Pendiente'),
            ('=2+3', '0002', 6.5, 8, 7.3),
            ('José de prueba', None, 'Sin inscripción', 'Sin inscripción', 'Pendiente')
        ]
        assert sheet['A5'].data_type == 's'
        assert sheet['C5'].data_type == 'n' and sheet['C5'].fill.fgColor.rgb == 'FFFFE8EA'
        summary = wb['Estadísticas']
        assert summary['B3'].value == 7.3
        assert [summary[f'B{i}'].value for i in range(4, 8)] == [3, 2, 1, 1]
        assert [summary.cell(12, i).value for i in range(1, 7)] == ['Introducción a la Biblia', 8, 1, 1, 0, 1]
        wb.close()


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=shutil.which('chromium'), headless=True)
        context, page, state, individual, data = await fixture(browser)
        await open_group(page)
        await expect(page.locator('#groupFinalTable .group-grade-failed')).to_have_text('6.5')
        await expect(page.locator('#groupFinalTable .group-grade-pending')).to_have_text('Pendiente')
        await expect(page.locator('#groupFinalNotice')).to_contain_text('inscripciones fuera de este grupo')
        await export_check(page)
        assert not data['writes']
        print('PASS grupo visible, estados distintos y Excel de dos hojas con notas numéricas', flush=True)

        await page.get_by_role('button', name='Editar finales', exact=True).click()
        inputs = page.locator('#groupFinalTable input')
        await expect(inputs).to_have_count(2)
        await inputs.nth(0).fill('11')
        await expect(page.locator('#groupFinalReview')).to_be_disabled()
        await expect(inputs.nth(0)).to_have_attribute('aria-invalid', 'true')
        await inputs.nth(0).fill('9,4')
        await inputs.nth(1).fill('0')
        await expect(page.locator('#groupFinalDraftStatus')).to_have_text('2 cambios sin publicar')
        await expect(page.locator('#groupFinalExcel')).to_be_disabled()
        assert not data['writes']
        await page.locator('#groupFinalReview').click()
        modal = page.get_by_role('dialog', name='Confirmar calificaciones finales')
        await expect(modal).to_contain_text('Catecismo I · 9.0 → 9.4')
        await expect(modal).to_contain_text('Introducción a la Biblia · Pendiente → 0.0')
        await modal.get_by_role('button', name='Volver').click()
        await expect(inputs.nth(0)).to_have_value('9,4')
        await page.locator('#groupFinalReview').click()
        confirm = modal.get_by_role('checkbox')
        publish = modal.get_by_role('button', name='Publicar 2 finales')
        await confirm.check()
        await expect(publish).to_be_disabled()
        await modal.get_by_role('textbox', name='Motivo de la captura o corrección').fill('Acta revisada por el docente')
        await publish.click()
        await expect(page.locator('#groupFinalStatus')).to_have_text('Calificaciones finales publicadas.')
        assert len(data['writes']) == 1
        assert data['writes'][0]['p_items'] == [
            {'enrollment_id': ENROLLMENTS[0], 'score': 94}, {'enrollment_id': ENROLLMENTS[1], 'score': 0}
        ]
        await expect(page.locator('#groupFinalTable tbody tr').first).to_contain_text('4.7')
        print('PASS corrección y nota pendiente de materias distintas, con motivo y confirmación', flush=True)

        data['conflict'] = True
        await page.locator('#groupFinalEdit').click()
        await inputs.nth(0).fill('9.5')
        await page.locator('#groupFinalReview').click()
        await modal.get_by_role('textbox', name='Motivo de la captura o corrección').fill('Acta corregida por el docente')
        await modal.get_by_role('checkbox').check()
        await modal.get_by_role('button', name='Publicar 1 final').click()
        await expect(modal.get_by_role('status')).to_contain_text('cambiaron')
        await expect(modal.get_by_role('button', name='Publicar 1 final')).to_be_disabled()
        await modal.get_by_role('button', name='Cerrar y actualizar').click()
        await expect(page.locator('#groupFinalTable tbody tr').first).to_contain_text('9.6')
        assert len(data['writes']) == 2

        await page.locator('#groupFinalGroup').select_option('CI-2')
        await expect(page.locator('#groupFinalNotice')).to_contain_text('no hay seminaristas')
        await page.locator('#groupFinalPeriod').select_option(OTHER_PERIOD)
        await expect(page.locator('#groupFinalStatus')).to_contain_text('no tiene grupos')
        await expect(page.locator('#groupFinalTable')).to_be_hidden()

        await page.locator('#kardexByStudent').click()
        await expect(page.locator('#kardexStudents li')).to_have_count(2)
        await page.locator('#kardexByGroup').click()
        await expect(page.locator('#groupFinalTable tbody tr')).to_have_count(3)
        await page.evaluate('(id) => PortalKardex.requestStudent(id)', kardex.STUDENT)
        await expect(page.locator('#kardexByStudent')).to_have_attribute('aria-pressed', 'true')
        await expect(page.locator('#kardexPreview')).to_contain_text('KARDEX ACADÉMICO')
        assert not state['errors'] and not state['route_errors'], (state['errors'], state['route_errors'])
        print('PASS conflicto recuperable, periodos aislados y acceso a kardex individual', flush=True)
        await context.close()

        context, page, state, _, data = await fixture(browser, mobile=True)
        await page.evaluate('location.hash = "kardex"')
        await expect(page.locator('#groupFinalTable tbody tr')).to_have_count(3)
        assert await page.locator('#groupFinalTable').evaluate('e => e.scrollWidth > e.clientWidth')
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.locator('#groupFinalEdit').click()
        await page.locator('#groupFinalTable input').first.fill('8.5')
        page.once('dialog', lambda dialog: dialog.dismiss())
        await page.locator('#kardexByStudent').click()
        await expect(page.locator('#groupFinalDraftStatus')).to_have_text('1 cambio sin publicar')
        page.once('dialog', lambda dialog: dialog.dismiss())
        await page.evaluate('location.hash = "inicio"')
        await expect(page.locator('body')).to_have_attribute('data-view', 'kardex')
        await expect(page).to_have_url(re.compile(r'#kardex$'))
        await page.locator('#groupFinalTable input').first.fill('9.0')
        await page.locator('#groupFinalCancel').click()
        data['deny'] = True
        downloads = []
        page.on('download', lambda download: downloads.append(download))
        await page.locator('#groupFinalExcel').click()
        await expect(page.locator('#groupFinalTable')).to_be_hidden()
        assert not downloads
        assert not data['writes'] and not state['errors'], (data['writes'], state['errors'])
        print('PASS tabla móvil, descarte explícito de edición y exportación bloqueada al revocar acceso', flush=True)
        await context.close()

        for role in ['student', 'professor']:
            context, page, state, _, data = await fixture(browser, role=role)
            await page.evaluate('location.hash = "kardex"')
            await expect(page.locator('#kardexByGroup')).to_be_hidden()
            assert not data['calls'], data['calls']
            await context.close()
        print('PASS sin vista ni consultas de grupo desde seminarista o profesor', flush=True)
        await browser.close()


if __name__ == '__main__':
    portal.prepare()
    try:
        asyncio.run(main())
    finally:
        portal.server.shutdown()
        portal.server.server_close()
        portal.TEMP.cleanup()
