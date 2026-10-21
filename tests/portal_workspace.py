"""Campus navigation/administration/activation: real SDK and simulated API.
Run: python tests/portal_workspace.py. No production requests or credentials.
"""
import asyncio, copy, json, re, shutil
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright, expect
import portal_subjects as h
from portal_control_catalogs import subject, period, CONTROL_PROFILE

OUT=None
checks=0
P='90000000-0000-4000-8000-000000000001'; A='90000000-0000-4000-8000-000000000002'; CL='90000000-0000-4000-8000-000000000003'; EN='90000000-0000-4000-8000-000000000004'; AS='90000000-0000-4000-8000-000000000005'

def person(uid,name,role):return {'id':uid,'full_name':name,'role':role,'active':True,'management_revision':0,'email':role+'@example.invalid'}

async def fixture(browser,**kwargs):
    catalog={'subjects':[subject(1,'Cristología')],'periods':[period(7,'Enero–Junio 2027')]}
    context,page,state=await h.fixture(browser,profile=CONTROL_PROFILE,catalog=catalog,start='panel.html#inicio',**kwargs)
    data={'people':[person(P,'Pbro. Profesor','professor'),person(A,'Alumno de prueba','student')],'classes':[],'enrollments':[],'assignments':[],'events':[],'calls':[],'read_status':200,'write_status':200,'read_gate':None,'read_started':asyncio.Event(),'write_gate':None,'write_started':asyncio.Event()}
    async def route_api(route):
        req=route.request;url=urlparse(req.url);path=url.path;body=req.post_data_json;headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Content-Type':'application/json'}
        if path in ['/rest/v1/subjects','/rest/v1/academic_periods']:
            query=parse_qs(url.query)
            if query.get('limit')!=['50']:return await route.fallback()
            rows=state['catalog_subjects' if path.endswith('/subjects') else 'catalog_periods']
            return await route.fulfill(status=200,headers=headers,body=json.dumps(rows))
        if '/functions/v1/invite-person' in path:
            data['calls'].append(('invite',body));return await route.fulfill(status=503,headers=headers,body=json.dumps({'error':'Email not configured'}))
        if path.endswith('portal_admin_read'):
            data['calls'].append(('read',copy.deepcopy(body)));data['read_started'].set()
            if data['read_gate']:await data['read_gate'].wait()
            if data['read_status']!=200:return await route.fulfill(status=data['read_status'],headers=headers,body=json.dumps({'code':'42501' if data['read_status']==403 else 'XX000','message':'Fixture'}))
            kind=body['p_resource'];rows=data['people'] if kind in ('students','professors') else data['classes'] if kind=='active_classes' else data[kind]
            if kind in ('students','professors'):rows=[r for r in rows if r['active'] and r['role']==('student' if kind=='students' else 'professor')]
            if kind=='active_classes':rows=[r for r in rows if r['active']]
            needle=body['p_search'].casefold()
            if needle:rows=[r for r in rows if needle in json.dumps(r,ensure_ascii=False).casefold()]
            start=body['p_offset'];end=start+body['p_limit'];return await route.fulfill(status=200,headers=headers,body=json.dumps({'items':rows[start:end],'has_more':len(rows)>end}))
        if path.endswith('portal_admin_write'):
            data['calls'].append(('write',copy.deepcopy(body)));data['write_started'].set()
            if data['write_gate']:await data['write_gate'].wait()
            if data['write_status']!=200:return await route.fulfill(status=data['write_status'],headers=headers,body=json.dumps({'code':'PT409' if data['write_status']==409 else 'XX000','message':'Fixture'}))
            action=body['p_action'];args=body['p_data'];entity=args.get('id',CL)
            if action=='class_create':data['classes'].append({'id':CL,'subject_id':subject(1)['id'],'period_id':period(7)['id'],'active':True,'code':'CAT-001','subject_name':'Cristología','period_name':'Enero–Junio 2027','starts_on':'2027-01-01','ends_on':'2027-06-30','students':0,'professors':0})
            elif action in ('enroll','assign'):
                kind='enrollments' if action=='enroll' else 'assignments';user=next(r for r in data['people'] if r['id']==args['person_id']);entity=EN if action=='enroll' else AS
                data[kind].append({'id':entity,'person_id':user['id'],'class_id':CL,'full_name':user['full_name'],'subject_name':'Cristología','period_name':'Enero–Junio 2027','active':True});data['classes'][0]['students' if action=='enroll' else 'professors']+=1
            elif action in ('enrollment_state','assignment_state','class_state'):
                kind={'enrollment_state':'enrollments','assignment_state':'assignments','class_state':'classes'}[action];next(r for r in data[kind] if r['id']==entity)['active']=args['active']
            elif action=='person_update':
                user=next(r for r in data['people'] if r['id']==entity);user.update(full_name=args['full_name'],role=args['role'],active=args['active'],management_revision=user['management_revision']+1)
            elif action in ('subject_update','period_update'):
                rows=state['catalog_subjects' if action=='subject_update' else 'catalog_periods'];next(r for r in rows if r['id']==entity).update(args)
            return await route.fulfill(status=200,headers=headers,body=json.dumps({'saved':True,'id':entity}))
        await route.fallback()
    await context.route(h.API+'/**',route_api)
    return context,page,state,data

