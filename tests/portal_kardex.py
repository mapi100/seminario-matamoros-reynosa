"""Kardex: SDK real y API simulada, sin estudiantes ni servicios reales."""
import asyncio,copy,json,shutil,re,html,subprocess
from pathlib import Path
from playwright.async_api import async_playwright,expect
import portal_subjects as h

SAMPLE=json.loads((Path(__file__).parent/'fixtures/kardex.json').read_text())['record']
STUDENT=SAMPLE['student']['id'];PROGRAM=SAMPLE['program']['id']
checks=0

async def fixture(browser,role='control_escolar',mobile=False):
    context,page,state=await h.fixture(browser,profile={'full_name':'Control de prueba' if role=='control_escolar' else 'Usuario de prueba','role':role,'active':True},start='panel.html#inicio',mobile=mobile)
    record=copy.deepcopy(SAMPLE);record.pop('notes',None);record['method']['display_scale']='10';record['program']['display_scale']='10'
    data={'record':record,'institution':record['institution'],'programs':[record['program']],'issues':{},'calls':[],'read_status':200,'write_status':200,'issue_status':200,'issue_started':asyncio.Event(),'gate':None,'read_started':asyncio.Event(),'errors':[],'next_subjects':False}
    def project(program):
        result=copy.deepcopy(data['record'])
        if program is None:
            result['program']=None;result['method']={'repeat_policy':'all','weighted':False,'display_scale':'100'}
            for row in result['rows']:row['counted']=row['score'] is not None
            finals=[row['score'] for row in result['rows'] if row['score'] is not None];result['stats']['average']=sum(finals)/len(finals) if finals else None;result['stats']['counted']=len(finals);result['stats']['graded']=len(finals);result['stats']['enrollments']=len(result['rows']);result['final_ready']=False;result['final_reasons']=['Selecciona un programa para generar un kardex final']
        return result
    async def api_route(route):
        req=route.request
        if '/rpc/portal_kardex_' not in req.url:return await route.fallback()
        args=req.post_data_json;name=req.url.rsplit('/',1)[-1];data['calls'].append((name,copy.deepcopy(args)));headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'}
        async def reply(status,value):return await route.fulfill(status=status,headers=headers,body=json.dumps(value))
        try:
            if name=='portal_kardex_read':
                data['read_started'].set()
                if data['gate']:await data['gate'].wait()
                if data['read_status']!=200:
                    if data['read_status']==403:state['profile']['active']=False
                    return await reply(data['read_status'],{'code':'42501' if data['read_status']==403 else 'PGRST202','message':'Fixture read error'})
                kind=args['p_resource'];items=[]
                if kind=='programs':items=copy.deepcopy(data['programs'])
                elif kind=='students':
                    items=[{'id':STUDENT,'full_name':data['record']['student']['full_name'],'active':True,'student_number':data['record']['student']['student_number'],'curp':data['record']['student']['curp'],'enrollments':4},{'id':'20000000-0000-4000-8000-000000000002','full_name':'Alumno inactivo','active':False,'student_number':'MR-002','curp':None,'enrollments':0}]
                    needle=args['p_search'].lower()
                    if needle:items=[s for s in items if needle in json.dumps(s,ensure_ascii=False).lower()]
                elif kind=='record':return await reply(200,project(args['p_program']))
                elif kind=='settings':return await reply(200,{'institution':data['institution']})
                elif kind=='curriculum':
                    items=[{**row,'included':True} for row in data['record']['curriculum']]
                    needle=args['p_search'].lower()
                    if needle:items=[row for row in items if needle in (row['code']+' '+row['name']).lower()]
                elif kind=='issues':items=[{'id':i['id'],'folio':i['folio'],'kind':i['kind'],'issued_at':i['issued_at'],'student_name':i['snapshot']['student']['full_name'],'program_name':i['snapshot']['program']['name'] if i['snapshot']['program'] else None} for i in data['issues'].values()]
                elif kind=='issue':return await reply(200,data['issues'][args['p_issue']])
                else:raise AssertionError(kind)
                start=args['p_offset'];end=start+args['p_limit'];return await reply(200,{'items':items[start:end],'has_more':len(items)>end})
            if name=='portal_kardex_write':
                if data['write_status']!=200:return await reply(data['write_status'],{'code':'PT409','message':'El expediente cambió; actualiza antes de guardar'})
                action=args['p_action'];body=args['p_data'];entity=body.get('id',STUDENT)
                if action=='student_save':
                    assert 'role' not in body and 'score' not in body;data['record']['student'].update({k:v for k,v in body.items() if k not in ['student_id','revision']});data['record']['student']['revision']+=1
                elif action=='institution_save':data['institution'].update(body);data['institution']['revision']+=1
                elif action=='program_save':
                    if 'id' in body:next(p for p in data['programs'] if p['id']==body['id']).update(body)
                    else:entity='20000000-0000-4000-8000-000000000090';data['programs'].append({**body,'id':entity})
                elif action=='curriculum_save':
                    assert len(body['items'])==2
                    for item in body['items']:assert 'score' not in item
                elif action=='academic_save':
                    for item in body['items']:
                        assert 'score' not in item;row=next(r for r in data['record']['rows'] if r['enrollment_id']==item['enrollment_id']);row.update(item);row['revision']+=1
                else:raise AssertionError(action)
                return await reply(200,{'saved':True,'id':entity})
            if name=='portal_kardex_issue':
                data['issue_started'].set();id=args['p_request_id']
                if id not in data['issues']:
                    snapshot=project(args['p_program']);snapshot['notes']=args['p_notes']
                    data['issues'][id]={'id':id,'folio':'KDX-2026-000001','kind':args['p_kind'],'issued_at':'2026-10-22T20:00:00+00:00','snapshot':snapshot}
                if data['issue_status']!=200:return await reply(data['issue_status'],{'code':'XX000','message':'Lost reply'})
                return await reply(200,{'saved':True,'id':id,'folio':data['issues'][id]['folio']})
            raise AssertionError(name)
        except Exception as error:
            if 'Target page, context or browser has been closed' not in str(error):data['errors'].append(str(error))
            await route.abort()
    await context.route(h.API+'/**',api_route)
    return context,page,state,data

