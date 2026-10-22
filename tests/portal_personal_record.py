"""Expediente personal: SDK real, API simulada y datos ficticios."""
import asyncio,copy,hashlib,json,shutil
from pathlib import Path
from playwright.async_api import async_playwright,expect
import portal_subjects as h

STUDENT='20000000-0000-4000-8000-000000000001';checks=0

async def fixture(browser,role='student',mobile=False):
    c,page,state=await h.fixture(browser,profile={'full_name':'Alumno de prueba' if role=='student' else 'Control de prueba','role':role,'active':True},start='panel.html#inicio',mobile=mobile)
    uid=h.UID if role=='student' else STUDENT
    row={'student':{'id':uid,'full_name':'Alumno de prueba','role':'student','active':True,'login_email':'alumno@example.invalid'},'identity':{'curp':None,'birth_date':None,'age':None,'age_as_of':'2026-10-22'},'details':{},'school':{'student_number':'MR-001','entered_on':'2026-08-01','completed_on':None,'enrollments':4,'programs':[{'id':'20000000-0000-4000-8000-000000000080','name':'Formación filosófica','plan_name':'Plan de prueba 2026'}]},'revision':0,'updated_at':None,'review':{'reviewed':False,'reviewed_at':None,'reviewer':None},'can_review':role=='control_escolar'}
    data={'row':row,'calls':[],'errors':[],'read_status':200,'save_status':200,'save_code':'XX000','gate':None,'started':asyncio.Event(),'save_gate':None,'save_started':asyncio.Event(),'commit_lost':False,'reviews':0}
    def result():
        r=copy.deepcopy(data['row']);r['token']=hashlib.md5(json.dumps({key:r[key] for key in ['student','identity','details','revision']},sort_keys=True).encode()).hexdigest()
        required=[('birth_date','Fecha de nacimiento'),('curp','CURP'),('phone','Teléfono personal'),('street','Calle'),('city','Municipio / ciudad'),('state','Estado'),('country','País'),('emergency_name','Contacto de emergencia'),('emergency_phone','Teléfono de emergencia')]
        missing=[label for key,label in required if not (r['identity'].get(key) if key in ('birth_date','curp') else r['details'].get(key))];r['completion']={'completed':9-len(missing),'total':9,'missing':missing};return r
    async def route_api(route):
        req=route.request
        if '/rpc/portal_student_record_' not in req.url and not req.url.endswith(('/portal_admin_read','/portal_kardex_read')):return await route.fallback()
        body=req.post_data_json;name=req.url.rsplit('/',1)[-1];data['calls'].append((name,copy.deepcopy(body)));headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'}
        async def reply(status,body):return await route.fulfill(status=status,headers=headers,body=json.dumps(body))
        try:
            if name=='portal_kardex_read':
                if body['p_resource'] in ['programs','issues']:return await reply(200,{'items':[],'has_more':False})
                assert body['p_resource']=='record' and body['p_student']==uid
                sample=json.loads((Path(__file__).parent/'fixtures/kardex.json').read_text())['record'];sample['student'].update({'id':uid,'full_name':data['row']['student']['full_name'],'curp':data['row']['identity']['curp'],'birth_date':data['row']['identity']['birth_date']});sample['program']=None;sample['curriculum']=[];sample['method']={'repeat_policy':'all','weighted':False,'display_scale':'100'};sample['final_ready']=False;sample['final_reasons']=['Selecciona un programa'];sample['stats']['average']=80
                return await reply(200,sample)
            if name=='portal_admin_read':
                if body['p_resource']!='people':return await route.fallback()
                return await reply(200,{'items':[{'id':uid,'full_name':'Alumno de prueba','role':'student','active':True,'management_revision':0,'email':'alumno@example.invalid'}],'has_more':False})
            if name=='portal_student_record_read':
                data['started'].set()
                if data['gate']:await data['gate'].wait()
                if data['read_status']!=200:
                    if data['read_status']==403:state['profile']['active']=False
                    return await reply(data['read_status'],{'code':'42501' if data['read_status']==403 else 'PGRST202','message':'Fixture'})
                if body['p_resource']=='students':return await reply(200,{'items':[{'id':uid,'full_name':'Alumno de prueba','student_number':'MR-001','active':True,'updated_at':None},{'id':'20000000-0000-4000-8000-000000000002','full_name':'Alumno inactivo','student_number':'MR-002','active':False,'updated_at':None}],'has_more':False})
                return await reply(200,result())
            if name=='portal_student_record_save':
                data['save_started'].set()
                if data['save_gate']:await data['save_gate'].wait()
                if data['save_status']!=200 and not data['commit_lost']:return await reply(data['save_status'],{'code':data['save_code'],'message':'El expediente cambió. Actualiza antes de guardar'})
                p=body['p_data'];assert set(p)=={'full_name','curp','birth_date','details'};assert 'age' not in p['details'] and 'role' not in p['details']
                data['row']['student']['full_name']=p['full_name'];data['row']['identity'].update({'curp':p['curp'] or None,'birth_date':p['birth_date'] or None,'age':22 if p['birth_date'] else None});data['row']['details']={k:v for k,v in p['details'].items() if v};data['row']['revision']+=1;data['row']['updated_at']='2026-10-22T21:00:00Z';data['row']['review']={'reviewed':False,'reviewed_at':None,'reviewer':None}
                if role=='student':state['profile']['full_name']=p['full_name']
                if data['commit_lost']:return await reply(500,{'code':'XX000','message':'Lost response'})
                return await reply(200,{**result(),'saved':True})
            if name=='portal_student_record_review':
                data['reviews']+=1;data['row']['review']={'reviewed':True,'reviewed_at':'2026-10-22T21:00:00Z','reviewer':'Control de prueba'};return await reply(200,{**result(),'saved':True})
            raise AssertionError(name)
        except Exception as exc:
            if 'Target page, context or browser has been closed' not in str(exc):data['errors'].append(str(exc))
            try:await route.abort()
            except Exception:pass
    await c.route(h.API+'/**',route_api)
    return c,page,state,data

