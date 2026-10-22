"""Control Escolar docente y eliminación: SDK real, API/Storage simulados.
Run python3 tests/portal_staff_deletion.py. Sin solicitudes a Supabase real.
"""
import asyncio,copy,json,shutil
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_workspace as w
from portal_control_catalogs import subject,period

TOKEN='a'*32
checks=0
PATH=w.CL+'/a2000000-0000-4000-8000-000000000001/'+h.UID+'/a3000000-0000-4000-8000-000000000001/trabajo.pdf'

def class_row():return {'id':w.CL,'subject_id':subject(1)['id'],'period_id':period(7)['id'],'active':True,'code':'CAT-001','subject_name':'Cristología','period_name':'Enero–Junio 2027','starts_on':'2027-01-01','ends_on':'2027-06-30','students':1,'professors':1}

async def fixture(browser,**args):
    context,page,state,data=await w.fixture(browser,**args)
    data['classes']=[class_row()]
    data['people'].append(w.person(h.UID,'Pbro. Martín de prueba','control_escolar'))
    extra={'preview_status':200,'delete_status':200,'storage_status':200,'queued':[],'missing':set(),'calls':[],'gate':None,'started':asyncio.Event(),'label':'CAT-001 · Cristología','storage_started':asyncio.Event(),'cleanup_done':asyncio.Event()}
    async def route_api(route):
        path=urlparse(route.request.url).path;body=route.request.post_data_json
        headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'}
        def response(status,payload):return route.fulfill(status=status,headers=headers,body=json.dumps(payload))
        if path.endswith('portal_admin_delete_preview'):
            extra['calls'].append(('preview',body));extra['started'].set()
            if extra['gate']:await extra['gate'].wait()
            if extra['preview_status']!=200:return await response(extra['preview_status'],{'code':'XX000','message':'Fixture'})
            return await response(200,{'id':body['p_id'],'kind':body['p_kind'],'label':extra['label'],'token':TOKEN,'counts':{'classes':1,'enrollments':1,'professors':1,'announcements':1,'modules':1,'topics':1,'assignments':1,'submissions':1,'grades':1,'events':1,'stored_files':len(extra['queued'])}})
        if path.endswith('portal_admin_delete'):
            extra['calls'].append(('delete',copy.deepcopy(body)))
            if extra['delete_status']!=200:return await response(extra['delete_status'],{'code':'PT409' if extra['delete_status']==409 else 'XX000','message':'Los registros cambiaron; cierra y revisa de nuevo la eliminación'})
            assert body['p_confirmation']=='ELIMINAR' and body['p_token']==TOKEN
            data['classes'].clear();data['enrollments'].clear();data['assignments'].clear()
            if body['p_kind']=='subject':state['catalog_subjects'].clear()
            if body['p_kind']=='period':state['catalog_periods'].clear()
            return await response(200,{'id':body['p_id'],'saved':True,'pending_files':len(extra['queued'])})
        if path.endswith('portal_admin_cleanup_files'):
            if body['p_ack']:extra['queued']=[s for s in extra['queued'] if s not in extra['missing']]
            if not extra['queued'] and extra['missing']:extra['cleanup_done'].set()
            return await response(200,{'paths':extra['queued'][:100],'remaining':len(extra['queued'])})
        if path=='/storage/v1/object/portal-coursework':
            extra['storage_started'].set();extra['calls'].append(('storage',copy.deepcopy(body)))
            if extra['storage_status']!=200:return await response(extra['storage_status'],{'statusCode':'500','message':'Storage unavailable','error':'Fixture'})
            extra['missing'].update(body['prefixes'])
            return await response(200,[{'name':s} for s in body['prefixes']])
        await route.fallback()
    await context.route(h.API+'/**',route_api)
    await expect(page.locator('#controlHome')).to_be_visible()
    return context,page,state,data,extra

async def done(context,state,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];checks+=1;print('PASS '+label,flush=True);await context.close()

