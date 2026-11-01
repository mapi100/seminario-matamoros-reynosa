"""Flujo de grupos en Etapas y semestres: SDK real y API ficticia, sin producción."""
import asyncio,copy,json,shutil,re
from playwright.async_api import async_playwright,expect
import portal_formation as f
h=f.h
S=[f'10000000-0000-4000-8000-{n:012d}' for n in range(600,638)]
C=[f'10000000-0000-4000-8000-{n:012d}' for n in range(650,654)]
checks=0
async def fixture(browser,mobile=False,theme=None):
 c,page,state,formation,kdata=await f.fixture(browser,mobile=mobile)
 data={'period_id':f.PERIOD,'token':'a'*32,'students':[{'id':s,'full_name':f'Seminarista {i:02}','student_number':None,'stage_code':'introductorio' if i<10 else 'filosofia' if i==10 else None,'semester':1 if i<10 else 3 if i==10 else None,'revision':1 if i<11 else 0} for i,s in enumerate(S)],
       'classes':[{'id':cl,'name':f'Materia {i+1}','group_code':'CI-1' if i<3 else 'CI-2','revision':1} for i,cl in enumerate(C)],
       'enrollments':[{'student_id':S[0],'class_id':C[0],'active':True},{'student_id':S[1],'class_id':C[0],'active':False}]}
 control={'calls':[],'writes':[],'status':200,'read_status':200,'gate':None,'started':asyncio.Event()}
 async def route_api(route):
  req=route.request
  if '/rpc/portal_formation_group_' not in req.url:return await route.fallback()
  args=req.post_data_json;control['calls'].append(copy.deepcopy(args))
  async def reply(status,value):return await route.fulfill(status=status,content_type='application/json',body=json.dumps(value))
  if req.url.endswith('portal_formation_group_read'):
   control['started'].set()
   if control['gate']:await control['gate'].wait()
   if control['read_status']==403:state['profile']['active']=False
   if control['read_status']!=200:return await reply(control['read_status'],{'code':'PGRST202','message':'Falta instalar SQL'})
   value=copy.deepcopy(data);value['period_id']=args['p_period']
   if args['p_period']!=f.PERIOD:value['students']=[];value['classes']=[];value['enrollments']=[]
   return await reply(200,value)
  control['writes'].append(copy.deepcopy(args))
  if control['status']!=200:return await reply(control['status'],{'code':'PT409' if control['status']==409 else 'XX000','message':'El grupo o sus materias cambiaron. Cierra y actualiza antes de continuar.'})
  if args['p_action']=='assign':
   selected=[r for r in data['students'] if r['id'] in args['p_students']]
   for r in selected:r.update(stage_code=args['p_stage'],semester=args['p_semester'],revision=r['revision']+1)
   result={'saved':True,'assigned':len(selected),'unchanged':0}
  else:
   result={'saved':True,'enrolled':0,'reactivated':0,'already_enrolled':0,'kept_inactive':0}
   for student in args['p_students']:
    for cl in args['p_classes']:
     r=next((r for r in data['enrollments'] if r['class_id']==cl and r['student_id']==student),None)
     if r and r['active']:result['already_enrolled']+=1
     elif r and not args['p_reactivate']:result['kept_inactive']+=1
     elif r:r['active']=True;result['reactivated']+=1
     else:data['enrollments'].append({'class_id':cl,'student_id':student,'active':True});result['enrolled']+=1
  data['token']='b'*32
  return await reply(200,result)
 await c.route(h.API+'/**',route_api)
 if theme:await page.evaluate('(value)=>localStorage.setItem("seminario.portal.theme",value)',theme);await page.reload()
 await page.evaluate('location.hash="etapas"')
 await expect(page.locator('#formationStages [data-group]')).to_have_count(16)
 return c,page,state,data,control
