"""Captura por categorías en Chromium con SDK real y API simulada."""
import asyncio,copy,json,re,shutil
from playwright.async_api import async_playwright,expect
import portal_learning as l
h=l.h
codes=['tasks','exams','projects','participation'];checks=0
async def fixture(browser,role='professor',mobile=False,theme='light',configured=False):
 c,p,s,d=await l.fixture(browser,role,mobile=mobile)
 await expect(p.locator('#panelContent')).to_be_visible()
 schema={'entry_mode':'categories','categories':[{'code':c,'weight':w,'mode':'equal'} for c,w in zip(codes,[30,50,0,20])],'items':[]}
 summary={'configured':True,'entry_mode':'categories','average':None,'categories':[{'code':c,'weight':w,'average':None} for c,w in zip(codes,[30,50,0,20])],'coverage':0,'ready':False,'reasons':['Pendientes'],'token':'a'*32,'items':[]}
 student={'enrollment_id':l.ENROLLMENT,'name':'Seminarista de prueba','final_score':None,'grades':[],'exemptions':[],'category_grades':[],'summary':copy.deepcopy(summary),'draft_summary':copy.deepcopy(summary)}
 book={'students':[student],'assignments':[],'has_more':False,'revision':1 if configured else 0,'published':schema if configured else None,'draft':schema if configured else None,'errors':[],'entry_mode':'categories' if configured else 'activities'}
 state={'book':book,'writes':[],'status':200,'read_status':200,'gate':None,'started':asyncio.Event()}
 async def api(route):
  req=route.request
  if '/rpc/portal_gradebook_' not in req.url:return await route.fallback()
  headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'POST,OPTIONS','Content-Type':'application/json'}
  async def reply(data,status=200):await route.fulfill(status=status,headers=headers,body=json.dumps(data))
  if req.method=='OPTIONS':return await route.fulfill(status=204,headers=headers)
  args=req.post_data_json
  if req.url.endswith('portal_gradebook_read'):
   state['started'].set()
   if state['gate']:await state['gate'].wait()
   if state['read_status']!=200:return await reply({'code':'42501','message':'Acceso revocado'},state['read_status'])
   if args['p_resource']=='own':return await reply({'assignments':[],'entry_mode':'categories','summary':student['summary'],'final_score':student['final_score']})
   return await reply(book)
  state['writes'].append(copy.deepcopy(args))
  if state['status']!=200:return await reply({'code':'PT409' if state['status']==409 else 'XX000','message':'Fallo simulado'},state['status'])
  payload=args['p_data'];action=args['p_action']
  if action=='category_scheme_publish':book.update(published=payload['schema'],draft=payload['schema'],revision=book['revision']+1,entry_mode='categories')
  elif action=='category_marks_save':
   r=payload['students'][0];grades=[]
   for code,score in r['marks'].items():
    old=next((x for x in student['category_grades'] if x['category']==code),{});grades.append({'category':code,'score':score,'published_score':score if payload['publish'] else old.get('published_score'),'revision':1})
   student['category_grades']=grades
   if payload['publish']:
    average=sum(r['marks'][c['code']]*c['weight']/100 for c in book['published']['categories'] if c['weight']>0)
    student['final_score']=r.get('override') if r.get('override') is not None else average
    student['summary'].update(average=average,ready=True,token='b'*32)
   else:student['summary']['token']='c'*32
  else:raise AssertionError(action)
  return await reply({'saved':True,'id':l.COURSE})
 await c.route(h.API+'/**',api)
 await p.evaluate('(theme)=>{document.documentElement.dataset.theme=theme;document.documentElement.dataset.themeTone=theme==="light"?"light":"dark"}',theme)
 await p.evaluate('(hash)=>location.hash=hash','curso/'+l.COURSE+('/mis-notas' if role=='student' else '/calificaciones'))
 await expect(p.locator('#learningContent')).to_contain_text('Mis calificaciones' if role=='student' else 'Calificaciones por categoría')
 return c,p,s,d,state
async def done(c,s,d,label):
 global checks
 assert not s['errors'],s['errors'];assert not s['route_errors'],s['route_errors'];assert not d['errors'],d['errors'];checks+=1;print('PASS '+label,flush=True);await c.close()
async def fill(p,marks={'tasks':'8','exams':'9','participation':'10'}):
 for code,value in marks.items():await p.locator('.category-table input[data-category="'+code+'"]').fill(value)
