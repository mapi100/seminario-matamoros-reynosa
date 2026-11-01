"""Organizador y selector: >50 clases, arrastre, teclado, errores y aislamiento."""
import asyncio,copy,json,shutil
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_workspace as w

PER='da000000-0000-4000-8000-000000000001';PER2='da000000-0000-4000-8000-000000000002'
GROUPS=['CI-1','CI-2','1F-1','1F-2','2F-3','2F-4','3F-5','3F-6','1T-1','1T-2','2T-3','2T-4','3T-5','3T-6','4T-7','4T-8']
checks=0

def sample():
 periods=[{'id':PER,'name':'Ago-Dic 2026','created_at':'2026-01-01T00:00:00Z','starts_on':'2026-08-01','ends_on':'2026-12-31'},{'id':PER2,'name':'Ene-May 2027','created_at':'2026-01-01T00:00:00Z','starts_on':'2027-01-01','ends_on':'2027-05-31'}]
 subjects=[{'id':f'db000000-0000-4000-8000-{i:012d}','code':f'TEST-{i:03d}','created_at':'2026-01-01T00:00:00Z','name':f'Materia ficticia {i:03d}'} for i in range(1,146)]
 classes=[{'id':f'dc000000-0000-4000-8000-{i:012d}','subject_id':s['id'],'period_id':PER,'period_name':periods[0]['name'],'active':True,'name':s['name'],'subject_name':s['name'],'code':s['code'],'group_code':GROUPS[(i-1)%16],'revision':1,'students':0,'professors':0,'starts_on':periods[0]['starts_on'],'ends_on':periods[0]['ends_on']} for i,s in enumerate(subjects[:134],1)]
 return {'periods':periods,'subjects':subjects,'classes':classes,'status':200,'write_status':200,'writes':[],'reads':0,'gate':None,'started':asyncio.Event()}

async def fixture(browser,mobile=False):
 c,page,state,admin=await w.fixture(browser,mobile=mobile);data=sample();admin['classes']=data['classes'];state['catalog_periods']=data['periods'];state['catalog_subjects']=data['subjects']
 async def api(route):
  path=urlparse(route.request.url).path
  if path.endswith('portal_course_board_read'):
   data['reads']+=1;data['started'].set()
   if data['gate']:await data['gate'].wait()
   if data['status']!=200:return await route.fulfill(status=data['status'],content_type='application/json',body=json.dumps({'code':'PGRST202' if data['status']==404 else 'XX000','message':'Fixture'}))
   per=route.request.post_data_json['p_period'] or PER
   return await route.fulfill(status=200,content_type='application/json',body=json.dumps({'periods':data['periods'],'period_id':per,'subjects':data['subjects'],'classes':[x for x in data['classes'] if x['period_id']==per]}))
  if path.endswith('portal_course_board_write'):
   args=route.request.post_data_json;data['writes'].append(args)
   if data['write_status']!=200:return await route.fulfill(status=data['write_status'],content_type='application/json',body=json.dumps({'code':'PT409' if data['write_status']==409 else 'XX000','message':'Otra persona cambió esta clase.'}))
   row=next((x for x in data['classes'] if x['id']==args['p_course']),None)
   if row:row.update(group_code=args['p_group'],revision=row['revision']+1)
   else:
    subject=next(s for s in data['subjects'] if s['id']==args['p_subject']);row={**subject,'id':'dc000000-0000-4000-8000-000000009999','subject_id':subject['id'],'period_id':args['p_period'],'period_name':'Ago-Dic 2026','active':True,'group_code':args['p_group'],'revision':1};data['classes'].append(row)
   return await route.fulfill(status=200,content_type='application/json',body=json.dumps({'saved':True,'id':row['id'],'revision':row['revision'],'created':args['p_course'] is None}))
  if path.endswith('portal_course_groups_read'):
   items=[{'course_id':x['id'],'code':x['code'],'period_name':x['period_name'],'group_code':x['group_code'],'revision':x['revision']} for x in data['classes']]
   return await route.fulfill(status=200,content_type='application/json',body=json.dumps({'items':items}))
  await route.fallback()
 await c.route(h.API+'/**',api)
 await page.evaluate('PortalCourseGroups.reload()')
 return c,page,state,admin,data

async def done(c,state,label):
 global checks
 assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];checks+=1;print('PASS '+label,flush=True);await c.close()