async def open_class(page):
    await w.nav(page,'clases');await page.get_by_role('button',name='Eliminar clase',exact=True).click();await expect(page.locator('#deletionTarget')).to_contain_text('Cristología')

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        c,page,state,data,x=await fixture(browser)
        await w.nav(page,'clases');await page.get_by_role('button',name='Asignar profesor',exact=True).click();await w.select_ready(page,'class_id',w.CL)
        await expect(page.locator('#admin-person_id')).to_contain_text('Pbro. Martín de prueba (Control Escolar)')
        await w.select_ready(page,'person_id',h.UID);await page.locator('#managementSave').click();await expect(page.locator('#managementList')).to_contain_text('2 profesores')
        assert data['people'][-1]['role']=='control_escolar'
        await expect(page.locator('#workspaceNav [data-route=materias-asignadas]')).not_to_have_attribute('hidden','')
        await done(c,state,'Control Escolar appears in teacher picker and keeps administrative role/menu')

        c,page,state,data,x=await fixture(browser)
        await open_class(page);await expect(page.locator('#deletionSave')).to_be_disabled();await page.locator('#deletionConfirmation').fill('eliminar');await expect(page.locator('#deletionSave')).to_be_disabled();await page.locator('#deletionCancel').click()
        assert not any(kind=='delete' for kind,_ in x['calls'])
        await done(c,state,'Cancel and nonexact confirmation send no destructive request')

        for kind in ['class','subject','period']:
            c,page,state,data,x=await fixture(browser)
            if kind=='class':await open_class(page)
            else:
                await w.nav(page,'catalogos-academicos');await page.get_by_role('button',name='Eliminar '+('materia' if kind=='subject' else 'periodo'),exact=True).click();await expect(page.locator('#deletionTarget')).to_contain_text('Cristología')
            await expect(page.locator('#deletionCounts')).to_contain_text('Entregas: 1')
            await page.locator('#deletionConfirmation').fill('ELIMINAR');await page.locator('#deletionSave').click();await expect(page.locator('#deletionDialog')).not_to_be_visible();await expect(page.locator('#deletionNotice')).to_contain_text('eliminado definitivamente')
            if kind=='class':await expect(page.locator('#managementList li')).to_have_count(0)
            else:await expect(page.locator('#'+('subject' if kind=='subject' else 'period')+'List li')).to_have_count(0)
            assert len([r for k,r in x['calls'] if k=='delete'])==1
            await done(c,state,'Confirmed '+kind+' deletion refreshes its list exactly once')

        for status in [409,500]:
            c,page,state,data,x=await fixture(browser);x['delete_status']=status
            await open_class(page);await page.locator('#deletionConfirmation').fill('ELIMINAR');await page.locator('#deletionSave').click();await expect(page.locator('#deletionMessage')).to_contain_text('registros cambiaron' if status==409 else 'No se pudo confirmar');await expect(page.locator('#deletionSave')).to_be_disabled();assert len(data['classes'])==1
            await done(c,state,'Stale preview or uncertain '+str(status)+' is never retried blindly')

        c,page,state,data,x=await fixture(browser);x['queued']=[PATH]
        await open_class(page);await page.locator('#deletionConfirmation').fill('ELIMINAR');await page.locator('#deletionSave').click();await expect(page.locator('#deletionNotice')).to_contain_text('eliminado definitivamente');await expect(page.locator('#deletionCleanupRetry')).to_be_hidden();await asyncio.wait_for(x['cleanup_done'].wait(),10);assert not x['queued']
        await done(c,state,'Official Storage API deletes queued attachments and acknowledges absence')

        c,page,state,data,x=await fixture(browser);x['queued']=[PATH];x['storage_status']=500
        await open_class(page);await page.locator('#deletionConfirmation').fill('ELIMINAR');await page.locator('#deletionSave').click();await expect(page.locator('#deletionCleanupRetry')).to_be_visible();await expect(page.locator('#deletionNotice')).to_contain_text('No se pudo comprobar');assert not data['classes'] and x['queued']
        x['storage_status']=200;await page.locator('#deletionCleanupRetry').click();await asyncio.wait_for(x['cleanup_done'].wait(),10);await expect(page.locator('#deletionCleanupRetry')).to_be_hidden();assert not x['queued'];assert len([r for k,r in x['calls'] if k=='delete'])==1
        await done(c,state,'Storage failure remains visible and retry completes without deleting academic data twice')

        c,page,state,data,x=await fixture(browser);x['preview_status']=500
        await w.nav(page,'clases');await page.get_by_role('button',name='Eliminar clase',exact=True).click();await expect(page.locator('#deletionMessage')).to_contain_text('No se pudo calcular');await expect(page.locator('#deletionSave')).to_be_disabled()
        await done(c,state,'Failed impact calculation cannot enable deletion')

        c,page,state,data,x=await fixture(browser);x['label']='<img src=x onerror=alert(1)> Cristología'
        await open_class(page);await expect(page.locator('#deletionTarget img')).to_have_count(0)
        await done(c,state,'Server labels render as text without HTML execution')

        c,page,state,data,x=await fixture(browser);x['gate']=asyncio.Event()
        await w.nav(page,'clases');await page.get_by_role('button',name='Eliminar clase',exact=True).click();await x['started'].wait();await page.evaluate('location.hash="inicio"');await expect(page.locator('#deletionDialog')).not_to_be_visible();x['gate'].set();await page.wait_for_timeout(100);await expect(page.locator('#deletionSave')).to_be_disabled()
        await done(c,state,'Navigation discards delayed preview and closes confirmation')

        c,page,state,data,x=await fixture(browser,mobile=True)
        await open_class(page);assert await page.locator('#deletionDialog').evaluate('(d)=>d.scrollWidth<=d.clientWidth && d.getBoundingClientRect().height<=innerHeight')
        await page.screenshot(path=str(h.ARTIFACTS/'seminario-eliminar-clase-movil.png'),full_page=True)
        await done(c,state,'Mobile confirmation fits screen and shows scope before deletion')
        await browser.close();print(f'PASS {checks} staff/deletion browser scenarios; mocked API only')

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
