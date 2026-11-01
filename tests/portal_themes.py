"""Temas del portal: navegador real, fixtures ficticios y ninguna escritura en producción."""
import asyncio,json,shutil
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_learning as l
import portal_weighted_grades as grades
import portal_batch_and_professors as batch
import portal_workspace as w

KEY='seminario.portal.theme';checks=0

async def choose(page,mode):
    if not await page.locator('#portalThemeOptions').is_visible():await page.locator('#portalThemeButton').click()
    await page.locator('#portalThemeOptions input[value="'+mode+'"]').check()
    await expect(page.locator('html')).to_have_attribute('data-theme',mode)
    await page.keyboard.press('Escape')
    await expect(page.locator('#portalThemeButton')).to_have_attribute('aria-expanded','false')

async def contrast(page,selectors):
    results=await page.evaluate(r'''selectors=>{
        const rgba=s=>s.match(/[\d.]+/g)?.map(Number)||[0,0,0,0];
        const blend=(a,b)=>[0,1,2].map(i=>a[i]*(a[3]??1)+b[i]*(1-(a[3]??1)));
        function background(e){if(!e)return[255,255,255];const c=rgba(getComputedStyle(e).backgroundColor);return(c[3]??1)>=1?c:blend(c,background(e.parentElement));}
        const lum=c=>c.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((n,x,i)=>n+x*[.2126,.7152,.0722][i],0);
        return selectors.flatMap(s=>[...document.querySelectorAll(s)].filter(e=>e.getClientRects().length&&!e.disabled).map(e=>{const a=lum(rgba(getComputedStyle(e).color)),b=lum(background(e));return{selector:s,text:e.textContent.slice(0,50),ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};}));
    }''',selectors)
    assert results,selectors
    assert all(r['ratio']>=4.5 for r in results),[r for r in results if r['ratio']<4.5]

