"""Etapas: navegador con SDK real y API simulada, sin cuentas reales."""
import asyncio,copy,json,shutil
from playwright.async_api import async_playwright,expect
import portal_kardex as k
h=k.h
STAGES=[{'code':'introductorio','name':'Curso Introductorio','ecclesial_name':'Etapa propedéutica','semesters':2},
        {'code':'filosofia','name':'Filosofía','ecclesial_name':'Etapa discipular','semesters':6},
        {'code':'teologia','name':'Teología','ecclesial_name':'Etapa configuradora','semesters':8}]
PERIOD=k.SAMPLE['rows'][0]['period_id'];P2='10000000-0000-4000-8000-000000000099'
checks=0

def history(semester=3,code='filosofia',period=PERIOD):
    stage=next(s for s in STAGES if s['code']==code)
    return {'student_id':k.STUDENT,'period_id':period,'period_name':'Ago–Dic 2026','starts_on':'2026-08-01','ends_on':'2026-12-20',
            'stage_code':code,'stage_name':stage['name'],'ecclesial_name':stage['ecclesial_name'],'semesters':stage['semesters'],'semester':semester,'revision':1}

async def fixture(browser,role='control_escolar',mobile=False):
    c,page,state,kdata=await k.fixture(browser,role,mobile)
    data={'rows':[{'id':k.STUDENT,'full_name':'Seminarista de prueba','active':True,'student_number':'MR-001','stage_code':None,'semester':None,'revision':0}],
          'history':[],'calls':[],'status':200,'read_status':200,'gate':None,'started':asyncio.Event()}
    kdata['record']['formation_history']=[history()]
    async def route_api(route):
        req=route.request
        if '/rpc/portal_formation_' not in req.url:return await route.fallback()
        args=req.post_data_json;data['calls'].append(copy.deepcopy(args));headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'}
        async def reply(status,value):return await route.fulfill(status=status,headers=headers,body=json.dumps(value))
        if req.url.endswith('portal_formation_save'):
            if data['status']!=200:return await reply(data['status'],{'code':'PT409' if data['status']==409 else 'XX000','message':'La etapa cambió; actualiza la lista'})
            data['rows'][0].update(stage_code=args['p_stage'],semester=args['p_semester'],revision=data['rows'][0]['revision']+1)
            data['history']=[history(args['p_semester'],args['p_stage'],args['p_period'])]
            return await reply(200,{'saved':True})
        data['started'].set()
        if data['gate']:await data['gate'].wait()
        if data['read_status']!=200:
            if data['read_status']==403:state['profile']['active']=False
            return await reply(data['read_status'],{'code':'42501','message':'Acceso denegado'})
        kind=args['p_resource']
        if kind=='settings':return await reply(200,{'stages':STAGES,'periods':[{'id':PERIOD,'name':'Ago–Dic 2026'},{'id':P2,'name':'Ene–Jun 2027'}]})
        if kind in ['own','history']:return await reply(200,{'history':data['history']})
        assert kind=='students'
        rows=data['rows'];needle=args['p_search'].lower()
        rows=[r for r in rows if (not args['p_stage'] or r['stage_code']==args['p_stage']) and (not needle or needle in r['full_name'].lower())]
        return await reply(200,{'items':rows,'has_more':False})
    await c.route(h.API+'/**',route_api)
    return c,page,state,data,kdata

async def open_stages(page):
    await page.evaluate('location.hash="etapas"');await expect(page.locator('#formationStudents li')).to_have_count(1)