async def done(c,state,data,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors'];checks+=1;print('PASS '+label,flush=True);await c.close()

async def open_record(page):
    await page.evaluate('location.hash="kardex"');await expect(page.locator('#kardexStudents li')).to_have_count(2);await page.locator('#kardexStudents li').first.get_by_role('button',name='Ver historial').click();await expect(page.locator('#kardexPreview .kardex-table tbody tr')).to_have_count(7);await expect(page.locator('#kardexIssues li')).to_have_count(1)

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        c,page,state,data=await fixture(browser);await open_record(page);await expect(page.locator('#kardexPreview')).to_contain_text('VISTA PREVIA');await expect(page.locator('#kardexPreview .kardex-summary')).to_contain_text('80');await expect(page.locator('#kardexPreview')).to_contain_text('Historia');await expect(page.locator('#kardexPreview')).to_contain_text('Filosofía')
        await done(c,state,data,'Control sees complete chronological history, grades and automatically computed average')

        c,page,state,data=await fixture(browser);await page.evaluate('location.hash="kardex"');await expect(page.locator('#kardexStudents li')).to_have_count(2);await page.locator('#kardexSearch').fill('MR-001');await page.locator('#kardexSearchForm button').click();await expect(page.locator('#kardexStudents li')).to_have_count(1)
        await done(c,state,data,'student search accepts name, matricula and includes inactive alumni')

        for role in ['student','professor']:
            c,page,state,data=await fixture(browser,role);await page.evaluate('location.hash="kardex"');await expect(page.locator('#kardexSection')).to_be_hidden();assert not data['calls'];await expect(page.locator('#workspaceNav [data-route=kardex]')).to_be_hidden()
            await done(c,state,data,role+' cannot open Kardex even by forged URL')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#kardexProgram').select_option(PROGRAM);await expect(page.locator('#kardexPreview .kardex-summary')).to_contain_text('9.67');await expect(page.locator('#kardexRequirements')).to_be_hidden();await page.locator('#kardexKind').select_option('final');await page.locator('#kardexIssue').click();await expect(page.locator('#kardexDialog')).to_contain_text('KDX-2026-000001');assert len(data['issues'])==1
        await page.screenshot(path=str(h.ARTIFACTS/'seminario-kardex-emitido.png'),full_page=True)
        await done(c,state,data,'program policy/scale and complete-plan final issue produce a fixed internal folio')

        c,page,state,data=await fixture(browser);data['record']['student']['student_number']=None
        await open_record(page);await expect(page.locator('#kardexIssue')).to_be_disabled();await page.locator('#kardexStudentData').click();await page.locator('#kx-student_number').fill('MR-2026-001');await page.locator('#kardexSave').click();await expect(page.locator('#kardexDialog')).to_have_count(0);await expect(page.locator('#kardexIssue')).to_be_enabled()
        await done(c,state,data,'matricula can be completed intuitively before issuing')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#kardexInstitution').click();await page.locator('#kx-officer_name').fill('Responsable de prueba');await page.locator('#kardexSave').click();await expect(page.locator('#kardexDialog')).to_have_count(0);await expect(page.locator('#kardexPreview')).to_contain_text('Responsable de prueba');assert data['institution']['cct'] is None or data['institution']['cct']==''
        await page.locator('#kardexPrograms').click();await page.get_by_role('button',name='Nuevo programa',exact=True).click();await page.locator('#kx-name').fill('Formación teológica');await page.locator('#kx-plan_name').fill('Plan de prueba');await page.locator('#kx-display_scale').select_option('10');await page.locator('#kardexSave').click();await expect(page.locator('#kardexDialog')).to_have_count(0);await expect(page.locator('#kardexProgram option')).to_have_count(3);assert data['programs'][-1]['pass_mark'] is None and data['programs'][-1]['rvoe_number']==''
        await done(c,state,data,'plantel and new programs can be configured without inventing CCT, RVOE or passing criteria')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#kardexAcademicData').click();await expect(page.locator('#kardexDialog')).to_contain_text('Clasificar materias');await page.locator('[aria-label="Evaluación para filas sin tipo"]').select_option('EXT');await page.get_by_role('button',name='Aplicar a filas sin evaluación',exact=True).click();await page.locator('#kardexSave').click();await expect(page.locator('#kardexDialog')).to_have_count(0);assert any(call[0]=='portal_kardex_write' and call[1]['p_action']=='academic_save' for call in data['calls'])
        await done(c,state,data,'academic classification saves metadata without modifying grades')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#kardexPrograms').click();await page.get_by_role('button',name='Materias y créditos',exact=True).click();await expect(page.locator('#kardexDialog input[type=number]')).to_have_count(4);await page.locator('#kardexDialog input[type=number]').first.fill('8');await page.locator('#kardexSave').click();await expect(page.locator('#kardexDialog')).to_have_count(0)
        await done(c,state,data,'curriculum credits/hours are configured once by program')

        c,page,state,data=await fixture(browser);await open_record(page);data['issue_status']=500;await page.locator('#kardexIssue').click();await expect(page.locator('#kardexIssue')).to_have_text('Comprobar / reintentar emisión');await expect(page.locator('#kardexProgram')).to_be_disabled();data['issue_status']=200;await page.locator('#kardexIssue').click();await expect(page.locator('#kardexDialog')).to_contain_text('KDX-2026-000001');calls=[args for name,args in data['calls'] if name=='portal_kardex_issue'];assert len(calls)==2 and calls[0]==calls[1] and len(data['issues'])==1
        await done(c,state,data,'lost issue response can safely retry the identical request without duplicate documents')

        c,page,state,data=await fixture(browser);await open_record(page);data['issue_status']=500;await page.locator('#kardexIssue').click();await expect(page.locator('#kardexKind')).to_be_disabled();await page.evaluate('location.hash="inicio"');data['issue_status']=200;await open_record(page);await expect(page.locator('#kardexKind')).to_be_enabled();await expect(page.locator('#kardexNotes')).to_be_enabled();await expect(page.locator('#kardexIssue')).to_have_text('Emitir kardex');await expect(page.locator('#kardexIssues')).to_contain_text('KDX-2026-000001')
        await done(c,state,data,'returning after uncertain issue resets controls and shows the existing issued copy')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#kardexIssue').click();await expect(page.locator('#kardexDialog')).to_be_visible();await page.evaluate('() => {window.print=()=>{window.__printedKardex=document.getElementById("kardexPrintRoot").textContent;window.__printedHtml=document.getElementById("kardexPrintRoot").outerHTML;};}');before=len([a for n,a in data['calls'] if n=='portal_kardex_read' and a['p_resource']=='issue']);await page.locator('#kardexDialog').get_by_role('button',name='Imprimir / Guardar PDF',exact=True).click();await page.wait_for_function('window.__printedKardex');assert 'Seminarista Alfa' in await page.evaluate('window.__printedKardex');after=len([a for n,a in data['calls'] if n=='portal_kardex_read' and a['p_resource']=='issue']);assert after==before+1;await expect(page.locator('#kardexPrintRoot')).to_have_count(0)
        markup=await page.evaluate('window.__printedHtml');links=await page.locator('link[rel=stylesheet]').evaluate_all('(links)=>links.map(link=>link.outerHTML).join("")');pdfpage=await c.new_page()
        await pdfpage.set_content('<html><head><title>Kardex de muestra con datos ficticios</title><base href="'+html.escape(h.BASE+'/portal/',quote=True)+'">'+links+'</head><body class="kardex-printing">'+markup+'</body></html>',wait_until='networkidle')
        pdfpath=h.ARTIFACTS/'seminario-kardex-ejemplo.pdf';await pdfpage.pdf(path=str(pdfpath),prefer_css_page_size=True,print_background=True);text=subprocess.run(['pdftotext',str(pdfpath),'-'],check=True,capture_output=True,text=True).stdout
        assert text.count('\f')==1 and 'Filosofía' in text and 'Control Escolar' in text and 'KDX-2026-000001' in text;await pdfpage.close()
        await done(c,state,data,'printing refreshes server authorization, prints issued copy and clears temporary document')

        c,page,state,data=await fixture(browser);await open_record(page)
        # Exercise print CSS with a complete, long transcript, not a cropped screen capture.
        originals=copy.deepcopy(data['record']['rows']);data['record']['rows']=[]
        for n in range(120):
            row=copy.deepcopy(originals[n%4]);row['code']=f'MAT-{n+1:03}';row['name']=f'Materia de prueba {n+1:03}';row['period_id']='20000000-0000-4000-8000-'+str(100+n//10).zfill(12);row['period_name']=f'Periodo {n//10+1:02}';data['record']['rows'].append(row)
        await page.locator('#kardexIssue').click();await expect(page.locator('#kardexDialog')).to_be_visible();await page.evaluate('() => {window.print=()=>{window.__printHtml=document.getElementById("kardexPrintRoot").outerHTML;};}')
        await page.locator('#kardexDialog').get_by_role('button',name='Imprimir / Guardar PDF',exact=True).click();await page.wait_for_function('window.__printHtml');markup=await page.evaluate('window.__printHtml');links=await page.locator('link[rel=stylesheet]').evaluate_all('(links)=>links.map(link=>link.outerHTML).join("")')
        pdfpage=await c.new_page();await pdfpage.set_content('<html><head><base href="'+html.escape(h.BASE+'/portal/',quote=True)+'">'+links+'</head><body class="kardex-printing">'+markup+'</body></html>',wait_until='networkidle')
        pdfpath=h.ARTIFACTS/'seminario-kardex-ejemplo-120-materias.pdf';await pdfpage.pdf(path=str(pdfpath),prefer_css_page_size=True,print_background=True);text=subprocess.run(['pdftotext',str(pdfpath),'-'],check=True,capture_output=True,text=True).stdout
        assert 'Materia de prueba 120' in text and 'Control Escolar' in text and 'KDX-2026-000001' in text and text.count('Evaluación')>=2 and len(text.split('\f'))>2
        await pdfpage.close();await done(c,state,data,'multipage PDF preserves all 120 subjects, repeats table headings and includes signatures')

        c,page,state,data=await fixture(browser);await open_record(page);await page.locator('#kardexIssue').click();await expect(page.locator('#kardexDialog')).to_be_visible();issue=next(iter(data['issues'].values()));issue['snapshot']['student']['full_name']='=2+3';issue['snapshot']['rows'][0]['name']='+cmd'
        async with page.expect_download() as download_info:await page.locator('#kardexDialog').get_by_role('button',name='Descargar CSV',exact=True).click()
        download=await download_info.value;path=await download.path();text=Path(path).read_text(encoding='utf-8-sig');assert "'=2+3" in text and "'+cmd" in text and 'KDX-2026-000001' in text
        await done(c,state,data,'CSV export uses issued records and neutralizes spreadsheet formulas')

        c,page,state,data=await fixture(browser);await open_record(page);data['record']['student']['full_name']='<img src=x onerror=alert(1)>'
        await page.locator('#kardexRefresh').click();await expect(page.locator('#kardexPreview')).to_contain_text('<img');await expect(page.locator('#kardexPreview img')).to_have_count(1)
        await done(c,state,data,'record fields render as literal text, not injected HTML')

        c,page,state,data=await fixture(browser);await open_record(page);data['read_status']=403;await page.locator('#kardexRefresh').click();await expect(page.locator('#kardexPreview .kardex-paper')).to_have_count(0);await expect(page.locator('#kardexSection')).to_be_hidden()
        await done(c,state,data,'revoked Control access clears private history and rechecks profile')

        c,page,state,data=await fixture(browser);await open_record(page);data['gate']=asyncio.Event();data['read_started'].clear();await page.locator('#kardexRefresh').click();await data['read_started'].wait();await page.evaluate('location.hash="inicio"');data['gate'].set();await page.wait_for_timeout(100);await expect(page.locator('#kardexPreview .kardex-paper')).to_have_count(0)
        await done(c,state,data,'late history replies cannot restore private records after leaving')

        c,page,state,data=await fixture(browser,mobile=True);await open_record(page);assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(h.ARTIFACTS/'seminario-kardex-movil.png'),full_page=True)
        await done(c,state,data,'mobile Kardex workflow fits the screen')
        c,page,state,data=await fixture(browser);await open_record(page);await page.screenshot(path=str(h.ARTIFACTS/'seminario-kardex-historial.png'),full_page=True)
        await done(c,state,data,'desktop history preview and issue actions are ready for review')
        await browser.close();print(f'PASS {checks} Kardex browser scenarios; mocked API only')

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
