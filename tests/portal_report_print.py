"""PDF real en Chromium: una hoja, pie completo y sin encabezados del navegador.

Datos ficticios, RPC simulada y archivos locales; no accede a Supabase.
Requiere Playwright, Chromium y Poppler. PDFs de prueba en /tmp por defecto.
"""
import argparse,asyncio,copy,json,re,shutil,subprocess
from pathlib import Path
from lxml import html
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/tmp/seminario-report-print-checks')
ID='20000000-0000-4000-8000-000000000001';PERIOD='20000000-0000-4000-8000-000000000030';ISSUE='20000000-0000-4000-8000-000000000099'
SUBJECTS=['Catecismo I','Introducción a la Biblia','Comunicación Integral I','Inglés I','Documentos de Formación Sacerdotal','Historia de la Iglesia (Temas Selectos)','Introducción y Espiritualidad en la Liturgia','Latín I','Formación Humana I','Administración Parroquial Canónica']
COURSES=[('CI-1',9),('1F-1',9),('2F-3',9),('3F-5',10),('1T-1',9),('2T-3',9),('3T-5',9),('4T-7',10),('CI-2',8),('1F-2',8),('2F-4',9),('3F-6',7),('1T-2',9),('2T-4',10),('4T-8',10)]

def issued(code='CI-1',n=9,stress=False):
 stage='introductorio' if code.startswith('CI') else 'filosofia' if 'F' in code else 'teologia'
 semester=int(code.split('-')[1]);spring=semester%2==0
 name='Nombre ficticio para verificar la impresión de la boleta'
 subjects=[SUBJECTS[i%len(SUBJECTS)]+(' · Grupo '+str(i+1) if i>=10 else '') for i in range(n)]
 if stress:
  name=('Nombre completo de prueba para comprobar saltos y acentos Áéíóú Ñ ' * 3)[:160]
  subjects=[('Asignatura '+str(i+1)+' de formación y acompañamiento pastoral, filosofía, teología y humanidades con un nombre largo para comprobar el ajuste automático ' * 2)[:160] for i in range(n)]
 snapshot={'version':1,'scale':10,'decimals':1,'pass_mark':7,'institution':{'name':'SEMINARIO DE MATAMOROS-REYNOSA'},'student':{'id':ID,'full_name':name,'student_number':'TEST-2026-001'},'period':{'id':PERIOD,'name':'ENE-MAY 2027' if spring else 'AGO-DIC 2026','starts_on':'2027-01-01' if spring else '2026-08-01','ends_on':'2027-05-31' if spring else '2026-12-31'},'formation':{'period_id':PERIOD,'stage_code':stage,'semester':semester,'stage_name':{'introductorio':'Curso Introductorio','filosofia':'Filosofía','teologia':'Teología'}[stage],'ecclesial_name':{'introductorio':'Etapa propedéutica','filosofia':'Etapa discipular','teologia':'Etapa configuradora'}[stage]},'cycle':'2026-2027','rector_name':'Rector de prueba','prefect_name':'Prefecto de Estudios de prueba','rows':[{'name':name,'score':round(7+i%4,1)} for i,name in enumerate(subjects)],'ready':True,'reasons':[],'token':'a'*32}
 return {'id':ISSUE,'student_id':ID,'folio':'BOL-2026-PRUEBA','issued_at':'2026-11-05T20:00:00Z','snapshot':snapshot}