async def done(c,state,data,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];checks+=1
    print('PASS '+label,flush=True);await c.close()

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        c,page,state,data,kdata=await fixture(browser);await open_stages(page)
        for stage in STAGES:
            await page.locator('#formationStudents button').click();await page.locator('#formationStage').select_option(stage['code'])
            await expect(page.locator('#formationSemester option')).to_have_count(stage['semesters']+1)
            await page.locator('#formationSemester').select_option(str(stage['semesters']));await page.locator('#formationSave').click()
            await expect(page.locator('#formationDialog')).not_to_be_visible();await expect(page.locator('#formationStudents')).to_contain_text(stage['name']+' · Semestre '+str(stage['semesters']))
            call=next(x for x in reversed(data['calls']) if 'p_semester' in x);assert call['p_student']==k.STUDENT and call['p_period']==PERIOD
        await done(c,state,data,'Control assigns all three stages with exactly 2, 6 and 8 semesters')

        c,page,state,data,kdata=await fixture(browser);await open_stages(page);await page.locator('#formationStudents button').click()
        await page.locator('#formationStage').select_option('teologia');await page.locator('#formationSemester').select_option('8');await page.locator('#formationStage').select_option('introductorio')
        await expect(page.locator('#formationSemester')).to_have_value('');await expect(page.locator('#formationSemester option')).to_have_count(3)
        await page.locator('#formationCancel').click();assert not any('p_semester' in x for x in data['calls'])
        await page.locator('#formationPeriod').select_option(P2);await expect(page.locator('#formationStudents li')).to_have_count(1)
        await page.locator('#formationFilter').select_option('teologia');await expect(page.locator('#formationStudents li')).to_have_count(0)
        assert any(x.get('p_stage')=='teologia' and x.get('p_period')==P2 for x in data['calls'])
        await done(c,state,data,'stage changes clear an invalid semester; period and stage filters reach the server')

        for status in [409,500]:
            c,page,state,data,kdata=await fixture(browser);await open_stages(page);await page.locator('#formationStudents button').click()
            await page.locator('#formationStage').select_option('filosofia');await page.locator('#formationSemester').select_option('2');data['status']=status
            await page.locator('#formationSave').click();await expect(page.locator('#formationDialogStatus')).to_contain_text('cambió' if status==409 else 'No se pudo confirmar')
            if status==500:await expect(page.locator('#formationSave')).to_be_disabled()
            assert len([x for x in data['calls'] if 'p_semester' in x])==1
            await page.locator('#formationCancel').click();await done(c,state,data,'conflict or uncertain save '+str(status)+' does not resend automatically')

        c,page,state,data,kdata=await fixture(browser);await open_stages(page);data['rows'][0]['full_name']='<img src=x onerror=alert(1)>'
        await page.locator('#formationRefresh').click();await expect(page.locator('#formationStudents')).to_contain_text('<img src=x onerror=alert(1)>');await expect(page.locator('#formationStudents img')).to_have_count(0)
        data['read_status']=403;await page.locator('#formationRefresh').click();await expect(page.locator('#formationSection')).to_be_hidden();await expect(page.locator('#formationStudents li')).to_have_count(0)
        await done(c,state,data,'names render as text and revoked access removes student data')

        c,page,state,data,kdata=await fixture(browser);await open_stages(page);data['gate']=asyncio.Event();data['started'].clear()
        await page.locator('#formationRefresh').click();await data['started'].wait();await page.evaluate('location.hash="inicio"');data['gate'].set()
        await expect(page.locator('#formationSection')).to_be_hidden();await expect(page.locator('#formationStudents li')).to_have_count(0)
        await done(c,state,data,'a late read cannot restore formation data after navigation')

        c,page,state,data,kdata=await fixture(browser,'student');data['history']=[history()];await page.reload()
        await expect(page.locator('#formationOwnSummary')).to_contain_text('Filosofía · Semestre 3 de 6')
        await expect(page.locator('#workspaceNav [data-route=etapas]')).to_be_hidden()
        assert not any('p_semester' in x for x in data['calls']);await page.evaluate('location.hash="etapas"');await expect(page.locator('#formationSection')).to_be_hidden()
        await page.locator('#logoutButton').click();await expect(page).to_have_url(h.BASE+'/portal/index.html?estado=sesion_cerrada')
        await done(c,state,data,'students read their own trajectory without administration or write access')

        c,page,state,data,kdata=await fixture(browser,'professor');await page.evaluate('location.hash="etapas"')
        await expect(page.locator('#formationSection')).to_be_hidden();assert not data['calls']
        await done(c,state,data,'professors cannot open formation administration')

        c,page,state,data,kdata=await fixture(browser);await k.open_record(page)
        await expect(page.locator('#kardexPreview')).to_contain_text('Filosofía · Semestre 3 de 6')
        await page.locator('#kardexPrograms').click();await page.get_by_role('button',name='Editar programa',exact=True).click()
        await page.locator('#kx-formation_stage').select_option('filosofia');await page.locator('#kardexSave').click();await expect(page.locator('#kardexDialog')).to_have_count(0)
        assert next(x[1]['p_data'] for x in reversed(kdata['calls']) if x[0]=='portal_kardex_write')['formation_stage']=='filosofia'
        kdata['record']['curriculum'][0]['term']='1';kdata['record']['curriculum'][1]['term']='2'
        await page.locator('#kardexPrograms').click();await page.get_by_role('button',name='Materias y créditos',exact=True).click()
        await expect(page.locator('#kardexFields select[aria-label^="Semestre de"]')).to_have_count(2)
        await expect(page.locator('#kardexFields select[aria-label^="Semestre de"]').first.locator('option')).to_have_count(7)
        await done(c,state,data,'Kardex labels each period and plans offer bounded semester choices')

        for mobile in [False,True]:
            c,page,state,data,kdata=await fixture(browser,mobile=mobile);await open_stages(page)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.screenshot(path=str(h.ARTIFACTS/('seminario-etapas-movil.png' if mobile else 'seminario-etapas-escritorio.png')),full_page=True,animations='disabled')
            await page.locator('#formationStudents button').click();await page.locator('#formationStage').select_option('teologia');await page.locator('#formationSemester').select_option('8')
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await done(c,state,data,('mobile' if mobile else 'desktop')+' stage list and editor fit the screen')
        await browser.close();print(f'PASS {checks} formation browser scenarios; mocked API only',flush=True)

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
