"""Regresión del borrador de boleta cuando aún no existe su RPC de emisión."""
import asyncio,shutil
from pathlib import Path
from lxml import html
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parents[1]

async def main():
 tree=html.fromstring((ROOT/'portal/panel.html').read_text());node=tree.get_element_by_id('reportCards')
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  page=await browser.new_page();await page.set_content(html.tostring(node,encoding='unicode'))
  await page.evaluate("""() => {
   window.PortalGradeScale={format:n=>(n/10).toFixed(1)};
   window.PortalAuth={getClient:()=>({rpc:()=>({retry(){return this},abortSignal:async()=>({error:{code:'PGRST202'}})})})};
  }""")
  await page.add_script_tag(path=str(ROOT/'portal/report-cards.js'))
  await page.evaluate("""async () => {
   const pid='20000000-0000-4000-8000-000000000030';
   await window.PortalReportCards.mount({student:{id:'20000000-0000-4000-8000-000000000001',full_name:'Alumno ficticio',student_number:'TEST-001'},
    institution:{rector_name:'Rector ficticio',prefect_name:'Prefecto ficticio'},formation_history:[{period_id:pid,period_name:'AGO-DIC 2026',starts_on:'2026-08-01',ends_on:'2026-12-31',stage_code:'introductorio',semester:1}],
    rows:[{period_id:pid,period_name:'AGO-DIC 2026',starts_on:'2026-08-01',ends_on:'2026-12-31',name:'Materia vigente',score:80,enrollment_active:true},
     {period_id:pid,name:'Materia retirada',score:90,enrollment_active:false}]},async()=>{});
  }""")
  await expect(page.locator('#reportPreview tbody tr')).to_have_count(1)
  await expect(page.locator('#reportPreview')).to_contain_text('Materia vigente')
  await expect(page.locator('#reportPreview')).not_to_contain_text('Materia retirada')
  await expect(page.locator('#reportPreview')).to_contain_text('8.0')
  await expect(page.locator('#reportIssue')).to_be_disabled()
  print('PASS borrador excluye bajas, conserva escala y no permite emitir sin servidor')
  await browser.close()
if __name__=='__main__':asyncio.run(main())