async def done(c,state,label,data=None):
    global checks
    assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors']
    if data is not None:assert not data.get('errors'),data.get('errors')
    checks+=1;print('PASS '+label,flush=True);await c.close()

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for role in ['student','professor','control_escolar']:
            for mobile in [False,True]:
                c,page,state,data=await l.fixture(browser,role,mobile=mobile)
                await expect(page.locator('html')).to_have_attribute('data-theme','light')
                for mode in ['dark','oled','light']:
                    await choose(page,mode)
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(role,mobile,mode)
                    assert await page.locator('#portalThemeButton').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight}')
                    if mode!='light':
                        await contrast(page,['#welcomeTitle','.campus-widget .learning-meta','.header-account','.workspace-nav a','#portalThemeButton'])
                        bg=await page.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')
                        assert bg==('rgb(0, 0, 0)' if mode=='oled' else 'rgb(14, 18, 25)'),bg
                        await page.screenshot(path=str(h.ARTIFACTS/f'tema-{role}-{mode}-{mobile}.png'),full_page=True)
                assert await page.locator('#workspaceNav').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(73, 72, 77)'
                await done(c,state,role+(' móvil' if mobile else ' escritorio')+': tres temas, contraste, botón y disposición',data)

        c,page,state,data=await l.fixture(browser,'student')
        await choose(page,'dark');await page.reload();await expect(page.locator('html')).to_have_attribute('data-theme','dark')
        second=await c.new_page();await second.goto(h.BASE+'/portal/panel.html');await expect(second.locator('#portalThemeButton')).to_be_visible()
        await choose(second,'oled');await expect(page.locator('html')).to_have_attribute('data-theme','oled')
        await second.close();await page.locator('#logoutButton').click();await expect(page).to_have_url(h.BASE+'/portal/index.html?estado=sesion_cerrada')
        await expect(page.locator('html')).to_have_attribute('data-theme','oled')
        await contrast(page,['.access-intro h2','.access-intro p','.login-subtitle','.form-group label','.login-button','#portalThemeButton'])
        assert await page.locator('.brand-logo').evaluate('(e)=>getComputedStyle(e).filter')=='none'
        await page.screenshot(path=str(h.ARTIFACTS/'tema-acceso-oled.png'),full_page=True)
        await page.goto(h.BASE+'/portal/activar.html');await expect(page.locator('html')).to_have_attribute('data-theme','oled')
        await expect(page.locator('#portalThemeButton')).to_be_visible();await choose(page,'light')
        await done(c,state,'Preferencia persistente entre recargas, pestañas, salida y activación',data)

        c,page,state=await h.fixture(browser,session=False,start='index.html')
        await page.evaluate('(key)=>localStorage.setItem(key,"<invalid>")',KEY);await page.reload()
        await expect(page.locator('html')).to_have_attribute('data-theme','light')
        await c.add_init_script('''const get=Storage.prototype.getItem,set=Storage.prototype.setItem;Storage.prototype.getItem=function(k){if(k==='seminario.portal.theme')throw new DOMException('blocked');return get.call(this,k)};Storage.prototype.setItem=function(k,v){if(k==='seminario.portal.theme')throw new DOMException('blocked');return set.call(this,k,v)};''')
        await page.reload();await choose(page,'dark');await expect(page.get_by_role('button',name='Iniciar sesión',exact=True)).to_be_visible()
        await done(c,state,'Preferencia inválida o almacenamiento bloqueado no interrumpen el acceso')

        c,page,state=await h.fixture(browser,session=False,start='index.html',mobile=True)
        for width in [390,320]:
            await page.set_viewport_size({'width':width,'height':844});await page.locator('#portalThemeButton').click()
            assert await page.locator('#portalThemeOptions').evaluate('(p)=>{const a=p.getBoundingClientRect(),b=document.getElementById("portalThemeButton").getBoundingClientRect();return a.left>=0&&a.right<=innerWidth&&a.top>=b.bottom&&a.bottom<=innerHeight}')
            await page.keyboard.press('Escape');await choose(page,'dark')
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await done(c,state,'Acceso móvil: selector dentro de la pantalla y debajo de su botón en 320 y 390 px')

        for role in ['student','professor']:
            c,page,state,data,weights=await grades.fixture(browser,role)
            for mode in ['dark','oled']:
                await choose(page,mode)
                await contrast(page,['.weighted-number','.weighted-category h3','.weighted-category-score','.learning-grades-table td','.learning-gradebook td','.learning-gradebook th','.learning-button'])
                assert not weights['writes']
                await page.screenshot(path=str(h.ARTIFACTS/f'tema-notas-{role}-{mode}.png'),full_page=True)
            if role=='professor':
                await page.get_by_role('button',name='Configurar evaluación',exact=True).click()
                await expect(page.locator('.weighted-configuration')).to_be_visible()
                await contrast(page,['.weighted-configuration label','.weighted-configuration h3','.weighted-configuration input','.weighted-configuration .learning-button'])
            await done(c,state,role+': notas y ponderaciones con contraste sin modificar calificaciones',data)

        for role in ['student','professor']:
            c,page,state,data=await l.fixture(browser,role,route=f'curso/{l.COURSE}/contenido')
            await choose(page,'dark');await expect(page.locator('.learning-outline-topic').first).to_be_visible()
            await page.locator('.learning-outline-topic').first.click()
            await expect(page.locator('.learning-reader-body')).to_be_visible()
            await contrast(page,['.learning-outline-topic','.learning-outline-title','.learning-reader-body h2','.learning-reader-body .learning-prose','.learning-reader-arrow:enabled'])
            await page.screenshot(path=str(h.ARTIFACTS/f'tema-contenido-{role}.png'),full_page=True)
            if role=='professor':
                await page.get_by_role('button',name='Editar contenido',exact=True).click();await expect(page.locator('#learningDialog')).to_be_visible()
                await contrast(page,['#learningDialog label','#learningDialog input','#learningDialog textarea','#learningDialog .learning-button'])
                await page.keyboard.press('Escape')
            assert not data['writes']
            await done(c,state,role+': lector de contenido y formulario docente en oscuro sin escrituras',data)

        c,page,state,data=await batch.fixture(browser,mobile=True)
        await choose(page,'oled');await batch.open_batch(page)
        await expect(page.locator('#batchEnrollmentList input')).to_have_count(38)
        await contrast(page,['#batchEnrollmentTitle','#batchEnrollmentSummary strong','#batchEnrollmentStatus','.batch-enrollment-person strong','.batch-enrollment-person small','#batchEnrollmentStage','#batchEnrollmentSearch'])
        assert not data['batch_calls'];assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(h.ARTIFACTS/'tema-inscripcion-oled-movil.png'))
        await page.keyboard.press('Escape');await expect(page.locator('#batchEnrollmentDialog')).not_to_be_visible()
        await done(c,state,'Inscripción múltiple OLED en celular: formularios, estados y selección intactos')

        c,page,state,data=await batch.fixture(browser)
        await choose(page,'dark');await w.nav(page,'clases')
        await contrast(page,['#classDirectoryCount','.class-directory-card h4','.class-directory-tile small'])
        await w.nav(page,'catalogos-academicos');await expect(page.locator('#organizerSources')).not_to_be_empty()
        await contrast(page,['#organizerCount','.organizer-subject strong','.organizer-subject p'])
        data['assignments']=[{'id':w.AS,'person_id':w.P,'class_id':w.CL,'full_name':'Profesor ficticio','subject_name':'Materia de prueba','period_name':'Periodo ficticio','active':True}]
        await w.nav(page,'profesores');await expect(page.locator('.management-professor')).to_have_count(1)
        await contrast(page,['.management-professor summary h3','.management-professor summary>span'])
        data['read_status']=500;await page.locator('#managementRefresh').click();await expect(page.locator('#managementMessage')).to_have_class(__import__('re').compile('error'))
        await contrast(page,['#managementMessage'])
        assert not data['batch_calls']
        await done(c,state,'Control Escolar: clases, organizador, profesores agrupados y errores legibles')

        c,page,state,data=await l.fixture(browser,'professor')
        await choose(page,'oled')
        await page.evaluate('''()=>{for(const cls of ['report-paper','kardex-paper']){const d=document.createElement('article');d.className=cls;const h=document.createElement('h2');h.textContent='Documento ficticio';d.append(h);document.body.append(d)}}''')
        for paper in ['.report-paper','.kardex-paper']:
            assert await page.locator(paper).evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
            await contrast(page,[paper+' h2'])
        await page.emulate_media(media='print');await expect(page.locator('[data-theme-control]')).to_be_hidden()
        assert await page.locator('html').evaluate('(e)=>getComputedStyle(e).colorScheme')=='light'
        assert await page.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')!='rgb(0, 0, 0)'
        await done(c,state,'Documentos blancos e impresión independiente del modo OLED',data)

        c,page,state,data=await l.fixture(browser,'student',mobile=True)
        await page.set_viewport_size({'width':320,'height':740});await page.locator('#portalThemeButton').click()
        await expect(page.locator('#portalThemeOptions')).to_be_visible()
        await page.keyboard.press('ArrowDown');await expect(page.locator('html')).to_have_attribute('data-theme','dark')
        await page.keyboard.press('ArrowDown');await expect(page.locator('html')).to_have_attribute('data-theme','oled')
        await page.keyboard.press('Escape');await expect(page.locator('#portalThemeButton')).to_be_focused()
        await page.locator('#menuToggle').click();await expect(page.locator('#workspaceNav')).to_have_class(__import__('re').compile('menu-open'))
        await page.locator('#menuToggle').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await done(c,state,'Teclado, Escape, foco y menú lateral en pantalla de 320 px',data)
        await browser.close()
    print('PASS '+str(checks)+' escenarios de temas.',flush=True)

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
