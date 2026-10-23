"""Navegación real en Chromium; API simulada, sin datos ni mensajes reales."""
import asyncio,copy,json,re,shutil
from pathlib import Path
from playwright.async_api import async_playwright,expect
import portal_learning as l
h=l.h
checks=0

def check(name,condition=True):
    global checks
    assert condition,name
    checks+=1;print('PASS',name,flush=True)

def sample(role):
    data=l.sample_data(role)
    assignments=[]
    for n,(title,category) in enumerate([('Tarea 1','tasks'),('Tarea 2','tasks'),('Examen parcial','exams'),('Examen final','exams'),('Proyecto de investigación','projects'),('Participación en clase','participation')],1):
        assignments.append({'id':f'a2000000-0000-4000-8000-{n:012d}','title':title,'grading_category':category,'requires_submission':category in ['tasks','projects'],'published':True,'due_at':None})
    categories=[{'code':c,'weight':w,'mode':'equal'} for c,w in zip(['tasks','exams','projects','participation'],[30,50,20,0])]
    scheme={'categories':categories,'items':[{'id':a['id'],'category':a['grading_category'],'share':1} for a in assignments]}
    summary={'configured':True,'average':72.5,'coverage':30,'categories':[{'code':c['code'],'weight':c['weight'],'average':72.5 if c['code']=='tasks' else None} for c in categories],
             'items':[{'id':a['id'],'category':a['grading_category'],'weight':15 if i<2 else 25 if i<4 else 20 if i==4 else 0,'score':100 if i==0 else 45 if i==1 else None} for i,a in enumerate(assignments)],'pending':3,'unpublished':0,'ready':False,'reasons':['Faltan tres evaluaciones por publicar.'],'token':'a'*32}
    grades=[{'assignment_id':a['id'],'score':100 if i==0 else 45 if i==1 else None,'published_score':100 if i==0 else 45 if i==1 else None,'revision':1 if i<2 else 0,'feedback':'','published_feedback':'','submitted_at':None} for i,a in enumerate(assignments)]
    students=[{'enrollment_id':l.ENROLLMENT,'name':'Seminarista de prueba','final_score':None,'grades':grades,'exemptions':[],'summary':summary,'draft_summary':copy.deepcopy(summary)}]
    book={'assignments':assignments,'students':students,'has_more':False,'revision':1,'draft':copy.deepcopy(scheme),'published':copy.deepcopy(scheme),'errors':[]}
    own={'summary':{k:v for k,v in summary.items() if k not in ['token','ready','reasons','unpublished']},'final_score':None,'categories':categories,
         'assignments':[{**a,'category':a['grading_category'],'score':g['published_score'],'feedback':'','submitted':True,'exempt':False} for a,g in zip(assignments,grades)]}
    return data,book,own

async def fixture(browser,role='student',mobile=False):
    data,book,own=sample(role)
    context,page,state,data=await l.fixture(browser,role,mobile=mobile,data=data)
    weights={'book':book,'own':own,'writes':[],'status':200,'read_status':200,'gate':None,'started':asyncio.Event()}
    async def api(route):
        path=route.request.url
        if 'portal_gradebook_' not in path:return await route.fallback()
        headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'POST,OPTIONS','Content-Type':'application/json'}
        if route.request.method=='OPTIONS':return await route.fulfill(status=204,headers=headers)
        args=route.request.post_data_json
        if path.endswith('portal_gradebook_read'):
            weights['started'].set()
            if weights['gate']:await weights['gate'].wait()
            if weights['read_status']!=200:return await route.fulfill(status=weights['read_status'],headers=headers,body=json.dumps({'code':'PGRST202','message':'Missing migration'}))
            return await route.fulfill(status=200,headers=headers,body=json.dumps(own if args['p_resource']=='own' else book))
        weights['writes'].append(copy.deepcopy(args))
        if weights['status']!=200:return await route.fulfill(status=weights['status'],headers=headers,body=json.dumps({'code':'XX000','message':'Simulated failure'}))
        action=args['p_action'];payload=args['p_data']
        if action=='scheme_save':book['draft']=payload['schema'];book['revision']+=1
        elif action=='scheme_publish':book['published']=payload['schema'];book['revision']+=1
        elif action=='assessment_save':
            s=book['students'][0]
            if payload['exempt']:s['exemptions']=[{'id':payload['assignment_id'],'reason':payload['reason']}]
            else:
                g=next(g for g in s['grades'] if g['assignment_id']==payload['assignment_id']);g['score']=payload['score'];g['revision']+=1
                if payload['publish']:g['published_score']=g['score']
        elif action=='assessments_save':
            for item in payload['items']:
                g=next(g for g in book['students'][0]['grades'] if g['assignment_id']==item['assignment_id']);g['score']=item['score'];g['revision']+=1
                if payload['publish']:g['published_score']=g['score']
        elif action=='final_publish':book['students'][0]['final_score']=79.75
        return await route.fulfill(status=200,headers=headers,body=json.dumps({'id':l.COURSE,'saved':True}))
    await context.route(h.API+'/**',api)
    await page.evaluate('(hash)=>location.hash=hash',f'curso/{l.COURSE}/'+('mis-notas' if role=='student' else 'calificaciones'))
    await expect(page.locator('#learningContent')).to_contain_text('Promedio actual de la clase' if role=='student' else 'Libro de calificaciones')
    return context,page,state,data,weights