async def setup(browser,data,*,mobile=False,deny_print=False):
 context=await browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1100})
 page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 async def files(route):
  rel=route.request.url.split('https://seminario.test/',1)[1].split('?',1)[0];path=ROOT/rel
  if path.is_file():await route.fulfill(body=path.read_bytes(),content_type='image/png' if path.suffix=='.png' else 'text/plain')
  else:await route.abort()
 await context.route('**/*',lambda route:route.abort())
 await context.route('https://seminario.test/**',files)
 tree=html.fromstring((ROOT/'portal/panel.html').read_text());report=html.tostring(tree.get_element_by_id('reportCards'),encoding='unicode')
 styles=[]
 for link in tree.xpath('//link[@rel="stylesheet"]'):
  path=ROOT/'portal'/link.get('href').split('?',1)[0]
  if path.is_file():styles.append('<style media="'+link.get('media','all')+'">'+path.read_text()+'</style>')
 await page.set_content('<html lang="es" data-theme="oled" data-theme-tone="dark"><head><base href="https://seminario.test/portal/"><title>Panel de prueba</title>'+''.join(styles)+'</head><body class="dashboard-page" data-view="kardex"><div>'+report+'</div></body></html>')
 source=copy.deepcopy(data['snapshot']);source.update(institution=dict(data['snapshot']['institution'],rector_name=data['snapshot']['rector_name'],prefect_name=data['snapshot']['prefect_name']),formation_history=[data['snapshot']['formation']])
 source['formation_history'][0]=dict(source['formation_history'][0],period_name=source['period']['name'],starts_on=source['period']['starts_on'],ends_on=source['period']['ends_on'])
 source['rows']=[dict(row,period_id=PERIOD,period_name=source['period']['name'],starts_on=source['period']['starts_on'],ends_on=source['period']['ends_on'],enrollment_active=True) for row in source['rows']]
 await page.evaluate('''args => {
  window.__issue=args.issue;window.__record=args.source;window.__calls=[];window.__issueReads=0;window.__printRequested=0;
  window.print=()=>{window.__printRequested++};
  window.PortalAuth={getClient:()=>({rpc:(name,params)=>{
    window.__calls.push({name,params});return {retry(){return this},abortSignal:async()=>{
     if(params.p_resource==='preview')return {data:window.__issue.snapshot};
     if(params.p_resource==='issues')return {data:{items:[{id:window.__issue.id,folio:window.__issue.folio,period_name:window.__record.period.name}],has_more:false}};
     if(params.p_resource==='issue'){
      window.__issueReads++;
      if(args.deny && window.__issueReads>=2)return {error:{code:'42501'},status:403};
      return {data:window.__issue};
     }
     throw Error('RPC inesperada: '+name);
    }};
  }})};
 }''',{'issue':data,'source':source,'deny':deny_print})
 await page.add_script_tag(path=str(ROOT/'portal/report-cards.js'))
 await page.evaluate('window.PortalReportCards.mount(window.__record,async()=>{})')
 await page.locator('#reportIssues').get_by_role('button',name='Ver / imprimir boleta').click()
 await page.locator('#reportPreview').get_by_role('button',name='Imprimir / Guardar PDF').click()
 return context,page,errors

