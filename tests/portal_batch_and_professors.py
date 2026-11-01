"""Inscripción múltiple, profesores agrupados y barra de navegación; API simulada."""
import asyncio, json, shutil
from urllib.parse import urlparse
from playwright.async_api import async_playwright, expect
import portal_subjects as h
import portal_workspace as w

checks=0
IDS=[f'91000000-0000-4000-8000-{i:012d}' for i in range(1,38)]

async def fixture(browser,mobile=False):
    context,page,state,data=await w.fixture(browser,mobile=mobile)
    data['classes']=[{'id':w.CL,'subject_id':w.subject(1)['id'],'period_id':w.period(7)['id'],'active':True,'code':'FICT-1','subject_name':'Materia de prueba','period_name':'Enero–Junio 2027','group_code':'CI-1','revision':1,'students':1,'professors':0}]
    data['people'].extend(w.person(uid,f'Seminarista {i:02d}','student') for i,uid in enumerate(IDS,1))
    data['enrollments']=[{'id':w.EN,'person_id':w.A,'class_id':w.CL,'full_name':'Alumno de prueba','subject_name':'Materia de prueba','period_name':'Enero–Junio 2027','active':True},{'id':'91000000-0000-4000-8000-000000008888','person_id':IDS[0],'class_id':w.CL,'full_name':'Seminarista 01','subject_name':'Materia de prueba','period_name':'Enero–Junio 2027','active':False}]
    return context,page,state,data

async def open_batch(page):
    await w.nav(page,'clases')
    await page.get_by_role('button',name='Inscribir alumnos',exact=True).click()
    await expect(page.locator('#batchEnrollmentDialog')).to_be_visible()

