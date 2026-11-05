"""Exportación PDF/ZIP real en navegador; datos ficticios y recursos locales."""
import asyncio,copy,io,json,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
from playwright.async_api import async_playwright
import portal_report_print as p
ROOT=Path(__file__).resolve().parents[1]
async def main():
 with tempfile.TemporaryDirectory() as td:
  folder=Path(td)
  async with async_playwright() as tool:
   browser=await tool.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
   context=await browser.new_context(accept_downloads=True);page=await context.new_page();errors=[];requests=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   async def local(route):
    url=route.request.url;requests.append(url);path=ROOT/url.split('https://seminario.test/',1)[1].split('?',1)[0]
    if path.is_file():await route.fulfill(body=path.read_bytes(),content_type='application/javascript; charset=utf-8')
    elif path.name=='test.html':await route.fulfill(body='<html><head><meta charset="utf-8"><title>Prueba PDF ZIP</title></head><body></body></html>',content_type='text/html')
    else:await route.abort()
   await context.route('**/*',lambda route:route.abort());await context.route('https://seminario.test/**',local)
   await page.goto('https://seminario.test/test.html');await page.add_script_tag(url='https://seminario.test/portal/report-pdf.js')
   assert not any('/jspdf/' in x or 'report-pdf-assets' in x for x in requests)
   docs=[p.issued('CI-1',9),p.issued('4T-7',10,stress=True),p.issued('4T-7',20,stress=True)]
   for n,d in enumerate(docs):d['id']=f'20000000-0000-4000-8000-{n+200:012d}';d['folio']=f'BOL-2026-TEST-{n}';d['snapshot']['student']['full_name']='José Ángel Peña Ñúñez' if n==0 else d['snapshot']['student']['full_name']
   async with page.expect_download() as download:
    await page.evaluate('''async docs=>{
      const files=[];
      for(const d of docs){const bytes=await PortalReportPDF.pdf(d);files.push({name:PortalReportPDF.filename(d),bytes});}
      files.push({name:'LEEME_DEL_LOTE.txt',bytes:new TextEncoder().encode('Lote de prueba · pendientes: ninguna.')});
      const blob=PortalReportPDF.zip(files),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='prueba.zip';document.body.append(a);a.click();a.remove();
    }''',docs)
   file=await download.value;await file.save_as(folder/'prueba.zip')
   assert not errors,errors
   with zipfile.ZipFile(folder/'prueba.zip') as archive:
    assert archive.testzip() is None and len(archive.namelist())==4
    pdfs=[n for n in archive.namelist() if n.endswith('.pdf')]
    assert len(pdfs)==3 and len(set(pdfs))==3
    for name,data in zip(pdfs,docs):
     pdf=folder/name;pdf.write_bytes(archive.read(name));meta=subprocess.run(['pdfinfo',str(pdf)],text=True,capture_output=True,check=True).stdout
     assert re.search(r'Pages:\s+1\b',meta),meta
     text=subprocess.run(['pdftotext','-raw',str(pdf),'-'],text=True,capture_output=True,check=True).stdout
     normal=''.join(text.split())
     for row in data['snapshot']['rows']:assert ''.join(row['name'].split()) in normal,(row['name'],text)
     assert ''.join(data['snapshot']['student']['full_name'].split()) in normal,text
     assert text.count(data['folio'])==1 and 'Emitida' in text and 'Mínima aprobatoria 7.0' in text,(name,text[-700:])
     bbox=subprocess.run(['pdftotext','-bbox',str(pdf),'-'],text=True,capture_output=True,check=True).stdout
     assert 'http' not in text
    print('PASS ZIP abierto y CRC comprobado con zipfile; 3 PDF de una hoja, todos los textos y acentos, pie/folio íntegros')
    print('PASS recursos PDF solo se solicitan al exportar; tamaño ZIP:',(folder/'prueba.zip').stat().st_size)
   await context.close();await browser.close()
if __name__=='__main__':asyncio.run(main())