async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  c,page,state,admin,data=await fixture(browser)
  await w.nav(page,'inscripciones');await page.locator('#managementCreate').click()
  await expect(page.locator('#admin-class_id')).to_be_enabled();await expect(page.locator('#admin-class_id option')).to_have_count(135)
  await page.locator('#classPickerStage').select_option('F');await expect(page.locator('#admin-class_id optgroup')).to_have_count(6)
  await page.locator('#classPickerCourse').select_option('1F-1');await expect(page.locator('#admin-class_id optgroup')).to_have_count(1)
  await page.locator('#classPickerSearch').fill('003');await expect(page.locator('#admin-class_id option')).to_have_count(2)
  chosen=data['classes'][2]['id'];await page.locator('#admin-class_id').select_option(chosen);await w.select_ready(page,'person_id',w.A);await page.locator('#managementSave').click()
  await expect(page.locator('#managementDialog')).not_to_be_visible();write=next(x[1] for x in admin['calls'] if x[0]=='write');assert write['p_data']['class_id']==chosen and set(write['p_data'])=={'class_id','person_id'}
  await done(c,state,'134 clases, filtros por etapa/curso/búsqueda y envío sin filtros auxiliares')

  c,page,state,admin,data=await fixture(browser);data['status']=503
  await w.nav(page,'inscripciones');await page.locator('#managementCreate').click();await expect(page.get_by_role('button',name='Reintentar lista')).to_be_visible();await w.select_ready(page,'person_id',w.A)
  data['status']=200;await page.get_by_role('button',name='Reintentar lista').click();await expect(page.locator('#admin-class_id')).to_be_enabled();await expect(page.locator('#admin-person_id')).to_have_value(w.A)
  await page.locator('#classPickerPeriod').select_option(PER2);await expect(page.locator('.course-picker .lookup-status')).to_contain_text('No hay clases')
  await done(c,state,'Fallo de lectura recuperable sin perder alumno y cambio de periodo sin clases')

  c,page,state,admin,data=await fixture(browser);data['status']=404
  await w.nav(page,'inscripciones');await page.locator('#managementCreate').click();await expect(page.locator('#admin-class_id')).to_be_enabled();await expect(page.locator('#admin-class_id option')).to_have_count(135)
  calls=[x[1] for x in admin['calls'] if x[0]=='read' and x[1]['p_resource']=='active_classes'];assert [x['p_offset'] for x in calls]==[0,100]
  await done(c,state,'Compatibilidad sin RPC nueva recorre dos páginas de 100 y 34')

  for mobile in [False,True]:
   c,page,state,admin,data=await fixture(browser,mobile)
   await w.nav(page,'catalogos-academicos');await expect(page.locator('#organizerSources li')).to_have_count(134)
   await expect(page.locator('[data-group="CI-2"]')).to_contain_text('9 materias')
   await page.locator('[data-group="CI-2"]').click();await expect(page.locator('#organizerListTitle')).to_have_text('Materias de CI-2');await expect(page.locator('#organizerSources li')).to_have_count(9)
   card=page.locator('#organizerSources li').first
   if mobile:
    await card.get_by_role('button',name='Mover',exact=False).click();await page.locator('#organizerMoveGroup').select_option('1F-1');await page.get_by_role('button',name='Guardar cambio',exact=True).click()
   else:await card.drag_to(page.locator('[data-group="1F-1"]'))
   await expect(page.locator('#organizerStatus')).to_contain_text('ahora está en 1F-1');assert data['writes'][-1]['p_revision']==1
   await expect(page.locator('#organizerSources li')).to_have_count(8)
   await page.locator('#organizerAll').click();await page.locator('#organizerLibrary').click();await expect(page.locator('#organizerSources li')).to_have_count(11)
   await page.locator('#organizerSources li').first.get_by_role('button').click();await page.locator('#organizerMoveGroup').select_option('CI-1');await page.get_by_role('button',name='Guardar cambio',exact=True).click();await expect(page.locator('#organizerStatus')).to_contain_text('ahora está en CI-1');assert data['writes'][-1]['p_course'] is None
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   await expect(page.locator('#periodList .period-item')).to_have_count(2)
   await page.locator('#courseOrganizer').screenshot(path=str(h.ARTIFACTS/f'organizador-{mobile}.png'))
   await done(c,state,'Tablero '+('móvil con botones' if mobile else 'escritorio con arrastre')+', bloques, conteos y apertura desde catálogo')

  c,page,state,admin,data=await fixture(browser);await w.nav(page,'catalogos-academicos');await expect(page.locator('#organizerSources li')).to_have_count(134);data['write_status']=409
  await page.locator('#organizerSources li').first.get_by_role('button').click();await page.locator('#organizerMoveGroup').select_option('CI-2');await page.get_by_role('button',name='Guardar cambio',exact=True).click()
  await expect(page.locator('#organizerStatus')).to_contain_text('Actualiza');assert len(data['writes'])==1;await expect(page.locator('#organizerSources li').first.get_by_role('button')).to_be_disabled()
  await page.locator('#organizerRefresh').click();await expect(page.locator('#organizerSources li').first.get_by_role('button')).to_be_enabled();assert len(data['writes'])==1
  await done(c,state,'Conflicto no se reenvía y actualizar recupera el estado')

  c,page,state,admin,data=await fixture(browser);data['gate']=asyncio.Event()
  await w.nav(page,'catalogos-academicos');await data['started'].wait();await page.evaluate("location.hash='inicio'");data['gate'].set();await expect(page.locator('#courseOrganizer')).to_be_hidden();await expect(page.locator('#organizerSources li')).to_have_count(0)
  await done(c,state,'Respuesta tardía al navegar no repuebla el tablero')
  await browser.close()
 print('PASS '+str(checks)+' escenarios del organizador y selector.')
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
