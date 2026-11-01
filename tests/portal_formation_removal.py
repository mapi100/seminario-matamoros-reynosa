"""Quitar del bloque: revisión y CONFIRMAR, API ficticia; sin cuentas reales."""
import asyncio,copy,json,re,shutil
from playwright.async_api import async_playwright,expect
import portal_formation_groups as g
h=g.h
P26=g.f.PERIOD;P27=g.f.P2
checks=0
async def fixture(browser,mobile=False,theme=None):
 c,page,state,initial,base=await g.fixture(browser,mobile=mobile,theme=theme)
 data={P26:copy.deepcopy(initial),P27:copy.deepcopy(initial)};data[P27]['period_id']=P27;data[P27]['token']='c'*32
 control={'writes':[],'status':200,'gate':None,'started':asyncio.Event()}
 async def route_api(route):
  req=route.request;args=req.post_data_json
  async def reply(status,value):return await route.fulfill(status=status,content_type='application/json',body=json.dumps(value))
  if req.url.endswith('portal_formation_read'):
   if args['p_resource']=='settings':return await reply(200,{'stages':g.f.STAGES,'periods':[{'id':P26,'name':'AGO-DIC 2026'},{'id':P27,'name':'ENE-MAY 2027'}]})
   return await route.fallback()
  if req.url.endswith('portal_formation_group_read'):return await reply(200,data[args['p_period']])
  if not req.url.endswith('portal_formation_group_remove'):return await route.fallback()
  control['writes'].append(copy.deepcopy(args));control['started'].set()
  if control['gate']:await control['gate'].wait()
  if control['status']!=200:
   if control['status']==403:state['profile']['active']=False
   return await reply(control['status'],{'code':{409:'PT409',403:'42501',404:'PGRST202'}.get(control['status'],'XX000'),'message':'El grupo o sus materias cambiaron. Cierra y actualiza.'})
  current=data[args['p_period']]
  if args['p_kind']=='students':
   for row in current['students']:
    if row['id'] in args['p_ids']:row.update(stage_code=None,semester=None,revision=0)
  else:
   current['classes']=[r for r in current['classes'] if r['id'] not in args['p_ids']]
   current['enrollments']=[r for r in current['enrollments'] if r['class_id'] not in args['p_ids']]
  current['token']='d'*32
  return await reply(200,{'saved':True,'kind':args['p_kind'],'removed':len(args['p_ids']),'period_id':args['p_period'],'group_code':'CI-1'})
 await c.route(h.API+'/**',route_api)
 await page.locator('#formationRefresh').click();await expect(page.locator('#formationStages [data-group]')).to_have_count(16)
 await page.locator('#formationPeriod').select_option(P27);await expect(page.locator('#formationStages [data-group="CI-1"]')).to_contain_text('10 seminaristas')
 await g.select_group(page)
 return c,page,state,data,control
async def open_remove(page,kind='students'):
 await page.get_by_role('button',name='Quitar '+('seminaristas' if kind=='students' else 'materias'),exact=True).click()
 await expect(page.locator('.formation-group-remove')).to_be_visible()
async def select_and_review(page):
 await page.get_by_role('button',name='Seleccionar resultados',exact=True).click();await page.locator('#formationRemoveNext').click()
async def done(c,state,label):
 global checks
 assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];checks+=1;print('PASS '+label,flush=True);await c.close()
