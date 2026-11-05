"""Flujos de Control Escolar con SDK real, API simulada y ZIP/PDF locales."""
import asyncio,copy,json,shutil,subprocess,zipfile
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_learning as l
import portal_course_organizer as o
import portal_report_print as p

E2='a5000000-0000-4000-8000-000000000002'
S2='a5100000-0000-4000-8000-000000000002';S3='a5100000-0000-4000-8000-000000000003'
checks=0
async def fixture(browser,mobile=False):
 c,page,state,learning=await l.fixture(browser,'control_escolar',mobile=mobile)
 await expect(page.locator('#panelContent')).to_be_visible()
 board=o.sample();board['classes'][0]['id']=l.COURSE
 school={'course':{'id':l.COURSE,'name':'Materia ficticia 001','period_name':'Ago-Dic 2026'},'students':[
  {'enrollment_id':l.ENROLLMENT,'student_id':h.UID,'name':'José Ángel de prueba','student_number':'TEST-01','published_score':None,'draft_score':None,'revision':0},
  {'enrollment_id':E2,'student_id':S2,'name':'Ana María de prueba','student_number':'TEST-02','published_score':85,'draft_score':85,'revision':1}],'token':'a'*32}
 docs=[]
 for i,student in enumerate(school['students']):
  doc=p.issued();doc.update(id=f'20000000-0000-4000-8000-{i+400:012d}',student_id=student['student_id'],folio='BOL-TEST-'+str(i))
  doc['snapshot']['student'].update(id=student['student_id'],full_name=student['name'],student_number=student['student_number'])
  doc['snapshot']['period']['id']=o.PER;docs.append(doc)
 plan={'period_id':o.PER,'period_name':'Ago-Dic 2026','stage':'introductorio','semester':1,'group_code':'CI-1','token':'b'*32,'items':[
  {'student_id':d['student_id'],'name':d['snapshot']['student']['full_name'],'action':'issue','preview':d['snapshot']} for d in docs]+[
  {'student_id':S3,'name':'Pendiente de prueba','action':'pending','preview':{'reasons':['Falta una calificación final']}}]}
 extra={'school':school,'plan':plan,'docs':docs,'calls':[],'writes':[],'issues':[],'school_status':200,'write_status':200,'first_lost':False,'revoke_final':False,'gate':None,'started':asyncio.Event()}
 async def api(route):
  path=urlparse(route.request.url).path;name=path.rsplit('/',1)[-1]
  if name not in ['portal_course_board_read','portal_school_finals_read','portal_school_finals_save','portal_report_group_read','portal_report_group_issue']:return await route.fallback()
  headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'POST,OPTIONS','Content-Type':'application/json'}
  async def reply(data,status=200):await route.fulfill(status=status,headers=headers,body=json.dumps(data))
  if route.request.method=='OPTIONS':return await route.fulfill(status=204,headers=headers)
  args=route.request.post_data_json;extra['calls'].append((name,copy.deepcopy(args)))
  if name=='portal_course_board_read':
   period=args['p_period'] or o.PER
   return await reply({'periods':board['periods'],'subjects':board['subjects'],'period_id':period,'classes':[x for x in board['classes'] if x['period_id']==period]})
  if name=='portal_school_finals_read':
   extra['started'].set()
   if extra['gate']:await extra['gate'].wait()
   if extra['school_status']!=200:return await reply({'code':'42501','message':'No autorizado'},extra['school_status'])
   return await reply(extra['school'])
  if name=='portal_school_finals_save':
   extra['writes'].append(copy.deepcopy(args))
   if extra['write_status']!=200:return await reply({'code':'PT409','message':'Las notas cambiaron. Actualiza.'},extra['write_status'])
   for change in args['p_items']:
    student=next(x for x in school['students'] if x['enrollment_id']==change['enrollment_id']);student.update(published_score=change['score'],draft_score=change['score'])
   school['token']='c'*32;return await reply({**school,'saved':True})
  if name=='portal_report_group_read':return await reply(plan)
  extra['issues'].append(copy.deepcopy(args))
  if extra['first_lost'] and len(extra['issues'])==1:return await reply({'code':'XX000','message':'Respuesta perdida'},500)
  if extra['revoke_final'] and len(extra['issues'])>=2:
   state['profile']['role']='professor';return await reply({'code':'42501','message':'Acceso revocado'},403)
  ready=[x for x in plan['items'] if x['action']!='pending']
  return await reply({'saved':True,'batch_id':args['p_request'],'period_id':o.PER,'period_name':plan['period_name'],'group_code':'CI-1','documents':docs[:len(ready)],'total':len(plan['items']),'newly_issued':sum(x['action']=='issue' for x in ready),'reused':sum(x['action']=='reuse' for x in ready),'pending':[{'name':x['name'],'reasons':x['preview']['reasons']} for x in plan['items'] if x['action']=='pending']})
 await c.route(h.API+'/**',api)
 return c,page,state,learning,board,extra