async def open_record(page,role='student'):
    await page.evaluate('location.hash="'+('mi-perfil' if role=='student' else 'expedientes')+'"')
    if role=='control_escolar':await expect(page.locator('#personalStudents li')).to_have_count(2);await page.locator('#personalStudents li').first.get_by_role('button',name='Abrir expediente').click()
    await expect(page.locator('#personal-full_name')).to_be_visible();await expect(page.locator('#personalStatus')).to_contain_text('Expediente actualizado')

async def done(c,state,data,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors'];checks+=1;print('PASS '+label,flush=True);await c.close()

async def visibility(page,hidden):
    await page.evaluate('(hidden)=>{Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>hidden?"hidden":"visible"});document.dispatchEvent(new Event("visibilitychange"));}',hidden)

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        c,page,state,data=await fixture(browser);await expect(page.locator('#panelContent')).to_be_visible();assert not data['calls'];await expect(page.locator('#personalProfileLink')).to_contain_text('Completar mis datos');await open_record(page);await expect(page.locator('#personalTabs [role=tab]')).to_have_count(6);await expect(page.locator('#personalAge')).to_contain_text('Se calcula');await expect(page.locator('#personalReviewTools')).to_be_hidden()
        await done(c,state,data,'student has an intuitive six-section private form, loaded only when opened')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#personal-full_name').fill('Nombre completo de prueba');await page.locator('#personal-birth_date').fill('2004-01-27');await page.locator('#personal-curp').fill('xexx040127htsxxx01');await expect(page.locator('#personal-curp')).to_have_value('XEXX040127HTSXXX01');await expect(page.locator('#personalAge')).to_contain_text('22 años');await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('Datos guardados y vinculados');await expect(page.locator('#workspaceUserName')).to_have_text('Nombre completo de prueba');await expect(page.locator('#profileName')).to_have_text('Nombre completo de prueba');assert data['row']['identity']['birth_date']=='2004-01-27';assert data['row']['school']['student_number']=='MR-001'
        await done(c,state,data,'name updates in campus header, CURP is normalized and age is calculated without writable academic fields')

        c,page,state,data=await fixture(browser);await open_record(page);await page.get_by_role('tab',name='Contacto',exact=True).click();await page.locator('#personal-phone').fill('+52 868 100 0000');await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('Datos guardados y vinculados');assert data['row']['identity']['curp'] is None and data['row']['details']['phone']=='+52 868 100 0000';await expect(page.locator('#personalDirty')).to_have_text('Datos guardados')
        await done(c,state,data,'partial contact data can be saved without inventing CURP or birth date')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#personal-curp').fill('123');await page.get_by_role('tab',name='Domicilio',exact=True).click();await page.locator('#personalSave').click();await expect(page.locator('#personal-curp')).to_be_visible();assert not [x for x in data['calls'] if x[0].endswith('_save')]
        await done(c,state,data,'invalid field on a hidden section opens the correct tab before native validation')

        c,page,state,data=await fixture(browser);await open_record(page);await page.get_by_role('tab',name='Datos escolares',exact=True).click();await expect(page.locator('#personalGroups')).to_contain_text('MR-001');await expect(page.locator('#personalGroups')).to_contain_text('Formación filosófica');await expect(page.locator('#personalPanel5 input')).to_have_count(0)
        await done(c,state,data,'matricula, school dates and program come from the existing academic record and are read-only')

        c,page,state,data=await fixture(browser,'professor');await expect(page.locator('#panelContent')).to_be_visible();await page.evaluate('location.hash="expedientes"');await expect(page.locator('#personalRecordSection')).to_be_hidden();await page.evaluate('location.hash="mi-perfil"');await expect(page.locator('#personalRecordSection')).to_be_hidden();assert not data['calls']
        await done(c,state,data,'professors cannot open private student forms by forged routes')

        c,page,state,data=await fixture(browser,'control_escolar');await open_record(page,'control_escolar');await expect(page.locator('#personalReviewTools')).to_be_visible();await page.locator('#personalMarkReviewed').click();await expect(page.locator('#personalReviewState')).to_contain_text('Revisado por Control Escolar');await expect(page.locator('#personalMarkReviewed')).to_be_disabled();await page.locator('#personal-full_name').fill('Nombre revisado');await expect(page.locator('#personalMarkReviewed')).to_be_disabled();await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('Datos guardados y vinculados');await expect(page.locator('#personalReviewState')).to_contain_text('Pendiente de revisión');assert data['reviews']==1
        await done(c,state,data,'Control can search, edit and review, and modified data return to pending review')

        c,page,state,data=await fixture(browser,'control_escolar');await page.evaluate('location.hash="personas"');await expect(page.locator('#managementList li')).to_have_count(1);await page.get_by_role('button',name='Expediente personal',exact=True).click();await expect(page.locator('#personal-full_name')).to_be_visible();await expect(page).to_have_url(h.BASE+'/portal/panel.html#expedientes')
        await done(c,state,data,'Control can reach a specific student directly from Personas')

        c,page,state,data=await fixture(browser,'control_escolar');await open_record(page,'control_escolar');await page.get_by_role('tab',name='Datos escolares',exact=True).click();await page.get_by_role('button',name='Abrir kardex de este alumno',exact=True).click();await expect(page.locator('#kardexStudentName')).to_have_text('Alumno de prueba');await page.locator('#kardexPersonalData').click();await expect(page.locator('#personal-full_name')).to_have_value('Alumno de prueba');assert [args for name,args in data['calls'] if name=='portal_student_record_read' and args.get('p_student')==STUDENT]
        await done(c,state,data,'personal record and Kardex link both ways to the same student')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#personal-full_name').fill('Borrador privado temporal');await visibility(page,True);await expect(page.locator('#personalGroups input')).to_have_count(0);assert 'Borrador privado temporal' not in await page.evaluate('JSON.stringify(localStorage)');await visibility(page,False);await expect(page.locator('#personal-full_name')).to_have_value('Borrador privado temporal');await expect(page.locator('#personalDirty')).to_have_text('Cambios sin guardar');await expect(page.locator('#personalStatus')).to_contain_text('Se conservaron')
        await done(c,state,data,'private draft survives switching tabs in memory, clears DOM while hidden and never enters localStorage')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#personal-full_name').fill('Borrador personal');await visibility(page,True);state['profile']['role']='professor';await visibility(page,False);await expect(page.locator('#personalRecordSection')).to_be_hidden();await expect(page.locator('#personalGroups input')).to_have_count(0)
        await done(c,state,data,'role changes discard the private draft instead of restoring it to a different access level')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#personal-full_name').fill('Cambio pendiente');page.once('dialog',lambda d:d.dismiss());await page.evaluate('location.hash="mis-materias"');await expect(page).to_have_url(h.BASE+'/portal/panel.html#mi-perfil');await expect(page.locator('#personal-full_name')).to_have_value('Cambio pendiente');page.once('dialog',lambda d:d.accept());await page.evaluate('location.hash="mis-materias"');await expect(page.locator('#personalGroups input')).to_have_count(0)
        await done(c,state,data,'leaving a dirty form offers an explicit discard choice and clears the form after acceptance')

        c,page,state,data=await fixture(browser);await open_record(page);data['save_status']=409;data['save_code']='PT409';await page.locator('#personal-full_name').fill('Conflicto de prueba');await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('El expediente cambió');await expect(page.locator('#personalSave')).to_be_disabled();await expect(page.locator('#personal-full_name')).to_have_value('Conflicto de prueba');await expect(page.locator('#personalReload')).to_be_enabled()
        await done(c,state,data,'concurrent changes preserve typed data and require refresh instead of overwriting')

        c,page,state,data=await fixture(browser);await open_record(page);data['commit_lost']=True;await page.locator('#personal-full_name').fill('Guardado con respuesta perdida');await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('No se pudo confirmar');await expect(page.locator('#personalSave')).to_be_disabled();page.once('dialog',lambda d:d.accept());await page.locator('#personalReload').click();await expect(page.locator('#personalStatus')).to_contain_text('Expediente actualizado');await expect(page.locator('#personal-full_name')).to_have_value('Guardado con respuesta perdida');assert len([x for x in data['calls'] if x[0].endswith('_save')])==1
        await done(c,state,data,'an uncertain response checks the stored record without automatically resending mutations')

        c,page,state,data=await fixture(browser);await open_record(page);data['commit_lost']=True;await page.locator('#personal-full_name').fill('Datos confirmados al regresar');await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('No se pudo confirmar');await visibility(page,True);await visibility(page,False);await expect(page.locator('#personal-full_name')).to_have_value('Datos confirmados al regresar');await expect(page.locator('#personalDirty')).to_have_text('Datos guardados');await expect(page.locator('#personalSave')).to_be_enabled();assert len([x for x in data['calls'] if x[0].endswith('_save')])==1
        await done(c,state,data,'returning confirms an already committed draft without flagging a false conflict or resending')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#personal-full_name').fill('Borrador privado al salir');await page.locator('#logoutButton').click();await expect(page).to_have_url(h.BASE+'/portal/index.html?estado=sesion_cerrada');assert 'Borrador privado al salir' not in await page.evaluate('JSON.stringify(localStorage)');await expect(page.locator('#personalGroups')).to_have_count(0)
        await done(c,state,data,'signout discards the private draft and removes student data from the page')

        c,page,state,data=await fixture(browser);await open_record(page);data['read_status']=403;await page.locator('#personalReload').click();await expect(page.locator('#personalGroups input')).to_have_count(0);await expect(page.locator('#personalRecordSection')).to_be_hidden()
        await done(c,state,data,'revoked access clears private form fields and rechecks the profile')

        c,page,state,data=await fixture(browser);await open_record(page);data['gate']=asyncio.Event();data['started'].clear();await page.locator('#personalReload').click();await data['started'].wait();await page.evaluate('location.hash="inicio"');data['gate'].set();await page.wait_for_timeout(100);await expect(page.locator('#personalGroups input')).to_have_count(0)
        await done(c,state,data,'late reads cannot restore personal data after leaving')

        c,page,state,data=await fixture(browser);await open_record(page);await page.get_by_role('tab',name='Contacto',exact=True).focus();await page.keyboard.press('End');await expect(page.get_by_role('tab',name='Datos escolares',exact=True)).to_be_focused();await page.keyboard.press('Home');await expect(page.get_by_role('tab',name='Identificación',exact=True)).to_be_focused()
        await done(c,state,data,'keyboard users can move between section tabs with arrows, Home and End')

        c,page,state,data=await fixture(browser);await open_record(page);data['row']['student']['full_name']='<img src=x onerror=alert(1)>';await page.locator('#personalReload').click();await expect(page.locator('#personalStudentName')).to_have_text('<img src=x onerror=alert(1)>');await expect(page.locator('#personalRecordSection img')).to_have_count(0)
        await done(c,state,data,'personal names render as literal text rather than HTML')

        for mobile in [False,True]:
            c,page,state,data=await fixture(browser,mobile=mobile);await open_record(page);await page.locator('#personal-birth_date').fill('2004-01-27');await page.locator('#personal-curp').fill('XEXX040127HTSXXX01');await page.locator('#personalSave').click();await expect(page.locator('#personalStatus')).to_contain_text('Datos guardados y vinculados');await page.evaluate('window.scrollTo(0,0)');assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(h.ARTIFACTS/('seminario-expediente-movil.png' if mobile else 'seminario-expediente-escritorio.png')),full_page=True)
            await done(c,state,data,('mobile' if mobile else 'desktop')+' personal record fits screen and supports saving')
        await browser.close();print(f'PASS {checks} personal-record browser scenarios; mocked API only',flush=True)

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