async def main():
 async with async_playwright()as p:
  browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  c,page,state,data,ctrl=await fixture(browser);old=copy.deepcopy(data[P26]);await open_remove(page)
  await expect(page.locator('#formationRemoveList input')).to_have_count(10);await expect(page.locator('#formationRemoveNext')).to_be_disabled()
  await select_and_review(page);await expect(page.locator('#formationRemoveReview')).to_contain_text('ENE-MAY 2027 · CI-1 · Quitar 10 seminaristas')
  await expect(page.locator('#formationRemoveConfirm')).to_be_disabled();await page.locator('#formationRemoveConfirmation').fill('SI');await expect(page.locator('#formationRemoveConfirm')).to_be_disabled();assert not ctrl['writes']
  await page.locator('#formationRemoveConfirmation').fill('CONFIRMAR');await expect(page.locator('#formationRemoveConfirm')).to_be_enabled()
  box=await page.locator('#formationRemoveConfirmation').bounding_box();bar=await page.locator('.formation-group-remove .dialog-actions').bounding_box();assert box['y']+box['height']<=bar['y']+1
  await page.screenshot(path=str(h.ARTIFACTS/'quitar-seminaristas-confirmacion.png'),full_page=False,animations='disabled')
  await page.locator('#formationRemoveConfirm').click();await expect(page.locator('.formation-group-remove')).to_have_count(0);await expect(page.locator('#formationGroupContent')).to_contain_text('0 seminaristas')
  assert len(ctrl['writes'])==1 and ctrl['writes'][0]['p_period']==P27 and len(ctrl['writes'][0]['p_ids'])==10 and data[P26]==old
  await page.locator('#formationPeriod').select_option(P26);await expect(page.locator('#formationGroupContent')).to_contain_text('10 seminaristas')
  await done(c,state,'Quitar diez de ENE-MAY requiere CONFIRMAR y conserva los diez de AGO-DIC')

  c,page,state,data,ctrl=await fixture(browser);await open_remove(page);await page.locator('#formationRemoveList input').first.check();await page.locator('#formationRemoveSearch').fill('09')
  await expect(page.locator('#formationRemoveCount')).to_contain_text('1 seleccionados fuera del filtro');await page.locator('#formationRemoveList input').check();await page.locator('#formationRemoveNext').click()
  await expect(page.locator('#formationRemoveReview')).to_contain_text('Quitar 2 seminaristas');await page.locator('#formationRemoveConfirmation').fill('CONFIRMAR');await page.get_by_role('button',name='Volver a la selección',exact=True).click()
  await page.locator('#formationRemoveNext').click();await expect(page.locator('#formationRemoveConfirmation')).to_have_value('');await expect(page.locator('#formationRemoveConfirm')).to_be_disabled()
  await page.locator('#formationRemoveCancel').click();assert not ctrl['writes'];await done(c,state,'Selección múltiple persiste al buscar; volver limpia confirmación y cancelar no escribe')

  c,page,state,data,ctrl=await fixture(browser);before=copy.deepcopy(data[P27]['students']);await page.evaluate('window.__groupReloads=0;const original=window.PortalCourseGroups;window.PortalCourseGroups={...original,reload(){window.__groupReloads++;return original.reload();}}');await open_remove(page,'classes');await select_and_review(page)
  await expect(page.locator('#formationRemoveReview')).to_contain_text('Quitar 3 materias');await expect(page.locator('.formation-group-remove')).to_contain_text('Las clases, profesores, tareas, inscripciones y calificaciones se conservan')
  await page.locator('#formationRemoveConfirmation').fill('CONFIRMAR');await page.locator('#formationRemoveConfirm').click();await expect(page.locator('.formation-group-remove')).to_have_count(0)
  await expect(page.locator('#formationGroupContent')).to_contain_text('0 materias activas');assert data[P27]['students']==before and ctrl['writes'][0]['p_kind']=='classes';assert await page.evaluate('window.__groupReloads')==1
  await expect(page.get_by_role('button',name='Quitar materias',exact=True)).to_be_disabled();await done(c,state,'Quitar materias deja vacío el bloque y conserva seminaristas')

  for status in [409,500,404]:
   c,page,state,data,ctrl=await fixture(browser);await open_remove(page);await select_and_review(page);await page.locator('#formationRemoveConfirmation').fill('CONFIRMAR');ctrl['status']=status
   await page.locator('#formationRemoveConfirm').click();await expect(page.locator('#formationRemoveStatus')).to_contain_text('cambiaron' if status==409 else 'No se pudo confirmar' if status==500 else 'Falta instalar')
   await expect(page.locator('#formationRemoveConfirm')).to_be_disabled();assert len(ctrl['writes'])==1
   if status==409:await page.keyboard.press('Escape')
   else:await page.locator('#formationRemoveCancel').click()
   await expect(page.locator('.formation-group-remove')).to_have_count(0);await done(c,state,'Error '+str(status)+' no reenvía una retirada ni conserva la confirmación anterior')

  c,page,state,data,ctrl=await fixture(browser);await open_remove(page);await select_and_review(page);await page.locator('#formationRemoveConfirmation').fill('CONFIRMAR');ctrl['gate']=asyncio.Event();await page.locator('#formationRemoveConfirm').click();await ctrl['started'].wait()
  await expect(page.locator('#formationRemoveCancel')).to_be_disabled();await page.evaluate('location.hash="inicio"');ctrl['gate'].set();await expect(page.locator('.formation-group-remove')).to_have_count(0);await expect(page.locator('#formationGroupContent')).to_be_empty()
  await done(c,state,'Salida durante respuesta tardía descarta el diálogo y no repuebla la sección')

  c,page,state,data,ctrl=await fixture(browser);await open_remove(page);await select_and_review(page);await page.locator('#formationRemoveConfirmation').fill('CONFIRMAR');ctrl['status']=403
  await page.locator('#formationRemoveConfirm').click();await expect(page).to_have_url(re.compile(r'/portal/index.html\?estado=sin_acceso$'));await expect(page.locator('.formation-group-remove')).to_have_count(0)
  await done(c,state,'Revocar Control Escolar retira el diálogo y los datos privados')

  for theme in ['light','dark','oled']:
   c,page,state,data,ctrl=await fixture(browser,mobile=True,theme=theme);data[P27]['students'][0]['full_name']='<img src=x onerror=alert(1)>'
   await page.locator('#formationRefresh').click();await open_remove(page);await expect(page.locator('#formationRemoveList')).to_contain_text('<img src=x onerror=alert(1)>');await expect(page.locator('#formationRemoveList img')).to_have_count(0)
   await select_and_review(page);await expect(page.locator('#formationRemoveConfirmation')).to_be_visible();box=await page.locator('#formationRemoveConfirmation').bounding_box();bar=await page.locator('.formation-group-remove .dialog-actions').bounding_box();assert box['y']+box['height']<=bar['y']+1;assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   await page.screenshot(path=str(h.ARTIFACTS/('quitar-'+theme+'-movil.png')),full_page=False,animations='disabled')
   await page.keyboard.press('Escape');assert not ctrl['writes'];await done(c,state,'Móvil '+theme+': confirmación legible, texto seguro y Escape sin escritura')
  await browser.close()
 print('PASS '+str(checks)+' flujos de retirada de grupos en navegador.')
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