async def render(browser,data,path,*,mobile=False):
 original=json.dumps(data,ensure_ascii=False,sort_keys=True)
 context,page,errors=await setup(browser,data,mobile=mobile)
 await page.wait_for_function('window.__printRequested===1')
 await page.emulate_media(media='print')
 await page.evaluate('''() => window.addEventListener('beforeprint',()=>{
  const main=document.querySelector('#reportPrintRoot .report-main'),content=main.firstElementChild,
    footer=document.querySelector('#reportPrintRoot footer'),paper=document.querySelector('#reportPrintRoot .report-paper');
  window.__layout={mainBottom:main.getBoundingClientRect().bottom,contentBottom:content.getBoundingClientRect().bottom,
    footerBottom:footer.getBoundingClientRect().bottom,paperBottom:paper.getBoundingClientRect().bottom,
    scale:Number(content.style.getPropertyValue('--report-content-scale')||1),rows:paper.querySelectorAll('tbody tr').length};
 })''')
 form=data['snapshot']['formation'];sem=form['semester'];stage=form['stage_code']
 code=('CI' if stage=='introductorio' else str((sem+1)//2)+('F' if stage=='filosofia' else 'T'))+'-'+str(sem)
 await expect(page.locator('#reportPrintRoot .report-student')).to_contain_text(code)
 average=round(sum(round(r['score']*10) for r in data['snapshot']['rows'])/len(data['snapshot']['rows'])+1e-8)/10
 await expect(page.locator('#reportPrintRoot tfoot')).to_contain_text(f'{average:.1f}')
 for i,row in enumerate(data['snapshot']['rows']):
  cell=page.locator('#reportPrintRoot tbody tr').nth(i).locator('td')
  background=await cell.evaluate('e=>getComputedStyle(e).backgroundColor')
  assert (background=='rgb(255, 0, 0)')==(row['score']<=6.9),(row,background)
  assert await page.locator('#reportPrintRoot tbody tr').nth(i).locator('th').evaluate('e=>getComputedStyle(e).backgroundColor')!='rgb(255, 0, 0)'
 await page.pdf(path=str(path),prefer_css_page_size=True,display_header_footer=True,print_background=True)
 layout=await page.evaluate('window.__layout')
 assert layout and layout['contentBottom']<=layout['mainBottom']+1,layout
 assert layout['footerBottom']<layout['paperBottom'],layout
 assert layout['rows']==len(data['snapshot']['rows']),layout
 assert not errors,errors
 assert await page.evaluate('window.__calls.every(c=>c.name==="portal_report_card_read")')
 await page.wait_for_function('!document.getElementById("reportPrintRoot")')
 assert await page.evaluate('document.title')=='Panel de prueba'
 assert not await page.locator('#reportPrintRoot').count()
 assert await page.evaluate('!document.documentElement.classList.contains("report-printing")')
 assert json.dumps(data,ensure_ascii=False,sort_keys=True)==original
 await context.close()
 meta=subprocess.run(['pdfinfo',str(path)],text=True,capture_output=True,check=True).stdout
 assert re.search(r'Pages:\s+1\b',meta),meta
 assert '612 x 792 pts' in meta,meta
 text=subprocess.run(['pdftotext','-raw',str(path),'-'],text=True,capture_output=True,check=True).stdout
 normalized=''.join(text.split())
 for row in data['snapshot']['rows']:assert ''.join(row['name'].split()) in normalized,(row['name'],text)
 for label in [data['snapshot']['student']['full_name'],data['snapshot']['student']['student_number'],data['snapshot']['rector_name'],data['snapshot']['prefect_name']]:assert ''.join(label.split()) in normalized,label
 assert text.count(data['folio'])==1,text
 assert code in text and 'PROMEDIO SEMESTRAL' in text,text
 assert all(s in text for s in ['Emitida','Escala 0','Mínima aprobatoria 7.0']),text
 assert 'https://' not in text and 'http://' not in text and not re.search(r'\d{1,2}/\d{1,2}/\d{2},\s*\d{1,2}:\d{2}',text),text
 bbox=subprocess.run(['pdftotext','-bbox',str(path),'-'],text=True,capture_output=True,check=True).stdout
 words=html.fromstring(bbox).xpath('//*[local-name()="word"]')
 folio=next(w for w in words if data['folio'] in ''.join(w.itertext()))
 assert 710<float(folio.get('ymin') or folio.get('yMin'))<780,dict(folio.attrib)
 return layout

async def main():
 global OUT
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args();OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
  for code,n in COURSES:
   layout=await render(browser,issued(code,n),OUT/(code+'.pdf'))
   assert layout['scale']==1,layout
   print('PASS',code,n,'materias; una página, pie completo, encabezados externos ausentes',flush=True)
  for n in [10,20]:
   layout=await render(browser,issued('4T-7',n,stress=True),OUT/('nombres-largos-'+str(n)+'.pdf'),mobile=True)
   print('PASS',n,'materias con nombres de 160 caracteres; vista móvil/OLED; escala',round(layout['scale'],3),flush=True)
  for code in ['CI-1','1F-1','4T-7']:
   data=issued(code,5)
   for row,score in zip(data['snapshot']['rows'],[10,10,7,5,6.9]):row['score']=score
   await render(browser,data,OUT/('rojas-'+code+'.pdf'))
   print('PASS',code,'promedio 7.8; rojo solo en 5 y 6.9; 7 aprobatoria; una hoja',flush=True)
  context,page,errors=await setup(browser,issued(),deny_print=True)
  await expect(page.locator('#reportCards')).to_be_hidden()
  assert await page.evaluate('window.__printRequested')==0
  assert not await page.locator('#reportPrintRoot').count();assert not errors,errors
  await context.close();print('PASS se revalidan permisos antes de imprimir; ninguna impresión si se revocaron')
  await browser.close()
 print('TOTAL 21 escenarios de impresión. PDFs:',OUT)
if __name__=='__main__':asyncio.run(main())