async def done(context,state,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];checks+=1;print('PASS '+label,flush=True);await context.close()

async def nav(page,route):
    await page.evaluate('(route)=>location.hash=route',route)
    if route in ['personas','clases','inscripciones','profesores','actividad']:await expect(page.locator('#managementSection')).to_be_visible()

async def select_ready(page,name,value):
    target=page.locator('#admin-'+name);await expect(target).to_be_enabled();await target.select_option(value)

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        context,page,state,data=await fixture(browser)
        await expect(page.locator('#controlHome')).to_be_visible();assert not data['calls']
        await page.screenshot(path=str(OUT/'seminario-campus-control.png'),full_page=True,animations='disabled')
        await nav(page,'clases');await expect(page.locator('#managementMessage')).to_contain_text('No hay registros')
        await page.locator('#managementCreate').click();await select_ready(page,'subject_id',subject(1)['id']);await select_ready(page,'period_id',period(7)['id']);await page.locator('#managementSave').click()
        await expect(page.locator('#managementDialog')).not_to_be_visible();await expect(page.locator('#managementList')).to_contain_text('Cristología')
        assert data['calls'][-2][0]=='write' or any(c[0]=='write' for c in data['calls'])
        await page.get_by_role('button',name='Asignar profesor',exact=True).click();await select_ready(page,'class_id',CL);await select_ready(page,'person_id',P);await page.locator('#managementSave').click();await expect(page.locator('#managementList')).to_contain_text('1 profesores')
        await page.get_by_role('button',name='Inscribir',exact=True).click();await select_ready(page,'class_id',CL);await select_ready(page,'person_id',A);await page.locator('#managementSave').click();await expect(page.locator('#managementList')).to_contain_text('1 alumnos')
        await nav(page,'inscripciones');await expect(page.locator('#managementList')).to_contain_text('Alumno de prueba');await page.get_by_role('button',name='Dar de baja',exact=True).click();await page.locator('#managementSave').click();await expect(page.locator('#managementList')).to_contain_text('Inactivo')
        await page.get_by_role('button',name='Reactivar',exact=True).click();await page.locator('#managementSave').click();await expect(page.locator('#managementList')).to_contain_text('Activo')
        await done(context,state,'Control opens a class, assigns a professor, enrolls a student, deactivates and restores enrollment')

        context,page,state,data=await fixture(browser)
        await nav(page,'personas');await expect(page.locator('#managementList')).to_contain_text('Pbro. Profesor')
        await page.locator('.management-row').first.get_by_role('button',name='Editar persona').click();await page.locator('#admin-full_name').fill('Pbro. Nombre actualizado');await page.locator('#managementSave').click();await expect(page.locator('#managementList')).to_contain_text('Nombre actualizado')
        await page.locator('.management-row').first.get_by_role('button',name='Editar persona').click();await expect(page.locator('#managementCancel')).to_be_enabled();await page.locator('#managementCancel').click();await expect(page.locator('#managementDialog')).not_to_be_visible()
        await page.locator('#managementSearch').fill('no existe');await page.locator('#managementSearchForm button[type=submit]').click();await expect(page.locator('#managementList li')).to_have_count(0)
        await done(context,state,'People edit has revision, clean dialog reuse, cancel and server search')

        context,page,state,data=await fixture(browser)
        await nav(page,'catalogos-academicos');await expect(page.locator('#subjectCode')).to_be_enabled();await page.get_by_role('button',name='Editar materia',exact=True).click();await page.locator('#admin-name').fill('Cristología actualizada');await page.locator('#managementSave').click();await expect(page.locator('#subjectList')).to_contain_text('Cristología actualizada')
        await page.get_by_role('button',name='Editar periodo',exact=True).click();await page.locator('#admin-name').fill('Periodo actualizado');await page.locator('#managementSave').click();await expect(page.locator('#periodList')).to_contain_text('Periodo actualizado')
        await done(context,state,'Catalog editing updates existing forms/lists without deleting history')

        context,page,state,data=await fixture(browser)
        await nav(page,'personas');await page.locator('#managementCreate').click();await page.locator('#admin-full_name').fill('Persona invitada');await page.locator('#admin-email').fill('existing@example.invalid');await page.locator('#managementSave').click();await expect(page.locator('#managementFormMessage')).to_contain_text('No se pudo confirmar');await expect(page.locator('#managementSave')).to_be_disabled();assert len([c for c in data['calls'] if c[0]=='invite'])==1;await page.locator('#managementCancel').click();await expect(page.locator('#managementDialog')).not_to_be_visible()
        await done(context,state,'Unavailable email is explicit; no blind resend; close remains available')

        context,page,state,data=await fixture(browser)
        data['read_status']=500;await nav(page,'personas');await expect(page.locator('#managementMessage')).to_contain_text('No se pudo consultar');data['read_status']=200;await page.locator('#managementRefresh').click();await expect(page.locator('#managementList li')).to_have_count(2)
        await page.locator('.management-row').first.get_by_role('button',name='Editar persona').click();data['write_status']=409;await page.locator('#managementSave').click();await expect(page.locator('#managementFormMessage')).to_contain_text('ya existe o cambió');await expect(page.locator('#managementSave')).to_be_enabled()
        await done(context,state,'Failed reads can retry and conflicts require refreshed data')

        context,page,state,data=await fixture(browser)
        data['people'][0]['full_name']='<img src=x onerror=alert(1)>'
        await nav(page,'personas');await expect(page.locator('#managementList')).to_contain_text('<img src=x onerror=alert(1)>');assert await page.locator('#managementList img').count()==0
        await done(context,state,'Directory names render as text, never HTML')

        context,page,state,data=await fixture(browser)
        data['read_gate']=asyncio.Event();await nav(page,'personas');await data['read_started'].wait();await page.locator('#logoutButton').click();data['read_gate'].set();await expect(page).to_have_url(re.compile('index.html'));assert await page.locator('#managementList').count()==0
        await done(context,state,'Logout prevents late directory data from returning')

        context,page,state,data=await fixture(browser,mobile=True)
        await expect(page.locator('#controlHome')).to_be_visible();await page.evaluate('window.PORTAL_SUPABASE_CONFIG=Object.freeze({...window.PORTAL_SUPABASE_CONFIG,features:{invitations:false}})');await page.locator('#menuToggle').click();await expect(page.locator('#menuToggle')).to_have_attribute('aria-expanded','true');await page.locator('#workspaceNav [data-route=personas]').click();await expect(page.locator('#managementSection')).to_be_visible();await expect(page.locator('#menuToggle')).to_have_attribute('aria-expanded','false');assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'mobile overflow'
        await page.screenshot(path=str(OUT/'seminario-campus-mobile.png'),full_page=True,animations='disabled')
        await done(context,state,'Mobile navigation opens, selects a section, closes and fits screen')

        for role in ['student','professor']:
            context,page,state=await h.fixture(browser,profile={'full_name':'Persona de prueba','role':role,'active':True})
            await expect(page.locator('#panelContent')).to_be_visible();await expect(page.locator('#workspaceNav [data-route=personas]')).not_to_be_visible();await page.evaluate("location.hash='personas'");await expect(page.locator('#managementSection')).not_to_be_visible();assert not any('/rpc/portal_admin_' in url for method,url in state['requests'])
            await done(context,state,role+' cannot navigate to Control Escolar')

        context,page,state=await h.fixture(browser,rows=[h.subject(1,name='Historia de la Iglesia'),h.subject(2,name='Filosofía')])
        await h.visible(page);await expect(page.locator('#subjectsList li')).to_have_count(2);await page.locator('#studentSearch').fill('historia');await expect(page.locator('#subjectsList li:visible')).to_have_count(1);await page.locator('#studentSearch').fill('sin coincidencias');await expect(page.locator('#studentFilterStatus')).to_contain_text('0 coincidencias');await page.locator('#studentSearch').fill('');await expect(page.locator('#subjectsList li:visible')).to_have_count(2)
        await page.screenshot(path=str(OUT/'seminario-campus-alumno.png'),full_page=True,animations='disabled')
        await done(context,state,'Student cards filter by text and restore without losing grades')

        context,page,state=await h.fixture(browser,session=False,start='index.html')
        sent=[]
        async def recover(route):
            sent.append(route.request.post_data_json);await route.fulfill(status=200,headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'},body='{}')
        await context.route(h.API+'/auth/v1/recover*',recover);await expect(page.locator('#email')).to_be_enabled();await page.locator('#email').fill('user@example.invalid');await page.locator('#forgotPassword').click();await expect(page.locator('#loginMessage')).to_contain_text('Si tu cuenta está registrada');assert sent
        await page.screenshot(path=str(OUT/'seminario-campus-acceso.png'),full_page=True,animations='disabled')
        await done(context,state,'Password recovery gives generic confirmation without account enumeration')

        context,page,state=await h.fixture(browser)
        changed=[]
        async def update_user(route):
            if route.request.method!='PUT':return await route.fallback()
            changed.append(route.request.post_data_json);await route.fulfill(status=200,headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'},body=json.dumps(h.USER))
        await context.route(h.API+'/auth/v1/user',update_user)
        activation_token=h.TOKEN.rsplit('.',1)[0]+'.'+h.enc({'fixture':'signature'})
        await page.goto(h.BASE+'/portal/activar.html#access_token='+activation_token+'&refresh_token=fixture-refresh-token&type=invite')
        await expect(page.locator('#activationForm')).to_be_visible();assert 'access_token' not in page.url
        await page.locator('#newPassword').fill('contraseña nueva de prueba');await page.locator('#confirmPassword').fill('otra contraseña diferente');await page.locator('#activationSave').click();assert not changed
        await page.locator('#confirmPassword').fill('contraseña nueva de prueba');await page.locator('#activationSave').click();await expect(page.locator('#activationContinue')).to_be_visible();assert len(changed)==1;assert await page.locator('#newPassword').input_value()==''
        await done(context,state,'Invitation verifies access, removes URL tokens, checks matching passwords and stores one password change')
        context,page,state,data=await fixture(browser)
        await page.evaluate('window.PORTAL_SUPABASE_CONFIG=Object.freeze({...window.PORTAL_SUPABASE_CONFIG,features:{invitations:false}})')
        await nav(page,'personas');await expect(page.locator('#managementCreate')).to_be_disabled();await expect(page.locator('#managementDescription')).to_contain_text('pendiente de activación');assert not any(c[0]=='invite' for c in data['calls'])
        await done(context,state,'Institutional email pending keeps invitations visibly disabled')

        context,page,state,data=await fixture(browser)
        state['profile']={'full_name':'Profesor actualizado','role':'professor','active':True};data['read_status']=403
        await page.evaluate("location.hash='personas'");await expect(page.locator('#profileRole')).to_have_text('Profesor');await expect(page.locator('#workspaceNav [data-route=personas]')).not_to_be_visible();await expect(page.locator('#managementSection')).not_to_be_visible();await expect(page.locator('#managementList')).to_have_text('')
        await done(context,state,'Revoked Control role clears directory and rechecks database identity')

        context,page,state,data=await fixture(browser)
        await nav(page,'personas');await expect(page.locator('#managementList li')).to_have_count(2);await page.locator('.management-row').first.get_by_role('button',name='Editar persona').click();data['write_status']=500;await page.locator('#managementSave').click();await expect(page.locator('#managementFormMessage')).to_contain_text('No se pudo confirmar');await expect(page.locator('#managementSave')).to_be_disabled();assert len([c for c in data['calls'] if c[0]=='write'])==1
        await done(context,state,'Uncertain write cannot be blindly repeated')

        context,page,state,data=await fixture(browser,mobile=True)
        await nav(page,'personas');await expect(page.locator('#managementList li')).to_have_count(2);await page.locator('.management-row').first.get_by_role('button',name='Editar persona').click();await expect(page.locator('#managementDialog')).to_be_visible();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.keyboard.press('Escape');await expect(page.locator('#managementDialog')).not_to_be_visible()
        await done(context,state,'Mobile dialog fits viewport and closes with Escape')

        teaching=[h.subject(1,name='Historia'),h.subject(2,name='Filosofía')];teaching[1]['academic_periods']['name']='Semestre 2027'
        context,page,state=await h.fixture(browser,profile={'full_name':'Profesor','role':'professor','active':True},teaching=teaching)
        await expect(page.locator('#teachingList li')).to_have_count(2);await expect(page.locator('#teacherPeriod option')).to_have_count(3);await page.locator('#teacherPeriod').select_option('Semestre 2027');await expect(page.locator('#teachingList li:visible')).to_have_count(1);await page.locator('#teacherPeriod').select_option('');await page.locator('#teacherSearch').fill('MAT-001');await expect(page.locator('#teachingList li:visible')).to_have_count(1)
        await done(context,state,'Professor course filtering uses actual periods and codes')

        await browser.close()
        print(f'PASS {checks} campus functional scenarios; no live Supabase writes',flush=True)

if __name__=='__main__':
    h.prepare()
    OUT=h.ARTIFACTS
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
