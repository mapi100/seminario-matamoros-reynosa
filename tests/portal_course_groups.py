"""Cursos CI/F/T visibles; API simulada, SDK real, sin datos de producción."""
import asyncio,json,shutil,os
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_learning as l
import portal_workspace as w

async def mock_groups(context,rows,save_status=200,class_rows=None):
    state={'items':rows,'writes':[]}
    async def route(req):
        path=urlparse(req.request.url).path
        if path.endswith('portal_course_groups_read'):
            return await req.fulfill(status=200,content_type='application/json',body=json.dumps({'items':state['items']}))
        if path.endswith('portal_course_group_save'):
            args=req.request.post_data_json;state['writes'].append(args)
            if save_status!=200:return await req.fulfill(status=save_status,content_type='application/json',body=json.dumps({'code':'PT409','message':'El curso cambió. Actualiza la lista.'}))
            row=next(x for x in state['items'] if x['course_id']==args['p_course']);row.update(group_code=args['p_group'],revision=row['revision']+1)
            if class_rows is not None:next(x for x in class_rows if x['id']==row['course_id']).update(group_code=row['group_code'],revision=row['revision'])
            return await req.fulfill(status=200,content_type='application/json',body=json.dumps({'saved':True,'group_code':row['group_code'],'revision':row['revision']}))
        await req.fallback()
    await context.route(h.API+'/**',route)
    return state

async def main():
    count=0
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for role in ['student','professor']:
            for mobile in [False,True]:
                c,page,state,data=await l.fixture(browser,role,mobile=mobile)
                rows=[{'course_id':l.COURSE,'code':'MAT-001','period_name':'Periodo de prueba 2026','group_code':'CI-1','revision':1}]
                await mock_groups(c,rows);await page.evaluate('PortalCourseGroups.reload()')
                selector='#subjectsList .subject-code' if role=='student' else '#teachingList .teaching-code'
                await expect(page.locator(selector).first).to_have_text('CI-1')
                assert await page.locator(selector).first.get_attribute('data-course-subject-code')=='MAT-001'
                await page.locator('#studentSearch' if role=='student' else '#teacherSearch').fill('CI-1')
                await expect(page.locator('#subjectsList li:visible' if role=='student' else '#teachingList li:visible')).to_have_count(1)
                await page.evaluate("location.hash='curso/'+%s+'/inicio'"%json.dumps(l.COURSE));await expect(page.locator('#learningCourseCode')).to_have_text('CI-1')
                assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors']
                width=await page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert width
                await page.screenshot(path=str(h.ARTIFACTS/f'curso-{role}-{mobile}.png'),full_page=True)
                await page.locator('#logoutButton').click();await expect(page).to_have_url(h.BASE+'/portal/index.html?estado=sesion_cerrada')
                assert await page.evaluate('PortalCourseGroups.get('+json.dumps(l.COURSE)+')===undefined') if await page.locator('#panelContent').count() else True
                await c.close();count+=1
        c,page,state,data=await w.fixture(browser)
        data['classes']=[{'id':w.CL,'subject_id':w.subject(1)['id'],'period_id':w.period(7)['id'],'active':True,'code':'CAT-001','subject_name':'Cristología','period_name':'Enero–Junio 2027','starts_on':'2027-01-01','ends_on':'2027-06-30','students':0,'professors':0}]
        rows=[{'course_id':w.CL,'code':'CAT-001','period_name':'Enero–Junio 2027','group_code':'1T-2','revision':1,'planned_professor':'Docente ficticio'}]
        data['classes'][0].update(group_code='1T-2',revision=1)
        groups=await mock_groups(c,rows,class_rows=data['classes']);await page.evaluate('PortalCourseGroups.reload()');await w.nav(page,'clases')
        await expect(page.locator('#classDirectoryList')).to_contain_text('1T-2');assert 'CAT-001' not in await page.locator('#classDirectoryList').inner_text()
        await page.locator('#classDirectoryList summary').click();await page.get_by_role('button',name='Curso / semestre').click();await expect(page.locator('.course-group-dialog')).to_be_visible()
        await page.locator('#classFormationCourse').select_option('2T-3');await page.get_by_role('button',name='Guardar curso',exact=True).click()
        await expect(page.locator('.course-group-dialog')).to_have_count(0);await expect(page.locator('#classDirectoryList')).to_contain_text('2T-3')
        assert groups['writes'][0]['p_revision']==1
        await page.locator('#classDirectoryList summary').click();await page.get_by_role('button',name='Curso / semestre').click();await page.get_by_role('button',name='Cancelar',exact=True).click();await expect(page.locator('.course-group-dialog')).to_have_count(0)
        await mock_groups(c,groups['items'],save_status=409)
        await page.get_by_role('button',name='Curso / semestre').click();await page.locator('#classFormationCourse').select_option('CI-1');await page.get_by_role('button',name='Guardar curso',exact=True).click()
        await expect(page.locator('.course-group-dialog')).to_contain_text('El curso cambió');await expect(page.get_by_role('button',name='Guardar curso',exact=True)).to_be_disabled();await page.get_by_role('button',name='Cancelar',exact=True).click()
        await c.close();count+=1
        # Materia nueva: el código se puede omitir y se conserva en el payload del servidor.
        c,page,state,data=await w.fixture(browser);await w.nav(page,'catalogos-academicos')
        await page.locator('#subjectName').fill('Materia ficticia nueva');await page.locator('#subjectCreate').click()
        await expect(page.locator('#subjectMessage')).to_contain_text('creada')
        calls=[args for action,args in state['catalog_calls'] if action=='create_subjects']
        assert calls and calls[-1]['p_code'].startswith('M-') and len(calls[-1]['p_code'])==18
        assert not state['route_errors'],state['route_errors']
        await c.close();count+=1
        await browser.close()
    print(f'PASS {count} escenarios de cursos (roles, móvil, etiquetas, selección, sesión y materia automática).')

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
