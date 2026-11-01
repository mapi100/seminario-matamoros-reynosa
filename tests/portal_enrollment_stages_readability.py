"""Filtros por trayectoria del periodo y legibilidad; SDK real, API simulada."""
import asyncio,copy,shutil
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_workspace as w
import portal_batch_and_professors as b
import portal_learning as learning

EXTRA='91000000-0000-4000-8000-000000000038'
PER2='96000000-0000-4000-8000-000000000001'
CL2='96000000-0000-4000-8000-000000000002'
checks=0

async def fixture(browser,mobile=False):
    c,page,state,data=await b.fixture(browser,mobile)
    data['people'].append(w.person(EXTRA,'Seminarista sin etapa','student'))
    students=[u for u in data['people'] if u['role']=='student']
    students[1]['full_name']='Aarón ficticio';students[9]['full_name']='Zacarías ficticio'
    for index,user in enumerate(students):
        stage,semester=('introductorio',1) if index<10 else ('introductorio',2) if index<15 else ('filosofia',3) if index<23 else ('teologia',5) if index<31 else (None,None)
        data['formations'].append({'id':user['id'],'period_id':w.period(7)['id'],'stage_code':stage,'semester':semester})
    return c,page,state,data

async def done(c,state,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors']
    checks+=1;print('PASS '+label,flush=True);await c.close()

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for mobile in [False,True]:
            c,page,state,data=await fixture(browser,mobile)
            # La trayectoria se pagina completa, incluso si hay personas históricas fuera de los candidatos.
            data['formations'].extend({'id':f'95000000-0000-4000-8000-{i:012d}','period_id':w.period(7)['id'],'stage_code':'filosofia','semester':2} for i in range(1,121))
            await b.open_batch(page)
            await expect(page.locator('#batchEnrollmentStage')).to_have_value('introductorio')
            await expect(page.locator('#batchEnrollmentSemester')).to_have_value('1')
            await expect(page.locator('#batchEnrollmentList input')).to_have_count(10)
            await expect(page.locator('#batchEnrollmentList .batch-enrollment-person strong').first).to_have_text('Aarón ficticio')
            await expect(page.locator('#batchEnrollmentList .batch-enrollment-person strong').last).to_have_text('Zacarías ficticio')
            assert [call['p_offset'] for call in data['formation_calls']]==[0,100]
            assert all(call['p_period']==w.period(7)['id'] for call in data['formation_calls'])
            await page.locator('#batchEnrollmentSelectAll').click();await expect(page.locator('#batchEnrollmentCount')).to_contain_text('9 seleccionados')
            await page.locator('#batchEnrollmentStage').select_option('filosofia')
            await expect(page.locator('#batchEnrollmentSemester option')).to_have_count(7)
            await expect(page.locator('#batchEnrollmentList input')).to_have_count(8)
            await expect(page.locator('#batchEnrollmentCount')).to_contain_text('9 fuera del filtro')
            await page.locator('#batchEnrollmentSemester').select_option('1');await expect(page.locator('#batchEnrollmentList')).to_contain_text('No hay alumnos')
            await page.locator('#batchEnrollmentSemester').select_option('3');await expect(page.locator('#batchEnrollmentList input')).to_have_count(8)
            await page.locator('#batchEnrollmentStage').select_option('teologia');await expect(page.locator('#batchEnrollmentSemester option')).to_have_count(9)
            await page.locator('#batchEnrollmentSemester').select_option('5');await expect(page.locator('#batchEnrollmentList input')).to_have_count(8)
            await page.locator('#batchEnrollmentAllStages').click();await expect(page.locator('#batchEnrollmentList input')).to_have_count(39)
            await expect(page.locator('#batchEnrollmentList .batch-enrollment-group')).to_have_count(5)
            await expect(page.locator('#batchEnrollmentList .batch-enrollment-group').last).to_contain_text('Sin etapa asignada')
            await page.locator('#batchEnrollmentStage').select_option('none');await expect(page.locator('#batchEnrollmentList input')).to_have_count(8)
            await page.locator('#batchEnrollmentStage').select_option('introductorio');await page.locator('#batchEnrollmentSemester').select_option('1')
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert await page.locator('#batchEnrollmentDialog').evaluate('(d)=>d.scrollWidth<=d.clientWidth')
            assert await page.locator('#batchEnrollmentSave').evaluate('(b)=>{const r=b.getBoundingClientRect(),d=b.closest("dialog").getBoundingClientRect();return r.top>=d.top && r.bottom<=d.bottom && r.bottom<=innerHeight}')
            await page.screenshot(path=str(h.ARTIFACTS/f'inscripcion-etapas-{mobile}.png'))
            await page.locator('#batchEnrollmentSearch').fill('aaron');await expect(page.locator('#batchEnrollmentList input')).to_have_count(1)
            await expect(page.locator('#batchEnrollmentCount')).to_contain_text('8 fuera del filtro')
            await page.locator('#batchEnrollmentSave').click();await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible()
            assert data['batch_calls']==[{'p_class':w.CL,'p_students':b.IDS[:9]}]
            await expect(page.locator('#classDirectoryStatus')).to_contain_text('8 nuevos · 1 reactivado')
            await done(c,state,('Móvil' if mobile else 'Escritorio')+': CI-1 propuesto, etapas/semestres/nombre, orden alfabético, 159 trayectorias paginadas y selección del grupo en una llamada')

        c,page,state,data=await fixture(browser)
        second={**data['classes'][0],'id':CL2,'period_id':PER2,'period_name':'Otro periodo ficticio','group_code':'2F-3'}
        data['classes'].append(second)
        data['formations'].extend({'id':uid,'period_id':PER2,'stage_code':'filosofia','semester':3} for uid in [w.A,b.IDS[0]])
        await w.nav(page,'clases');await page.evaluate('(row)=>PortalEnrollmentBatch.open(row)',second)
        await expect(page.locator('#batchEnrollmentStage')).to_have_value('filosofia');await expect(page.locator('#batchEnrollmentSemester')).to_have_value('3')
        await expect(page.locator('#batchEnrollmentList input')).to_have_count(2)
        assert data['formation_calls'][-1]['p_period']==PER2
        await done(c,state,'La etapa corresponde al periodo de la clase; no se reutiliza la del semestre anterior')

        c,page,state,data=await fixture(browser);data['formations']=[]
        await b.open_batch(page);await expect(page.locator('#batchEnrollmentStage')).to_have_value('none')
        await expect(page.locator('#batchEnrollmentList input')).to_have_count(39)
        await expect(page.locator('#batchEnrollmentFormationHelp')).to_contain_text('39 sin etapa')
        assert not data['batch_calls']
        await done(c,state,'Sin trayectorias registradas se identifican los pendientes y no se inventan etapas')

        c,page,state,data=await fixture(browser);data['formation_status']=503
        await b.open_batch(page);await expect(page.locator('#batchEnrollmentStatus')).to_contain_text('No se pudieron cargar')
        await expect(page.locator('#batchEnrollmentSave')).to_be_disabled();await expect(page.locator('#batchEnrollmentList input')).to_have_count(0)
        data['formation_status']=200;await page.locator('#batchEnrollmentRefresh').click()
        await expect(page.locator('#batchEnrollmentStage')).to_have_value('introductorio');await expect(page.locator('#batchEnrollmentList input')).to_have_count(10)
        await done(c,state,'Un fallo al consultar etapas se distingue de alumnos sin etapa y permite reintentar')

        c,page,state,data=await fixture(browser);data['formation_gate']=asyncio.Event()
        await b.open_batch(page);await data['formation_started'].wait();await page.evaluate("location.hash='inicio'");data['formation_gate'].set()
        await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible();await expect(page.locator('#batchEnrollmentStage option')).to_have_count(0)
        await expect(page.locator('#batchEnrollmentList')).to_be_empty()
        await done(c,state,'Una respuesta tardía de trayectorias no repuebla un diálogo cerrado')

        for role in ['student','professor']:
            for mobile in [False,True]:
                c,page,state,data=await learning.fixture(browser,role,mobile=mobile)
                await expect(page.locator('#panelContent')).to_be_visible()
                await expect(page.locator('body')).to_have_attribute('data-portal-role',role)
                font=await page.locator('#workspaceNav [data-route="inicio"]').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')
                assert font==(16 if mobile else 17),font
                selector='#subjectsList .subject-name' if role=='student' else '#teachingList .teaching-name'
                await expect(page.locator(selector).first).to_be_visible()
                assert await page.locator(selector).first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')>=(18 if mobile else 20)
                assert await page.locator('.dashboard-welcome h2').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')>=28
                if mobile:
                    await page.locator('#menuToggle').click();await expect(page.locator('#workspaceNav')).to_have_class(__import__('re').compile('menu-open'))
                    await page.locator('#menuToggle').click()
                else:
                    ys=await page.locator('#workspaceNav nav a:visible').evaluate_all('(links)=>links.map(a=>a.getBoundingClientRect().top)');assert max(ys)-min(ys)<1
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                await page.screenshot(path=str(h.ARTIFACTS/f'legibilidad-{role}-{mobile}.png'),full_page=True)
                await page.evaluate('(id)=>location.hash="curso/"+id+"/inicio"',learning.COURSE)
                await expect(page.locator('.learning-course-nav')).to_be_visible()
                assert await page.locator('.learning-course-nav a').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')>=(15 if mobile else 16)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                # La hoja está limitada a pantalla: las emisiones y la impresión conservan sus estilos.
                await page.emulate_media(media='print')
                assert await page.locator('link[href^="readability.css"]').get_attribute('media')=='screen'
                await page.emulate_media(media='screen')
                await done(c,state,role+(' móvil' if mobile else ' escritorio')+': textos mayores, menú, cursos y aula sin desbordamiento')
        await browser.close()
    print('PASS '+str(checks)+' escenarios de filtros por etapa y legibilidad.',flush=True)

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