async def select_group(page,code='CI-1'):await page.locator(f'#formationStages [data-group="{code}"]').click()
async def finish(c,state,label):
 global checks
 assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];checks+=1;print('PASS '+label,flush=True);await c.close()
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  c,page,state,data,ctrl=await fixture(browser);await select_group(page)
  await expect(page.locator('#formationGroupContent')).to_contain_text('10 seminaristas · 3 materias activas')
  await page.screenshot(path=str(h.ARTIFACTS/'grupos-escritorio.png'),full_page=True,animations='disabled')
  await page.get_by_role('button',name='Agregar seminaristas',exact=True).click()
  await expect(page.locator('#formationGroupPeople li')).to_have_count(27)
  await page.get_by_role('button',name='Seleccionar resultados',exact=True).click()
  await expect(page.locator('#formationGroupSelectionCount')).to_contain_text('27 seleccionados')
  await page.locator('#formationGroupFilter').select_option('2F-3')
  await expect(page.locator('#formationGroupSelectionCount')).to_contain_text('27 seleccionados fuera del filtro')
  await page.locator('#formationGroupPeople input').check()
  await page.locator('#formationGroupReview').click()
  await expect(page.locator('.formation-group-dialog')).to_contain_text('1 cambiarán de curso')
  assert not ctrl['writes']
  await page.locator('#formationGroupConfirm').click()
  await expect(page.locator('.formation-group-dialog')).to_have_count(0)
  await expect(page.locator('#formationGroupContent')).to_contain_text('38 seminaristas')
  assert len(ctrl['writes'])==1 and ctrl['writes'][0]['p_action']=='assign' and len(ctrl['writes'][0]['p_students'])==28 and ctrl['writes'][0]['p_classes']==[]
  await finish(c,state,'Asignación múltiple con filtro, selección persistente y revisión explícita del cambio de curso')

  c,page,state,data,ctrl=await fixture(browser);await select_group(page);await page.get_by_role('button',name='Inscribir en materias',exact=True).click()
  await expect(page.locator('#formationGroupPeople input:checked')).to_have_count(10)
  await expect(page.locator('#formationGroupClasses input:checked')).to_have_count(3)
  await page.locator('#formationGroupPeople input').last.uncheck();await page.locator('#formationGroupClasses input').last.uncheck()
  await page.locator('#formationGroupReview').click()
  await expect(page.locator('.formation-group-dialog')).to_contain_text('9 seminaristas × 2 materias')
  await expect(page.locator('.formation-group-dialog')).to_contain_text('16 inscripciones nuevas · 1 ya existentes (se omiten) · 1 bajas que se conservarán')
  await page.locator('#formationGroupConfirm').click();await expect(page.locator('.formation-group-dialog')).to_have_count(0)
  assert len(ctrl['writes'])==1 and len(ctrl['writes'][0]['p_students'])==9 and len(ctrl['writes'][0]['p_classes'])==2 and not ctrl['writes'][0]['p_reactivate']
  assert not next(r for r in data['enrollments'] if r['student_id']==S[1] and r['class_id']==C[0])['active']
  await finish(c,state,'Grupo preseleccionado, excepciones, existentes omitidos y bajas conservadas')

  c,page,state,data,ctrl=await fixture(browser);await select_group(page);await page.get_by_role('button',name='Inscribir en materias',exact=True).click();await page.locator('#formationGroupReactivate').check();await page.locator('#formationGroupReview').click()
  await expect(page.locator('.formation-group-dialog')).to_contain_text('1 bajas que se reactivarán')
  await page.get_by_role('button',name='Volver a la selección',exact=True).click();assert not ctrl['writes']
  await page.locator('#formationGroupReview').click();await page.locator('#formationGroupConfirm').click();await expect(page.locator('.formation-group-dialog')).to_have_count(0)
  assert ctrl['writes'][0]['p_reactivate']
  await finish(c,state,'Reactivación requiere opción explícita y volver a selección no escribe')

  for status in [409,500]:
   c,page,state,data,ctrl=await fixture(browser);await select_group(page);await page.get_by_role('button',name='Inscribir en materias',exact=True).click();await page.locator('#formationGroupReview').click();ctrl['status']=status;await page.locator('#formationGroupConfirm').click()
   await expect(page.locator('.formation-group-dialog [role=status]')).to_contain_text('cambiaron' if status==409 else 'No se pudo confirmar')
   await expect(page.locator('#formationGroupConfirm')).to_be_disabled();assert len(ctrl['writes'])==1
   await page.locator('#formationGroupCancel').click();await expect(page.locator('.formation-group-dialog')).to_have_count(0)
   await finish(c,state,'Conflicto o respuesta incierta '+str(status)+' no reenvía el lote')

  c,page,state,data,ctrl=await fixture(browser);await select_group(page,'CI-2');await expect(page.get_by_role('button',name='Inscribir en materias',exact=True)).to_be_disabled()
  await page.locator('#formationPeriod').select_option(f.P2);await expect(page.locator('#formationGroupContent')).to_contain_text('0 seminaristas')
  assert not ctrl['writes'];assert ctrl['calls'][-1]['p_period']==f.P2
  await finish(c,state,'Cambiar de periodo muestra sus datos propios y cursos vacíos no se inscriben')

  c,page,state,data,ctrl=await fixture(browser);ctrl['read_status']=404;await page.locator('#formationRefresh').click()
  await expect(page.locator('#formationGroupStatus')).to_contain_text('Falta instalar el SQL');await expect(page.locator('#formationStudents li')).to_have_count(1)
  await finish(c,state,'SQL pendiente informa sin impedir consulta individual')

  c,page,state,data,ctrl=await fixture(browser);ctrl['gate']=asyncio.Event();ctrl['started'].clear();await page.locator('#formationRefresh').click();await ctrl['started'].wait()
  await page.evaluate('location.hash="inicio"');ctrl['gate'].set();await expect(page.locator('#formationGroupContent')).to_be_empty();await expect(page.locator('#formationSection')).to_be_hidden()
  assert not ctrl['writes'];await finish(c,state,'Navegar fuera descarta respuestas tardías y datos de la sección')

  c,page,state,data,ctrl=await fixture(browser);await select_group(page);await page.get_by_role('button',name='Agregar seminaristas',exact=True).click()
  await page.locator('#formationGroupFilter').select_option('CI-1');await expect(page.locator('#formationGroupPeople input:disabled')).to_have_count(10)
  await expect(page.locator('#formationGroupReview')).to_be_disabled();await page.keyboard.press('Escape');await expect(page.locator('.formation-group-dialog')).to_have_count(0)
  ctrl['read_status']=403;await page.locator('#formationRefresh').click();await expect(page).to_have_url(re.compile(r'/portal/index.html\?estado=sin_acceso$'));await expect(page.locator('#formationGroupContent')).to_have_count(0)
  assert not ctrl['writes'];await finish(c,state,'Miembros actuales se omiten, Escape cancela y acceso revocado elimina los datos')

  for theme in ['light','dark','oled']:
   c,page,state,data,ctrl=await fixture(browser,mobile=True,theme=theme);await select_group(page)
   data['students'][0]['full_name']='<img src=x onerror=alert(1)>';await page.locator('#formationRefresh').click();await select_group(page)
   await page.get_by_role('button',name='Inscribir en materias',exact=True).click();await expect(page.locator('.formation-group-dialog')).to_contain_text('<img src=x onerror=alert(1)>');assert await page.locator('.formation-group-dialog img').count()==0
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   color=await page.locator('#formationStages [data-group="CI-1"]').evaluate('(el)=>getComputedStyle(el).color')
   assert color!='rgb(255, 255, 255)' or theme!='light',color
   await page.locator('#formationGroupReview').click()
   await page.screenshot(path=str(h.ARTIFACTS/('grupos-'+theme+'-movil.png')),full_page=True,animations='disabled')
   await page.locator('#formationGroupCancel').click()
   await finish(c,state,'Móvil '+theme+': sin desbordamiento, nombres como texto y cancelar sin escribir')
  await browser.close()
 print('PASS '+str(checks)+' flujos de grupos formativos en navegador.')
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