async def main():
 async with async_playwright() as pw:
  b=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  for mobile,theme in [(False,'light'),(True,'dark'),(True,'oled')]:
   c,p,s,d,state=await fixture(b,mobile=mobile,theme=theme)
   await p.get_by_role('button',name='Configurar evaluación',exact=True).click()
   await p.get_by_role('spinbutton',name='Porcentaje de Proyectos',exact=True).fill('0');await p.get_by_role('spinbutton',name='Porcentaje de Participación',exact=True).fill('20')
   await expect(p.locator('.weighted-total')).to_have_text('Total: 100 % de 100 %')
   await p.get_by_role('checkbox',name='He revisado los porcentajes y confirmo esta forma de evaluación.').check()
   await p.screenshot(path=str(h.ARTIFACTS/f'categorias-config-{theme}-{mobile}.png'))
   await p.get_by_role('button',name='Guardar porcentajes',exact=True).click()
   await expect(p.locator('.category-table input')).to_have_count(3)
   await expect(p.locator('.category-table')).to_contain_text('No cuenta')
   await fill(p,{'tasks':'8'});await expect(p.locator('.category-calculated')).to_have_text('Pendiente')
   await fill(p);await expect(p.locator('.category-calculated')).to_have_text('8.9')
   await p.get_by_role('button',name='Guardar borrador',exact=True).click();await p.locator('.category-dialog').get_by_role('button',name='Guardar borrador',exact=True).click()
   await expect(p.locator('.category-dialog')).to_have_count(0)
   assert state['writes'][-1]['p_data']['publish'] is False
   await expect(p.locator('.category-calculated')).to_have_text('8.9')
   await p.get_by_role('button',name='Revisar y publicar finales',exact=True).click()
   await p.get_by_role('spinbutton',name='Ajuste final de Seminarista de prueba').fill('9.5')
   await p.get_by_role('textbox',name='Motivo de ajustes o correcciones (mínimo 10 caracteres si corresponde)').fill('Ajuste de cierre autorizado por el profesor')
   await p.get_by_role('checkbox',name=re.compile('He revisado las notas seleccionadas')).check()
   await p.screenshot(path=str(h.ARTIFACTS/f'categorias-revision-{theme}-{mobile}.png'))
   await p.get_by_role('button',name='Publicar finales seleccionadas').click();await expect(p.locator('.category-dialog')).to_have_count(0)
   assert state['writes'][-1]['p_data']['students'][0]['override']==95
   assert state['writes'][-1]['p_data']['students'][0]['marks']=={'tasks':80,'exams':90,'participation':100}
   await expect(p.locator('.category-table')).to_contain_text('9.5')
   await fill(p,{'tasks':'0','exams':'0','participation':'0'});await expect(p.locator('.category-calculated')).to_have_text('0.0')
   await p.locator('#learningRoot').screenshot(path=str(h.ARTIFACTS/f'categorias-tabla-{theme}-{mobile}.png'))
   assert await p.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   await done(c,s,d,f'{theme} móvil={mobile}: porcentajes sin actividades, 0 % excluido, borrador, cálculo inmediato, ajuste y publicación')

  # Los borradores antiguos y una actividad ya creada no obligan a usarlas.
  c,p,s,d,state=await fixture(b)
  state['book']['draft']={'categories':[{'code':c,'weight':w,'mode':'equal'} for c,w in zip(codes,[30,50,20,0])],'items':[]}
  state['book']['assignments']=[{'id':l.ASSIGNMENT,'title':'Actividad anterior','published':True}]
  await p.get_by_role('button',name='Actualizar libro',exact=True).click()
  await expect(p.get_by_role('heading',name='Calificaciones por categoría')).to_be_visible()
  await p.get_by_role('button',name='Configurar evaluación',exact=True).click();await expect(p.locator('.category-dialog')).not_to_contain_text('agrega al menos una actividad')
  await p.keyboard.press('Escape');await done(c,s,d,'Curso con borrador y actividad anterior abre la configuración simple sin exigir actividades')

  c,p,s,d,state=await fixture(b,configured=True);state['status']=409
  await fill(p);await p.get_by_role('button',name='Revisar y publicar finales').click();confirm=p.get_by_role('checkbox',name=re.compile('He revisado las notas seleccionadas'));await confirm.check();await p.get_by_role('button',name='Publicar finales seleccionadas').click()
  await expect(p.locator('.category-dialog .learning-status')).to_contain_text('cambiaron');await confirm.uncheck();await confirm.check();await expect(p.get_by_role('button',name='Publicar finales seleccionadas')).to_be_disabled();assert len(state['writes'])==1
  await p.keyboard.press('Escape');state['gate']=asyncio.Event();state['started'].clear();await p.get_by_role('button',name='Actualizar libro',exact=True).click();await state['started'].wait();await p.evaluate("location.hash='inicio'");state['gate'].set();await expect(p.locator('#learningRoot')).to_be_empty()
  await done(c,s,d,'Conflicto no se reenvía; navegar descarta respuestas tardías')

  c,p,s,d,state=await fixture(b,'student',configured=True);await expect(p.get_by_role('button',name='Configurar evaluación')).to_have_count(0);assert not state['writes'];await done(c,s,d,'Alumno ve sus categorías y final publicada sin controles docentes')
  await b.close()
 print('PASS',checks,'flujos de captura por categorías')
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
