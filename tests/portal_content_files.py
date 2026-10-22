"""Subida docente, descarga privada y presentación. SDK real/API simulada."""
import asyncio,copy,json,shutil
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_learning as l
import portal_workspace as w

checks=0
FID='da000000-0000-4000-8000-000000000001'
DOC='application/vnd.openxmlformats-officedocument.wordprocessingml.document'

def file_row(topic=l.TOPIC):
    return {'id':FID,'name':'Lectura.pdf','size':30,'mimetype':'application/pdf','object_path':f'{l.COURSE}/{topic}/db000000-0000-4000-8000-000000000001/lectura.pdf'}

async def fixture(browser,role='professor',mobile=False,with_file=False):
    data=l.sample_data(role)
    if with_file:data['course']['modules'][0]['topics'][0]['files']=[file_row()]
    context,page,state,data=await l.fixture(browser,role,mobile=mobile,route=f'curso/{l.COURSE}/contenido',data=data)
    extra={'calls':[],'objects':{file_row()['object_path']:b'%PDF-1.4 fixture'} if with_file else {},'attach_fail':0,'lost_upload':0,'fail_upload':0,'attach_gate':None,'upload_gate':None,'upload_started':asyncio.Event(),'errors':[],'list_status':200,'upload_status':503}
    headers={'Access-Control-Allow-Origin':'*','Content-Type':'application/json'}
    async def route_api(route):
        req=route.request;path=urlparse(req.url).path
        def reply(status,result):return route.fulfill(status=status,headers=headers,body=json.dumps(result))
        try:
            if '/storage/v1/object/' in path and '/portal-content' in path:
                if req.method=='GET':
                    extra['calls'].append(('download',path));return await route.fulfill(status=200,body=b'%PDF-1.4 fixture',content_type='application/pdf')
                if req.method=='DELETE':
                    body=req.post_data_json;extra['calls'].append(('remove',body))
                    for item in body['prefixes']:extra['objects'].pop(item,None)
                    return await reply(200,[{'name':item} for item in body['prefixes']])
                if req.method=='POST':
                    extra['upload_started'].set();extra['calls'].append(('upload',path));object_path=path.split('/portal-content/',1)[1]
                    if extra['upload_gate']:await extra['upload_gate'].wait()
                    if extra['fail_upload']:
                        extra['fail_upload']-=1;return await reply(extra['upload_status'],{'error':'Unavailable','statusCode':str(extra['upload_status']),'message':'Fixture'})
                    extra['objects'][object_path]=b'fixture'
                    if extra['lost_upload']:
                        extra['lost_upload']-=1;return await reply(503,{'error':'Lost reply','statusCode':'503','message':'Fixture'})
                    return await reply(200,{'Key':'portal-content/'+object_path,'Id':FID})
            if path.endswith('/portal_content_files'):
                args=req.post_data_json;action=args['p_action'];body=args['p_data'];extra['calls'].append((action,copy.deepcopy(args)))
                topic=next(t for m in data['course']['modules'] for t in m['topics'] if t['id']==args['p_topic']);rows=topic.setdefault('files',[])
                if action=='list':
                    if extra['list_status']!=200:return await reply(extra['list_status'],{'code':'PGRST202','message':'Fixture'})
                    pending=[path for path in extra['objects'] if path.startswith(l.COURSE+'/'+topic['id']+'/') and not any(row['object_path']==path for row in rows)]
                    return await reply(200,{'items':rows,'pending':pending,'can_manage':role!='student'})
                if action=='attach':
                    if extra['attach_gate']:await extra['attach_gate'].wait()
                    if body['object_path'] not in extra['objects']:return await reply(404,{'code':'PT404','message':'Primero sube este archivo'})
                    row=next((row for row in rows if row['object_path']==body['object_path']),None)
                    if row is None:
                        row={'id':f'da000000-0000-4000-8000-{len(rows)+1:012d}','name':body['name'],'size':20,'mimetype':DOC if body['name'].endswith('.docx') else 'application/pdf','object_path':body['object_path']};rows.append(row)
                    if extra['attach_fail']:
                        extra['attach_fail']-=1;return await reply(500,{'code':'XX000','message':'Lost registration reply'})
                    return await reply(200,{'saved':True,'id':row['id']})
                if action=='remove':
                    topic['files']=[row for row in rows if row['id']!=body['id']];return await reply(200,{'saved':True,'id':body['id']})
                raise AssertionError(action)
            await route.fallback()
        except Exception as error:
            if 'Target page, context or browser has been closed' not in str(error):extra['errors'].append(str(error))
            await route.abort()
    await context.route(h.API+'/**',route_api)
    await expect(page.get_by_role('button',name='Nueva unidad',exact=True)).to_be_visible() if role!='student' else await expect(page.locator('#learningRoot')).to_be_visible()
    return context,page,state,data,extra

