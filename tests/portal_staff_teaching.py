"""Cursos propios del personal: SDK real, datos ficticios y ninguna escritura real."""
import asyncio
import shutil
from playwright.async_api import async_playwright, expect
import portal_subjects as h
import portal_learning as l
import portal_school_workflow as school


def assignments():
    rows=[]
    for i,name in enumerate(['Seminario de Tesis I','Pentateuco','Cartas Paulinas','Seminario de Tesis II','Evangelios Sinópticos'],1):
        row=h.subject(i,name=name)
        row.update(professor_id=h.UID,active=True)
        if i>3:
            row['academic_periods'].update(name='Ene-May 2027',starts_on='2027-01-01',ends_on='2027-05-31')
        rows.append(row)
    other=h.subject(6,name='Curso de otro profesor');other.update(professor_id=l.OTHER,active=True)
    inactive=h.subject(7,name='Asignación dada de baja');inactive.update(professor_id=h.UID,active=False)
    return rows+[other,inactive]


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for mobile in [False,True]:
            c,page,state,learning,board,extra=await school.fixture(browser,mobile)
            state['teaching']=assignments()
            await page.reload()
            await expect(page.locator('#controlHome')).to_be_visible()
            await expect(page.locator('#teachingSection')).to_be_hidden()
            await school.courses(page)
            await expect(page.locator('#teachingSection')).to_be_visible()
            await expect(page.locator('.teaching-card')).to_have_count(5)
            await expect(page.locator('#teachingTitle')).to_have_text('Mis cursos como profesor')
            assert all(r['query']['professor_id']==['eq.'+h.UID] for r in state['teaching_requests'])
            assert await page.locator('#classDirectory').evaluate('(directory)=>directory.nextElementSibling.id')=='teachingSection'
            assert await page.locator('#teachingSection').evaluate('(el)=>el.getBoundingClientRect().top>=document.getElementById("classDirectory").getBoundingClientRect().bottom')
            assert 'Curso de otro profesor' not in await page.locator('#teachingList').inner_text()
            assert 'Asignación dada de baja' not in await page.locator('#teachingList').inner_text()
            await page.locator('#teacherPeriod').select_option('Ene-May 2027')
            await expect(page.locator('.teaching-card:visible')).to_have_count(2)
            await page.locator('#teacherPeriod').select_option('Periodo de prueba 2026')
            await expect(page.locator('.teaching-card:visible')).to_have_count(3)
            # Conservar las tarjetas personales al cambiar el bloque del directorio general.
            await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
            await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(9)
            await expect(page.locator('.teaching-card:visible')).to_have_count(3)
            await page.evaluate("document.documentElement.dataset.theme='oled';document.documentElement.dataset.themeTone='dark'")
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.evaluate('document.activeElement.blur();scrollTo(0,0)')
            await page.screenshot(path=str(h.ARTIFACTS/f'cursos-propios-{mobile}.png'),full_page=True)
            await page.locator('#teachingSection').screenshot(path=str(h.ARTIFACTS/f'tarjetas-propias-{mobile}.png'))
            await page.locator('#teachingList .course-enter').first.click()
            await expect(page).to_have_url(h.BASE+'/portal/panel.html#curso/'+l.COURSE+'/inicio')
            await expect(page.get_by_role('navigation',name='Herramientas del curso').get_by_role('link',name='Calificaciones',exact=True)).to_be_visible()
            await expect(page.locator('#teachingSection')).to_be_hidden()
            # Volver lleva al directorio completo y conserva las tarjetas propias.
            await page.locator('.learning-back').click()
            await expect(page.locator('#teachingSection')).to_be_visible()
            await expect(page.locator('#classDirectory')).to_be_visible()
            await page.evaluate("location.hash='inicio'")
            await expect(page.locator('#teachingSection')).to_be_hidden()
            assert not state['errors'] and not state['route_errors'] and not learning['errors'],(state['errors'],state['route_errors'],learning['errors'])
            assert not extra['writes'] and not learning['writes']
            await c.close()
            print('PASS cursos propios + acceso general + filtros + aula '+('móvil' if mobile else 'escritorio'),flush=True)

        c,page,state,learning,board,extra=await school.fixture(browser)
        await school.courses(page)
        await expect(page.locator('#teachingStatus')).to_contain_text('Todavía no tienes materias asignadas')
        await expect(page.locator('#classDirectoryGroups [data-course]')).to_have_count(16)
        state['teaching_status']=500
        await page.reload()
        await expect(page.locator('#teachingRetry')).to_be_visible()
        await expect(page.locator('#classDirectoryGroups [data-course]')).to_have_count(16)
        state['teaching_status']=200;state['teaching']=assignments()
        await page.locator('#teachingRetry').click()
        await expect(page.locator('.teaching-card')).to_have_count(5)
        # El cambio de rol vuelve a validar el acceso y restaura la ubicación de profesores.
        state['profile']['role']='professor'
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await expect(page.locator('#profileRole')).to_have_text('Profesor')
        await expect(page.locator('#classDirectory')).to_be_hidden()
        await expect(page.locator('#teachingTitle')).to_have_text('Mis cursos')
        await expect(page.locator('.teaching-card')).to_have_count(5)
        assert await page.locator('#teachingSection').evaluate('(el)=>el.previousElementSibling.id')=='subjectsSection'
        assert not state['errors'] and not state['route_errors'] and not learning['errors']
        await c.close()
        print('PASS sin asignaciones + error/reintento + cambio de rol sin perder permisos',flush=True)
        await browser.close()


if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
