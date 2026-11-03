"""PDF privados de perfil: navegador/SDK reales con API ficticia; sin datos reales."""
import asyncio,copy,json,re,shutil
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_personal_record as p
h=p.h;PDF=b'%PDF-1.4\nDocumento ficticio\n%%EOF';checks=0

def row(student,num=1,kind='bautismo',name='Boleta.pdf',state='ready',owner=None):
 fid=f'da030000-0000-4000-8000-{num:012d}'
 return {'id':fid,'student_id':student,'kind':kind,'name':name,'size':len(PDF),'object_path':student+'/'+fid+'.pdf','state':state,'uploaded_by':owner or h.UID,'created_at':'2026-11-03T12:00:00Z'}
async def fixture(browser,role='student',mobile=False,with_file=False,theme=None):
 c,page,state,data=await p.fixture(browser,role,mobile);target=data['row']['student']['id']
 x={'items':{target:[row(target)]if with_file else []},'objects':{},'calls':[],'counter':10,'fail':'','list_status':200,'upload_gate':None,'upload_started':asyncio.Event(),'read_gate':None,'read_started':asyncio.Event(),'errors':[]}
 if with_file:x['objects'][row(target)['object_path']]=PDF
 async def api(route):
  req=route.request;path=urlparse(req.url).path
  async def reply(status,value):return await route.fulfill(status=status,content_type='application/json',body=json.dumps(value),headers={'Access-Control-Allow-Origin':'*'})
  try:
   if '/storage/v1/object/'in path and '/portal-personal'in path:
    if req.method=='GET':
     name=path.split('/portal-personal/',1)[1];x['calls'].append(('download',name));assert name in x['objects']
     return await route.fulfill(status=200,body=x['objects'][name],content_type='application/pdf',headers={'Access-Control-Allow-Origin':'*'})
    if req.method=='DELETE':
     x['calls'].append(('storage_remove',req.post_data_json))
     if x['fail']=='delete':x['fail']='';return await reply(503,{'statusCode':'503','error':'Fixture','message':'Delete not confirmed'})
     for name in req.post_data_json['prefixes']:x['objects'].pop(name,None)
     return await reply(200,[])
    if req.method=='POST':
     name=path.split('/portal-personal/',1)[1];x['calls'].append(('upload',name));x['upload_started'].set()
     if x['upload_gate']:await x['upload_gate'].wait()
     f=next(f for files in x['items'].values()for f in files if f['object_path']==name)
     if x['fail']=='upload403':x['fail']='';return await reply(403,{'statusCode':'403','error':'Forbidden','message':'Storage policy'})
     x['objects'][name]=PDF+b' '*max(0,f['size']-len(PDF))
     if x['fail']=='upload':x['fail']='';return await reply(503,{'statusCode':'503','error':'Fixture','message':'Lost upload reply'})
     return await reply(200,{'Key':'portal-personal/'+name,'Id':f['id']})
   if not path.endswith('/portal_student_files'):return await route.fallback()
   args=req.post_data_json;action=args['p_action'];student=args['p_student'];body=args['p_data'];x['calls'].append((action,copy.deepcopy(args)));files=x['items'].setdefault(student,[])
   if action=='list':
    x['read_started'].set()
    if x['read_gate']:await x['read_gate'].wait()
    if x['list_status']!=200:
     if x['list_status']==403:state['profile']['active']=False
     return await reply(x['list_status'],{'code':'42501'if x['list_status']==403 else'PGRST202','message':'Fixture'})
    return await reply(200,{'student_id':student,'items':files,'max_files':10,'max_size':5242880})
   if action=='reserve':
    if len(files)>=10:return await reply(400,{'code':'22023','message':'Ya hay 10 archivos'})
    x['counter']+=1;f=row(student,x['counter'],body['kind'],body['name'],'pending');f['size']=body['size'];files.append(f)
    if x['fail']=='reserve':x['fail']='';return await reply(503,{'code':'XX000','message':'Lost reservation'})
    return await reply(200,{'saved':True,'item':f})
   f=next((f for f in files if f['id']==body['id']),None)
   if action=='complete':
    assert f['object_path']in x['objects'];f['state']='ready'
    if x['fail']=='complete':x['fail']='';return await reply(503,{'code':'XX000','message':'Lost complete reply'})
    return await reply(200,{'saved':True,'item':f})
   if action=='remove':
    if not f:return await reply(200,{'saved':True,'removed':True,'id':body['id']})
    f['state']='deleting';return await reply(200,{'saved':True,'item':f})
   if action=='release':
    assert f['object_path']not in x['objects'];files.remove(f);return await reply(200,{'saved':True,'removed':True,'id':body['id']})
   raise AssertionError(action)
  except Exception as e:
   if 'Target page, context or browser has been closed'not in str(e):x['errors'].append(str(e))
   try:await route.abort()
   except Exception:pass
 await c.route(h.API+'/**',api)
 if theme:await page.evaluate('(v)=>localStorage.setItem("seminario.portal.theme",v)',theme);await page.reload()
 await p.open_record(page,role)
 return c,page,state,data,x