async def done(c,state,data,x,label):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors'];assert not x['errors'],x['errors'];checks+=1;print('PASS '+label,flush=True);await c.close()

async def add(page,name='Tema con archivos'):
    await page.get_by_role('button',name='Agregar contenido',exact=True).click();await page.locator('#learning-field-title').fill(name)

async def choose(page,files):
    await page.locator('#learningDialog input[type=file]').set_input_files(files)

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for role in ['professor','control_escolar']:
            c,page,state,data,x=await fixture(browser,role)
            await add(page);await page.locator('#learning-field-url').fill('https://example.org/lectura');await choose(page,[{'name':'Guía.docx','mimeType':DOC,'buffer':b'word fixture'},{'name':'Lectura.pdf','mimeType':'application/pdf','buffer':b'%PDF fixture'}]);await page.locator('#learningSave').click();await expect(page.locator('#learningDialog')).to_have_count(0)
            topic=data['course']['modules'][0]['topics'][-1];assert len(topic['files'])==2 and topic['url']=='https://example.org/lectura'
            assert len([r for r in data['writes'] if r['p_action']=='topic_save'])==1
            await expect(page.get_by_role('button',name='Descargar Guía.docx',exact=True)).to_be_visible()
            await done(c,state,data,x,role+' creates one topic with Word, PDF and a link')

        for files,label in [([{'name':'programa.exe','mimeType':'application/octet-stream','buffer':b'bad'}],'unsupported file'),([{'name':'grande.pdf','mimeType':'application/pdf','buffer':b'0'*(10*1024*1024+1)}],'oversize file')]:
            c,page,state,data,x=await fixture(browser);await add(page);await choose(page,files);await page.locator('#learningSave').click();await expect(page.locator('.content-file-message')).to_contain_text('Revisa');assert not data['writes'] and not x['calls']
            await done(c,state,data,x,label+' rejected before creating topic or upload')

        c,page,state,data,x=await fixture(browser);await add(page);await choose(page,[{'name':str(i)+'.pdf','mimeType':'application/pdf','buffer':b'x'} for i in range(6)]);await page.locator('#learningSave').click();await expect(page.locator('.content-file-message')).to_contain_text('hasta 5');assert not data['writes']
        await done(c,state,data,x,'file count limit checked before creating topic')

        for lost in ['attach_fail','lost_upload','fail_upload']:
            c,page,state,data,x=await fixture(browser);x[lost]=1
            await add(page);await choose(page,[{'name':'Reintento.pdf','mimeType':'application/pdf','buffer':b'%PDF fixture'}]);await page.locator('#learningSave').click();await expect(page.locator('#learningDialogMessage')).to_contain_text('tema quedó guardado');await expect(page.locator('#learning-field-title')).to_be_disabled()
            await page.get_by_role('button',name='Reintentar subida',exact=True).click();await expect(page.locator('#learningDialog')).to_have_count(0)
            assert len([r for r in data['writes'] if r['p_action']=='topic_save'])==1
            assert len(data['course']['modules'][0]['topics'][-1]['files'])==1
            if lost!='fail_upload':assert len([r for k,r in x['calls'] if k=='upload'])==1
            await done(c,state,data,x,lost+' resumes without duplicate topic/file')

        c,page,state,data,x=await fixture(browser);x['fail_upload']=1;x['upload_status']=403
        await add(page);await choose(page,[{'name':'Limite.pdf','mimeType':'application/pdf','buffer':b'x'}]);await page.locator('#learningSave').click();await expect(page.locator('#learningDialogMessage')).to_contain_text('tema quedó guardado');await expect(page.get_by_role('button',name='Reintentar subida',exact=True)).to_be_enabled()
        await done(c,state,data,x,'Storage rejection preserves the saved topic and retry dialog without treating it as account revocation')

        c,page,state,data,x=await fixture(browser,'student',with_file=True)
        await page.locator('.learning-topic summary').click();await expect(page.get_by_role('button',name='Descargar Lectura.pdf',exact=True)).to_be_visible();await expect(page.locator('input[type=file]')).to_have_count(0)
        async with page.expect_download() as download_info:await page.get_by_role('button',name='Descargar Lectura.pdf',exact=True).click()
        download=await download_info.value;assert download.suggested_filename=='Lectura.pdf'
        await done(c,state,data,x,'student downloads published material through authenticated Storage API')

        c,page,state,data,x=await fixture(browser,with_file=True)
        await page.locator('.learning-topic summary').click();await page.get_by_role('button',name='Editar contenido',exact=True).click();await expect(page.locator('#learningDialog .content-file-message')).to_contain_text('1 archivos')
        page.once('dialog',lambda d:d.accept());await page.get_by_role('button',name='Quitar',exact=True).click();await expect(page.locator('#learningDialog .content-file-message')).to_contain_text('Todavía no hay');assert not data['course']['modules'][0]['topics'][0]['files']
        await done(c,state,data,x,'teacher removes material with explicit confirmation')

        c,page,state,data,x=await fixture(browser);x['upload_gate']=asyncio.Event()
        await add(page);await choose(page,[{'name':'Salida.pdf','mimeType':'application/pdf','buffer':b'x'}]);await page.locator('#learningSave').click();await x['upload_started'].wait();await page.evaluate('window.PortalLearning.clear()');x['upload_gate'].set();await expect(page.locator('#learningDialog')).to_have_count(0);await page.wait_for_timeout(150);assert not any(k=='attach' for k,_ in x['calls'])
        await done(c,state,data,x,'clearing session during upload cannot revive dialog or register files afterward')

        c,page,state,data,x=await fixture(browser,mobile=True)
        await add(page);await expect(page.locator('#learningDialog input[type=file]')).to_be_visible();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(h.ARTIFACTS/'seminario-contenido-archivos-movil.png'))
        await done(c,state,data,x,'mobile file selection fits viewport')

        for mobile in [False,True]:
            c,page,state,data=await w.fixture(browser,mobile=mobile,teaching=[h.subject(1),h.subject(2)])
            await expect(page.locator('#teachingList li')).to_have_count(2)
            assert await page.evaluate('''()=>{const a=document.querySelector('#teachingSection').getBoundingClientRect(),b=document.querySelector('#controlHome').getBoundingClientRect();return a.bottom<=b.top || b.bottom<=a.top}''')
            assert await page.locator('.teaching-card').first.evaluate('(e)=>getComputedStyle(e,"::before").backgroundImage==="none"')
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.screenshot(path=str(h.ARTIFACTS/('seminario-control-sin-solapamiento-'+('movil' if mobile else 'escritorio')+'.png')),full_page=True)
            checks_label='Control home courses and administration do not overlap '+('mobile' if mobile else 'desktop')
            await done(c,state,{'errors':[]},{'errors':[]},checks_label)

        c,page,state,data,x=await fixture(browser)
        assert await page.locator('.learning-course-banner').evaluate('(e)=>getComputedStyle(e).backgroundImage==="none"')
        await page.evaluate(f'location.hash="curso/{l.COURSE}/inicio"');await expect(page.locator('.learning-module-picture')).to_have_count(1)
        assert await page.locator('.learning-module-picture').evaluate('(e)=>getComputedStyle(e).backgroundImage==="none"')
        await page.screenshot(path=str(h.ARTIFACTS/'seminario-clases-con-colores.png'),full_page=True)
        await done(c,state,data,x,'course banner and module tiles use color without photos')
        await browser.close();print(f'PASS {checks} content/layout browser scenarios; mock API only')

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
