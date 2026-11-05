"""Edición de matrícula desde expediente: API ficticia, sin personas reales."""
import asyncio,copy,json,shutil
from playwright.async_api import async_playwright,expect
import portal_personal_record as p
h=p.h
async def main():
 async with async_playwright()as pw:
  browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  for role in ['student','control_escolar']:
   c,page,state,data=await p.fixture(browser,role);calls=[]
   async def route(r):
    calls.append(r.request.post_data_json);data['row']['school']['student_number']=calls[-1]['p_number']
    result=copy.deepcopy(data['row']);result.update(saved=True,token='c'*32,completion={'total':9,'completed':0,'missing':[]})
    await r.fulfill(status=200,content_type='application/json',body=json.dumps(result))
   await c.route(h.API+'/rest/v1/rpc/portal_student_number_save',route)
   await p.open_record(page,role);await page.get_by_role('tab',name='Datos escolares',exact=True).click()
   if role=='student':await expect(page.get_by_role('button',name='Editar matrícula',exact=True)).to_have_count(0)
   else:
    page.once('dialog',lambda d:d.accept('SEM-FICT-2026'));await page.get_by_role('button',name='Editar matrícula',exact=True).click()
    await expect(page.locator('#personalStatus')).to_contain_text('Matrícula guardada');await expect(page.locator('#personalAccount')).to_contain_text('SEM-FICT-2026');assert calls[0]['p_student']==data['row']['student']['id']
   await page.get_by_role('tab',name='Seguro médico',exact=True).click();await expect(page.locator('#personal-medical_provider')).to_be_visible()
   assert not state['errors']and not state['route_errors']and not data['errors'],(state,data['errors']);await c.close();print('PASS permisos, edición de matrícula y cobertura médica: '+role)
  await browser.close()
if __name__=='__main__':
 h.prepare()
 try:asyncio.run(main())
 finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