async def courses(page):
 await page.evaluate("location.hash='materias-asignadas'")
 await expect(page.locator('#classDirectoryGroups [data-course]')).to_have_count(16)
async def block(page):
 await courses(page);await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
async def finals(page):
 await block(page);await page.locator('#classDirectoryList [href="#curso/'+l.COURSE+'/finales"]').click()
 await expect(page.locator('#learningContent input[type=number]')).to_have_count(2)
async def review(page):
 await page.get_by_role('button',name='Revisar y publicar finales').click()
 await expect(page.locator('.school-final-dialog')).to_be_visible()
 await expect(page.get_by_role('button',name='Publicar 2 finales')).to_be_disabled()
 await page.locator('.school-final-dialog input[type=checkbox]').check()
async def done(c,state,data,label):
 global checks
 assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors']
 checks+=1;print('PASS '+label,flush=True);await c.close()
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  for mobile in [False,True]:
   c,page,state,learning,board,extra=await fixture(browser,mobile)
   await page.evaluate("document.documentElement.dataset.theme='oled';document.documentElement.dataset.themeTone='dark'")
   await block(page)
   await expect(page.locator('#classDirectoryTitle')).to_have_text('Mis cursos')
   await expect(page.locator('#classDirectoryManage')).to_be_hidden()
   await expect(page.locator('#teachingSection')).to_be_hidden()
   await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(9)
   assert not any('get_teaching' in url for _,url in state['requests'])
   await page.locator('#classDirectoryAll').click();await expect(page.locator('#classDirectoryList .class-directory-card')).to_have_count(134)
   new=copy.deepcopy(board['classes'][0]);new.update(id='dc000000-0000-4000-8000-000000009991',name='Nueva clase sin asignaciones',group_code='CI-2',period_id=o.PER2)
   board['classes'].append(new)
   await page.locator('#classDirectoryPeriod').select_option(o.PER2);await expect(page.locator('#classDirectoryGroups [data-course="CI-2"]')).to_contain_text('1 clase')
   await page.locator('#classDirectoryGroups [data-course="CI-2"]').click();await expect(page.locator('#classDirectoryList')).to_contain_text(new['name'])
   await page.locator('#classDirectoryPeriod').select_option(o.PER);await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
   await page.locator('#classDirectory').screenshot(path=str(h.ARTIFACTS/f'control-mis-cursos-{mobile}.png'))
   await page.locator('#classDirectoryList [href="#curso/'+l.COURSE+'/finales"]').click();inputs=page.locator('#learningContent input[type=number]');await expect(inputs).to_have_count(2)
   await inputs.nth(0).fill('9.4');await inputs.nth(1).fill('8.7');await review(page)
   await page.screenshot(path=str(h.ARTIFACTS/f'control-confirmar-finales-{mobile}.png'))
   await page.get_by_role('button',name='Publicar 2 finales').click();await expect(page.locator('.school-final-status')).to_contain_text('publicadas')
   assert extra['writes'][0]['p_items']==[{'enrollment_id':l.ENROLLMENT,'score':94},{'enrollment_id':E2,'score':87}]
   await expect(inputs.nth(0)).to_have_value('9.4');await expect(inputs.nth(1)).to_have_value('8.7')
   await inputs.nth(0).fill('1e0');await page.get_by_role('button',name='Revisar y publicar finales').click();await expect(page.locator('.school-final-status')).to_contain_text('un decimal');await inputs.nth(0).fill('9.4')
   await page.get_by_role('button',name='Revisar y publicar finales').click();await expect(page.locator('.school-final-status')).to_contain_text('No hay calificaciones');assert len(extra['writes'])==1
   await page.locator('#learningRoot').screenshot(path=str(h.ARTIFACTS/f'control-finales-{mobile}.png'))
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   assert await page.locator('#learningContent>p').first.evaluate('p=>getComputedStyle(p).color')=='rgb(185, 193, 206)'
   await block(page);await page.locator('#classDirectoryReports').click();await expect(page.locator('#reportBatchDownload')).to_be_disabled()
   await expect(page.locator('.report-batch-dialog')).to_contain_text('2 de 3 boletas')
   await page.screenshot(path=str(h.ARTIFACTS/f'control-zip-{mobile}.png'))
   await page.locator('#reportBatchReviewed').check()
   async with page.expect_download() as pending:await page.locator('#reportBatchDownload').click()
   download=await pending.value;target=h.ARTIFACTS/f'control-{mobile}.zip';await download.save_as(target)
   with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None and len(archive.namelist())==3
    assert 'Pendiente de prueba' in archive.read('LEEME_DEL_LOTE.txt').decode()
    for name in archive.namelist():
     if name.endswith('.pdf'):
      pdf=h.ARTIFACTS/name;pdf.write_bytes(archive.read(name));assert 'Pages:           1' in subprocess.run(['pdfinfo',str(pdf)],capture_output=True,text=True,check=True).stdout
   assert len(extra['issues'])==2 and extra['issues'][0]==extra['issues'][1]
   await done(c,state,learning,('Móvil OLED' if mobile else 'Escritorio OLED')+': 134 clases, futuras sin asignar, finales escala 0–10 y ZIP real de una página con pendientes')

  c,page,state,learning,board,extra=await fixture(browser);extra['write_status']=409
  await finals(page);await page.locator('#learningContent input[type=number]').nth(0).fill('9');await page.get_by_role('button',name='Revisar y publicar finales').click();await page.locator('.school-final-dialog input[type=checkbox]').check();await page.get_by_role('button',name='Publicar 1 finales').click()
  await expect(page.locator('.school-final-dialog .control-message')).to_contain_text('cambiaron')
  await expect(page.get_by_role('button',name='Publicar 1 finales')).to_be_disabled()
  await page.keyboard.press('Escape');await expect(page.locator('#learningContent input[type=number]').nth(0)).to_have_value('')
  assert len(extra['writes'])==1
  extra['gate']=asyncio.Event();extra['started'].clear();await page.get_by_role('button',name='Actualizar notas').click();await extra['started'].wait();await page.evaluate("location.hash='inicio'");extra['gate'].set()
  await expect(page.locator('#learningRoot')).to_be_empty()
  await done(c,state,learning,'Conflicto exige releer y salir descarta notas tardías')

  c,page,state,learning,board,extra=await fixture(browser);extra['first_lost']=True
  for item in extra['plan']['items'][:2]:item['action']='reuse'
  await block(page);await page.locator('#classDirectoryReports').click();await expect(page.locator('#reportBatchReviewed')).to_be_hidden()
  await page.locator('#reportBatchDownload').click();await expect(page.locator('.report-batch-dialog .control-message')).to_contain_text('No se confirmó')
  async with page.expect_download():await page.locator('#reportBatchDownload').click()
  assert len(extra['issues'])==3 and len({x['p_request'] for x in extra['issues']})==1
  await done(c,state,learning,'Copias vigentes sin reemitir; respuesta perdida reintenta exactamente el mismo lote')

  c,page,state,learning,board,extra=await fixture(browser);extra['revoke_final']=True;downloads=[];page.on('download',lambda d:downloads.append(d))
  await block(page);await page.locator('#classDirectoryReports').click();await page.locator('#reportBatchReviewed').check();await page.locator('#reportBatchDownload').click()
  await expect(page.locator('#profileRole')).to_have_text('Profesor');await expect(page.locator('.report-batch-dialog')).to_have_count(0)
  assert not downloads
  await done(c,state,learning,'Revocación de Control Escolar impide descargar un ZIP ya generado')

  for role in ['student','professor']:
   c,page,state,learning=await l.fixture(browser,role,route='curso/'+l.COURSE+'/finales')
   await expect(page.locator('#learningContent')).to_be_visible();await expect(page.locator('a[href$="/finales"]')).to_have_count(0)
   assert not any('/portal_school_finals_' in url for _,url in state['requests'])
   await done(c,state,learning,role+': conserva sus cursos y no solicita captura reservada a Control Escolar')
  await browser.close()
 print(f'PASS {checks} escenarios de Control Escolar')
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