async def done(context,state,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors']
    checks+=1;print('PASS '+label,flush=True);await context.close()

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for mobile in [False,True]:
            c,page,state,data=await fixture(browser,mobile)
            await open_batch(page);await expect(page.locator('#batchEnrollmentList input')).to_have_count(38)
            await expect(page.locator('#batchEnrollmentList input[value="'+w.A+'"]').first).to_be_disabled()
            await expect(page.locator('#batchEnrollmentList input[value="'+w.A+'"]').first).to_be_checked()
            await page.locator('#batchEnrollmentSearch').fill('Seminarista 01');await page.locator('#batchEnrollmentList input').check()
            await page.locator('#batchEnrollmentSearch').fill('Seminarista 02');await page.locator('#batchEnrollmentSelectAll').click()
            await expect(page.locator('#batchEnrollmentCount')).to_contain_text('2 seleccionados')
            await page.locator('#batchEnrollmentSearch').fill('No existe');await expect(page.locator('#batchEnrollmentList')).to_contain_text('No hay alumnos')
            await page.locator('#batchEnrollmentSearch').fill('');await expect(page.locator('#batchEnrollmentList input:checked')).to_have_count(3)
            assert await page.locator('#batchEnrollmentDialog').evaluate('(d)=>d.scrollWidth<=d.clientWidth && d.getBoundingClientRect().height<=innerHeight')
            assert await page.locator('#batchEnrollmentSave').evaluate('(b)=>{const r=b.getBoundingClientRect(),d=b.closest("dialog").getBoundingClientRect();return r.top>=d.top && r.bottom<=d.bottom-8 && r.bottom<=innerHeight}')
            await page.screenshot(path=str(h.ARTIFACTS/f'inscripcion-multiple-{mobile}.png'))
            await page.locator('#batchEnrollmentSelectAll').click();await expect(page.locator('#batchEnrollmentCount')).to_contain_text('37 seleccionados')
            await page.locator('#batchEnrollmentClear').click();await expect(page.locator('#batchEnrollmentSave')).to_be_disabled()
            for uid in IDS[:2]:await page.locator('#batchEnrollmentList input[value="'+uid+'"]').check()
            await page.locator('#batchEnrollmentSave').click();await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible()
            await expect(page.locator('#classDirectoryStatus')).to_contain_text('1 nuevo · 1 reactivado')
            assert data['batch_calls']==[{'p_class':w.CL,'p_students':IDS[:2]}]
            assert len(data['enrollments'])==3 and data['enrollments'][1]['id']=='91000000-0000-4000-8000-000000008888' and data['enrollments'][1]['active']
            await page.get_by_role('button',name='Inscribir alumnos',exact=True).click();await expect(page.locator('#batchEnrollmentList input:disabled')).to_have_count(3)
            await page.keyboard.press('Escape');await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible()
            await done(c,state,('Móvil' if mobile else 'Escritorio')+': 38 candidatos, selección persistente, selección de resultados, alta y reactivación en una llamada')

        c,page,state,data=await fixture(browser);data['candidate_status']=503
        await open_batch(page);await expect(page.locator('#batchEnrollmentStatus')).to_contain_text('No se pudieron cargar')
        await expect(page.locator('#batchEnrollmentSave')).to_be_disabled();data['candidate_status']=200
        await page.locator('#batchEnrollmentRefresh').click();await expect(page.locator('#batchEnrollmentList input')).to_have_count(38)
        await done(c,state,'Error de lectura recuperable, sin habilitar un lote con lista desconocida')

        c,page,state,data=await fixture(browser)
        await open_batch(page);await page.locator('#batchEnrollmentList input[value="'+IDS[1]+'"]').check();data['write_status']=500
        await page.locator('#batchEnrollmentSave').click();await expect(page.locator('#batchEnrollmentStatus')).to_contain_text('No se pudo confirmar')
        await expect(page.locator('#batchEnrollmentSave')).to_be_disabled();assert len(data['batch_calls'])==1
        # Simula que el servidor alcanzó a confirmar el lote antes de perderse la respuesta HTTP.
        data['enrollments'].append({'id':'91000000-0000-4000-8000-000000008889','person_id':IDS[1],'class_id':w.CL,'full_name':'Seminarista 02','subject_name':'Materia de prueba','period_name':'Enero–Junio 2027','active':True})
        data['write_status']=200;await page.locator('#batchEnrollmentRefresh').click()
        await expect(page.locator('#batchEnrollmentList input[value="'+IDS[1]+'"]').first).to_be_disabled()
        await expect(page.locator('#batchEnrollmentCount')).to_contain_text('0 seleccionados');assert len(data['batch_calls'])==1
        await done(c,state,'Respuesta incierta no se reenvía; actualizar descubre las altas ya confirmadas')

        c,page,state,data=await fixture(browser);data['candidate_gate']=asyncio.Event()
        await open_batch(page);await data['candidate_started'].wait();await page.evaluate("location.hash='inicio'")
        data['candidate_gate'].set();await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible();await expect(page.locator('#batchEnrollmentList')).to_be_empty()
        await done(c,state,'Navegar cierra el diálogo y descarta candidatos tardíos')

        c,page,state,data=await fixture(browser);data['candidate_status']=404
        await open_batch(page);await expect(page.locator('#batchEnrollmentStatus')).to_contain_text('todavía no está habilitada')
        assert not data['batch_calls'];await expect(page.locator('#batchEnrollmentSave')).to_be_disabled()
        await done(c,state,'Falta de instalación SQL visible, sin recurrir a escrituras parciales')

        c,page,state,data=await fixture(browser)
        for width in [1920,1440,1100,850]:
            await page.set_viewport_size({'width':width,'height':1000})
            links=page.locator('#workspaceNav nav a:visible');ys=await links.evaluate_all('(links)=>links.map(a=>a.getBoundingClientRect().top)')
            assert max(ys)-min(ys)<1,(width,ys)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.evaluate("location.hash='mi-perfil'");await expect(page.locator('#workspaceNav [data-route="mi-perfil"]')).to_have_attribute('aria-current','page')
        assert await page.locator('#workspaceNav nav').evaluate('(n)=>{const a=n.querySelector("[data-route=mi-perfil]").getBoundingClientRect(),b=n.getBoundingClientRect();return a.left>=b.left-1 && a.right<=b.right+1}')
        await page.set_viewport_size({'width':1920,'height':1000});await page.screenshot(path=str(h.ARTIFACTS/'barra-una-linea.png'))
        await done(c,state,'Navegación de escritorio en una línea y Mi perfil visible, incluso en ancho reducido')

        c,page,state,data=await fixture(browser)
        teachers=[w.P,'92000000-0000-4000-8000-000000000001','92000000-0000-4000-8000-000000000002']
        data['people'].extend(w.person(uid,'Docente con mismo nombre','professor') for uid in teachers[1:])
        data['assignments']=[{'id':f'93000000-0000-4000-8000-{i:012d}','person_id':teachers[(i-1)%3],'class_id':w.CL,'full_name':'Pbro. Profesor' if (i-1)%3==0 else 'Docente con mismo nombre','subject_name':f'Materia ficticia {i:03d}','period_name':'Ago-Dic 2026' if i%2 else 'Ene-May 2027','active':i%5!=0} for i in range(1,218)]
        await w.nav(page,'profesores');await expect(page.locator('#managementList>.management-professor')).to_have_count(3)
        await expect(page.locator('#managementMessage')).to_contain_text('217 asignaciones')
        reads=[b for action,b in data['calls'] if action=='read' and b['p_resource']=='assignments'];assert [b['p_offset'] for b in reads]==[0,100,200]
        await expect(page.locator('#managementMore')).to_be_hidden()
        await expect(page.locator('#managementList summary h3').filter(has_text='Pbro. Profesor')).to_have_count(1)
        teacher=page.locator('.management-professor').filter(has=page.locator('summary h3',has_text='Pbro. Profesor'))
        await teacher.locator('summary').click();await expect(teacher.locator('h4')).to_have_count(2)
        await page.screenshot(path=str(h.ARTIFACTS/'profesores-agrupados.png'))
        await teacher.get_by_role('button',name='Asignar otra clase',exact=True).click();await expect(page.locator('#admin-person_id')).to_have_value(w.P)
        await w.select_ready(page,'class_id',w.CL);await page.locator('#managementSave').click();await expect(page.locator('#managementList>.management-professor')).to_have_count(3)
        await expect(page.locator('#managementMessage')).to_contain_text('218 asignaciones')
        await page.locator('#managementSearch').fill('Materia ficticia 121');await page.locator('#managementSearchForm button[type=submit]').click()
        await expect(page.locator('#managementList>.management-professor')).to_have_count(1);await expect(page.locator('#managementMessage')).to_contain_text('1 asignación que coincide')
        await page.locator('#managementList summary').click();await page.get_by_role('button',name='Dar de baja',exact=True).click();await page.locator('#managementSave').click()
        await page.locator('#managementList summary').click();await expect(page.get_by_role('button',name='Reactivar',exact=True)).to_be_visible()
        await done(c,state,'217 asignaciones de tres páginas se agrupan por identidad, con periodos, búsqueda, agregar clase y baja individual')

        c,page,state,data=await fixture(browser)
        data['assignments']=[{'id':f'94000000-0000-4000-8000-{i:012d}','person_id':w.P,'class_id':w.CL,'full_name':'Pbro. Profesor','subject_name':f'Materia ficticia {i:03d}','period_name':'Periodo ficticio','active':True} for i in range(1,102)]
        broken={'value':True}
        async def fail_second_page(route):
            if urlparse(route.request.url).path.endswith('portal_admin_read') and route.request.post_data_json.get('p_resource')=='assignments' and route.request.post_data_json.get('p_offset')==100 and broken['value']:
                return await route.fulfill(status=503,content_type='application/json',body=json.dumps({'code':'XX000','message':'Fixture'}))
            await route.fallback()
        await c.route(h.API+'/**',fail_second_page)
        await w.nav(page,'profesores');await expect(page.locator('#managementMessage')).to_contain_text('No se pudo consultar')
        await expect(page.locator('#managementList')).to_be_empty();broken['value']=False;await page.locator('#managementRefresh').click()
        await expect(page.locator('#managementList>.management-professor')).to_have_count(1);await expect(page.locator('#managementMessage')).to_contain_text('101 asignaciones')
        await done(c,state,'Una segunda página fallida no muestra grupos parciales; Actualizar recupera el grupo completo')

        c,page,state,data=await fixture(browser)
        await open_batch(page);await expect(page.locator('#batchEnrollmentList input')).to_have_count(38)
        state['profile']={'full_name':'Profesor ficticio','role':'professor','active':True};data['candidate_status']=403
        await page.locator('#batchEnrollmentRefresh').click();await expect(page.locator('#profileRole')).to_have_text('Profesor')
        await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible();await expect(page.locator('#batchEnrollmentList')).to_be_empty()
        await done(c,state,'Revocar Control Escolar cierra el diálogo y limpia nombres y selección')

        for role in ['student','professor']:
            c,page,state=await h.fixture(browser,profile={'full_name':'Usuario ficticio','role':role,'active':True})
            await expect(page.locator('#panelContent')).to_be_visible()
            await page.evaluate('(id)=>PortalEnrollmentBatch.open({id,active:true,subject_name:"Ficticia",period_name:"Ficticio"})',w.CL)
            await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible()
            assert not any('/rpc/portal_enrollment_' in url or '/rpc/portal_enroll_students' in url for method,url in state['requests'])
            await done(c,state,role+': inscripción múltiple inaccesible')
        await browser.close()
    print('PASS '+str(checks)+' escenarios de inscripción múltiple, profesores y navegación.',flush=True)

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