async def finish(context,state,data,name):
    check(name,not state['errors'] and not state['route_errors'] and not data['errors']);await context.close()

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        c,p,s,d,w=await fixture(browser)
        await expect(p.locator('.weighted-summary')).to_contain_text('72.5 / 100')
        await expect(p.locator('.weighted-summary')).to_contain_text('30 % del curso')
        await expect(p.locator('.weighted-categories')).to_contain_text('Tareas')
        await expect(p.get_by_role('button',name='Configurar evaluación')).to_have_count(0)
        await expect(p.locator('.weighted-table')).to_contain_text('Evaluación del profesor')
        check('student sees category averages, progress and pending final separately')
        await p.screenshot(path=str(h.ARTIFACTS/'promedios-alumno.png'),full_page=True)
        await finish(c,s,d,'student has no staff controls or JS errors')

        c,p,s,d,w=await fixture(browser,'professor')
        await p.evaluate('window.PortalLearning.navigate()')
        await p.get_by_role('button',name='Configurar evaluación',exact=True).click()
        check('rechecking the same route preserves gradebook controls')
        await expect(p.locator('.weighted-total')).to_have_text('Total: 100 % de 100 %')
        await p.get_by_label('Porcentaje de Tareas',exact=True).fill('25')
        await expect(p.locator('.weighted-total')).to_have_text('Total: 95 % de 100 %')
        await expect(p.get_by_role('button',name='Revisar y publicar criterios')).to_be_disabled()
        await p.get_by_label('Porcentaje de Participación',exact=True).fill('5')
        await p.get_by_label('Repartir Exámenes',exact=True).select_option('custom')
        await p.get_by_label('Peso de Examen parcial',exact=True).fill('40')
        await p.get_by_label('Peso de Examen final',exact=True).fill('60')
        await expect(p.locator('.weighted-dialog .weighted-table')).to_contain_text('20 %')
        await p.get_by_role('button',name='Guardar borrador',exact=True).click()
        await expect(p.get_by_role('button',name='Revisar y publicar criterios')).to_be_enabled()
        check('saving draft reopens review; custom exam weights and category totals shown')
        await p.screenshot(path=str(h.ARTIFACTS/'promedios-configuracion.png'),full_page=True)
        await p.get_by_role('button',name='Revisar y publicar criterios').click()
        await p.get_by_label('Motivo del cambio (obligatorio)',exact=True).fill('Criterios acordados para este semestre')
        await p.get_by_role('checkbox',name=re.compile('He revisado los porcentajes')).check()
        await p.get_by_role('button',name='Publicar criterios',exact=True).click()
        await expect(p.locator('.weighted-overview')).to_contain_text('Tareas: 25 %')
        check('scheme publication is explicit and carries revision, confirmation and reason',w['writes'][-1]['p_data']['confirmed'] and w['writes'][-1]['p_data']['revision']==2)
        await p.get_by_role('button',name='Revisar / calificar',exact=True).first.click()
        await p.get_by_role('button',name='Registrar cero por no entregar').click()
        await expect(p.get_by_label('Calificación (0 a 100)',exact=True)).to_have_value('0')
        await p.get_by_role('checkbox',name='Publicar esta calificación para el alumno').uncheck()
        await p.get_by_role('button',name='Guardar evaluación',exact=True).click()
        await expect(p.locator('.weighted-dialog')).to_have_count(0)
        check('zero is deliberate and draft/publication choice preserved',w['writes'][-1]['p_data']['score']==0 and not w['writes'][-1]['p_data']['publish'])
        await p.get_by_role('button',name='Revisar / calificar',exact=True).first.click()
        await p.get_by_role('checkbox',name='Exentar esta actividad para este alumno').check()
        await p.get_by_label('Motivo de la exención',exact=True).fill('Ausencia justificada por la institución')
        await expect(p.get_by_label('Calificación (0 a 100)',exact=True)).to_be_disabled()
        await p.get_by_role('button',name='Guardar evaluación',exact=True).click()
        await expect(p.locator('.weighted-table')).to_contain_text('Exentada')
        check('individual exemption has a reason and visible status')
        await p.get_by_role('button',name='Captura rápida',exact=True).click()
        await p.get_by_label('Calificación de Seminarista de prueba: Tarea 2',exact=True).fill('70')
        await p.get_by_role('button',name='Guardar borradores',exact=True).click()
        await p.locator('.weighted-dialog').get_by_role('button',name='Guardar borradores',exact=True).click()
        await expect(p.locator('.weighted-dialog')).to_have_count(0)
        check('quick entry saves a batch of drafts',w['writes'][-1]['p_action']=='assessments_save' and not w['writes'][-1]['p_data']['publish'])
        await p.get_by_role('button',name='Guardar y publicar notas',exact=True).click()
        await p.locator('.weighted-dialog').get_by_role('button',name='Guardar y publicar',exact=True).click()
        await expect(p.locator('.weighted-dialog')).to_have_count(0)
        check('quick entry can publish saved drafts without retyping',w['writes'][-1]['p_data']['publish'])
        await p.get_by_role('button',name='Revisar y publicar finales',exact=True).click()
        await expect(p.get_by_role('checkbox',name='Seleccionar a Seminarista de prueba')).to_be_disabled()
        await expect(p.locator('.weighted-dialog')).to_contain_text('Faltan tres evaluaciones')
        await p.keyboard.press('Escape')
        w['book']['students'][0]['summary'].update(ready=True,average=79.75,coverage=100,reasons=[])
        await p.get_by_role('button',name='Actualizar libro',exact=True).click()
        await expect(p.locator('.weighted-table')).to_contain_text('79.75')
        await p.get_by_role('button',name='Revisar y publicar finales',exact=True).click()
        await p.get_by_role('checkbox',name='Seleccionar a Seminarista de prueba').check()
        await p.get_by_role('checkbox',name=re.compile('He revisado las notas seleccionadas')).check()
        await p.get_by_role('button',name='Publicar finales seleccionadas',exact=True).click()
        await expect(p.locator('.weighted-dialog')).to_have_count(0)
        check('final review blocks pending evaluations and confirms selected students',w['writes'][-1]['p_action']=='final_publish')
        async with p.expect_download() as download:
            await p.get_by_role('button',name='Exportar alumnos mostrados').click()
        download=await download.value;check('grade summary CSV exports',download.suggested_filename=='promedios-clase.csv')
        await p.get_by_role('button',name='Nueva actividad',exact=True).click()
        await p.get_by_label('Tipo de actividad',exact=True).select_option('participation')
        await p.get_by_role('button',name='Continuar',exact=True).click()
        await expect(p.locator('#learning-field-grading_category')).to_have_value('participation')
        await expect(p.get_by_role('checkbox',name='El alumno debe entregar un trabajo en el portal')).not_to_be_checked()
        check('participation creation defaults to direct evaluation without file submission')
        await p.keyboard.press('Escape')
        await finish(c,s,d,'professor configuration and grading flows work')

        c,p,s,d,w=await fixture(browser,'control_escolar',mobile=True)
        await expect(p.get_by_role('button',name='Configurar evaluación')).to_be_visible()
        check('Control Escolar has same gradebook access')
        check('mobile gradebook stays within viewport',await p.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        await p.get_by_role('button',name='Configurar evaluación').click()
        check('mobile configuration stays within viewport',await p.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        await p.screenshot(path=str(h.ARTIFACTS/'promedios-configuracion-movil.png'),full_page=True)
        await p.keyboard.press('Escape')
        await p.get_by_role('button',name='Revisar / calificar',exact=True).first.click()
        w['status']=500
        await p.get_by_role('button',name='Guardar evaluación',exact=True).click()
        await expect(p.locator('.weighted-dialog')).to_contain_text('No se pudo confirmar')
        await expect(p.get_by_role('button',name='Guardar evaluación',exact=True)).to_be_disabled()
        check('uncertain writes cannot be blindly repeated')
        await p.keyboard.press('Escape')
        w['gate']=asyncio.Event();w['started'].clear()
        await p.get_by_role('button',name='Actualizar libro',exact=True).click()
        await w['started'].wait()
        await p.evaluate('location.hash="inicio"');w['gate'].set()
        await expect(p.locator('#learningRoot')).to_be_hidden()
        check('late gradebook response does not repaint after leaving course')
        await finish(c,s,d,'Control Escolar and navigation remain sound')
        c,p,s,d,w=await fixture(browser,'professor')
        w['read_status']=404
        await p.get_by_role('button',name='Actualizar libro',exact=True).click()
        await expect(p.locator('#learningContent')).to_contain_text('Falta instalar la actualización de ponderaciones')
        check('missing SQL migration gives a clear installation message')
        await finish(c,s,d,'missing migration leaves authentication intact')
        await browser.close()
    print('PASS',checks,'browser checks')

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