async def open_files(page):await page.get_by_role('tab',name='Archivos',exact=True).click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Archivos actualizados')
async def choose(page,name='Boleta.pdf',kind='bautismo',content=PDF,count=1):
 await page.locator('#personalFileKind').select_option(kind)
 await page.locator('#personalFileInput').set_input_files([{'name':name if count==1 else str(i)+name,'mimeType':'application/pdf','buffer':content}for i in range(count)])
async def done(c,state,data,x,label):
 global checks
 assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors'];assert not x['errors'],x['errors'];checks+=1;print('PASS '+label,flush=True);await c.close()
async def main():
 async with async_playwright()as pw:
  browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  for role in ['student','control_escolar']:
   c,page,state,data,x=await fixture(browser,role);assert not x['calls'];await open_files(page);await expect(page.locator('#personalSave')).to_be_hidden()
   await expect(page.locator('#personalFilesList')).to_contain_text('Formación previa');await expect(page.locator('#personalFilesList')).to_contain_text('Seguro médico')
   await choose(page,kind='preparatoria',count=2);await page.locator('#personalFilesUpload').click();await expect(page.locator('#personalFilesStatus')).to_contain_text('2 PDF guardados')
   target=data['row']['student']['id'];assert len(x['items'][target])==2 and all(f['kind']=='preparatoria'and f['state']=='ready'for f in x['items'][target])
   assert all(args['p_student']==target for action,args in x['calls']if action in['list','reserve','complete'])
   async with page.expect_download()as download_info:await page.locator('#personalFilesList').get_by_role('button',name='Descargar',exact=True).first.click()
   download=await download_info.value;assert download.suggested_filename=='0Boleta.pdf'
   assert not [args for name,args in data['calls']if name=='portal_student_record_save']
   await done(c,state,data,x,role+' sube varios PDF al expediente correcto y descarga por API privada sin guardar el formulario')

  c,page,state,data,x=await fixture(browser,'control_escolar',with_file=True);await open_files(page)
  previous=data['row']['student']['id'];other='20000000-0000-4000-8000-000000000002';data['row']['student'].update(id=other,full_name='Segundo alumno ficticio')
  await page.evaluate('(id)=>window.PortalPersonalRecord.requestStudent(id)',other);await expect(page.locator('#personal-full_name')).to_have_value('Segundo alumno ficticio');await open_files(page)
  await expect(page.locator('#personalFilesList').get_by_role('button',name='Descargar',exact=True)).to_have_count(0)
  assert x['items'][previous]and x['calls'][-1][1]['p_student']==other;await done(c,state,data,x,'Control cambia de expediente sin conservar documentos del alumno anterior')

  c,page,state,data,x=await fixture(browser,with_file=True);await open_files(page)
  page.once('dialog',lambda d:d.dismiss());await page.get_by_role('button',name='Quitar archivo',exact=True).click();assert not any(a=='remove'for a,_ in x['calls'])
  page.once('dialog',lambda d:d.accept());await page.get_by_role('button',name='Quitar archivo',exact=True).click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Archivo retirado');assert not x['objects'];await done(c,state,data,x,'Quitar exige confirmar y limpia Storage antes de liberar el registro')

  for name,content,text in [('x.docx',PDF,'únicamente PDF'),('x.pdf',b'No es un PDF','cabecera PDF'),('grande.pdf',b'x'*(5242881),'únicamente PDF')]:
   c,page,state,data,x=await fixture(browser);await open_files(page);await choose(page,name=name,content=content);await page.locator('#personalFilesUpload').click();await expect(page.locator('#personalFilesStatus')).to_contain_text(text);assert not any(a=='reserve'for a,_ in x['calls']);await done(c,state,data,x,'Archivo inválido se rechaza antes de subir: '+name)

  c,page,state,data,x=await fixture(browser);target=data['row']['student']['id'];x['items'][target]=[row(target,n)for n in range(1,10)];await open_files(page);await choose(page,count=2);await page.locator('#personalFilesUpload').click();await expect(page.locator('#personalFilesStatus')).to_contain_text('10 PDF en total');assert not any(a=='reserve'for a,_ in x['calls'])
  x['items'][target].append(row(target,10));await page.locator('#personalFilesRefresh').click();await expect(page.locator('#personalFileInput')).to_be_disabled();await done(c,state,data,x,'Límite de diez cuenta todos los apartados y bloquea nuevas cargas')

  for fail in ['reserve','upload','complete','upload403']:
   c,page,state,data,x=await fixture(browser);await open_files(page);await choose(page);x['fail']=fail;await page.locator('#personalFilesUpload').click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Actualizar archivos');await expect(page.locator('#personalFilesUpload')).to_be_disabled()
   assert len([a for a,_ in x['calls']if a=='reserve'])==1;await page.locator('#personalFilesRefresh').click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Archivos actualizados');await expect(page.locator('#personalRecordSection')).to_be_visible()
   if fail=='complete':await expect(page.locator('#personalFilesList').get_by_role('button',name='Descargar',exact=True)).to_have_count(1)
   else:
    page.once('dialog',lambda d:d.accept());await page.get_by_role('button',name='Limpiar carga incompleta',exact=True).click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Archivo retirado')
   await done(c,state,data,x,'Respuesta '+fail+' incierta se revisa/limpia sin reenvío automático ni duplicados')

  c,page,state,data,x=await fixture(browser,with_file=True);await open_files(page);x['fail']='delete';page.once('dialog',lambda d:d.accept());await page.get_by_role('button',name='Quitar archivo',exact=True).click();await expect(page.locator('#personalFilesStatus')).to_contain_text('No se pudo confirmar la eliminación');await page.locator('#personalFilesRefresh').click();page.once('dialog',lambda d:d.accept());await page.get_by_role('button',name='Completar eliminación',exact=True).click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Archivo retirado');await done(c,state,data,x,'Eliminación interrumpida conserva estado recuperable y libera el lugar al terminar')

  c,page,state,data,x=await fixture(browser);await page.locator('#personal-full_name').fill('Borrador sin guardar');await open_files(page);await choose(page);await page.locator('#personalFilesUpload').click();await expect(page.locator('#personalFilesStatus')).to_contain_text('1 PDF guardados');await page.get_by_role('tab',name='Identificación',exact=True).click();await expect(page.locator('#personal-full_name')).to_have_value('Borrador sin guardar');await expect(page.locator('#personalDirty')).to_have_text('Cambios sin guardar');await done(c,state,data,x,'Subir PDF no descarta ni guarda el borrador de datos personales')

  c,page,state,data,x=await fixture(browser);await open_files(page);await choose(page);x['upload_gate']=asyncio.Event();await page.locator('#personalFilesUpload').click();await x['upload_started'].wait();await page.evaluate('window.PortalPersonalRecord.clear(true)');x['upload_gate'].set();await expect(page.locator('#personalRecordSection')).to_be_hidden();await page.wait_for_timeout(150);assert not any(a=='complete'for a,_ in x['calls']);await done(c,state,data,x,'Respuesta tardía tras cerrar sesión no registra ni muestra archivos')

  c,page,state,data,x=await fixture(browser);x['list_status']=404;await page.get_by_role('tab',name='Archivos',exact=True).click();await expect(page.locator('#personalFilesStatus')).to_contain_text('Falta instalar');await page.get_by_role('tab',name='Contacto',exact=True).click();await expect(page.locator('#personal-phone')).to_be_visible();await done(c,state,data,x,'SQL pendiente muestra aviso y conserva las otras secciones del perfil')

  c,page,state,data,x=await fixture(browser);x['list_status']=403;await page.get_by_role('tab',name='Archivos',exact=True).click();await expect(page).to_have_url(re.compile(r'/portal/index.html\?estado=sin_acceso$'));await expect(page.locator('#personalFilesList')).to_have_count(0);await done(c,state,data,x,'Acceso revocado borra la lista y comprueba la sesión')

  for theme in ['light','dark','oled']:
   c,page,state,data,x=await fixture(browser,mobile=True,with_file=True,theme=theme);target=data['row']['student']['id'];x['items'][target][0]['name']='<img src=x onerror=alert(1)>.pdf';await open_files(page);await expect(page.locator('#personalFilesList img')).to_have_count(0);await expect(page.locator('#personalFilesList')).to_contain_text('<img src=x onerror=alert(1)>.pdf');assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');await page.screenshot(path=str(h.ARTIFACTS/('archivos-personales-'+theme+'-movil.png')),full_page=True,animations='disabled');await done(c,state,data,x,'Móvil '+theme+': archivos legibles sin desbordamiento ni HTML inyectado')
  await browser.close()
 print('PASS '+str(checks)+' flujos de archivos personales en navegador.')
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
