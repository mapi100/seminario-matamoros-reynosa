"""Regresión visual del acceso integrado de file:// tras cerrar sesión."""
import asyncio,shutil
from pathlib import Path
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_learning as l
from portal_themes import choose,contrast

async def main():
    checks=0
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for mobile in [False,True]:
            for mode in ['light','dark','oled']:
                c,page,state,data=await l.fixture(browser,'student',mobile=mobile)
                # Ejercitar la rama file:// con el mismo SDK y API simulada del servidor de pruebas.
                source=(h.ROOT/'portal/panel.js').read_text()
                assert source.count('window.location.protocol === "file:"')==1
                source=source.replace('window.location.protocol === "file:"','true')
                await c.route('**/portal/panel.js*',lambda route:route.fulfill(status=200,content_type='application/javascript',body=source))
                await page.reload();await expect(page.locator('#panelContent')).to_be_visible()
                await choose(page,mode);await page.locator('#logoutButton').click()
                await expect(page.locator('body')).to_have_attribute('data-view','acceso')
                await expect(page.locator('#localAccess')).to_be_visible();await expect(page.locator('#localLoginMessage')).to_contain_text('Has cerrado sesión')
                await expect(page.locator('#portalThemeButton')).to_be_visible()
                assert await page.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')=={'light':'rgb(244, 246, 249)','dark':'rgb(14, 18, 25)','oled':'rgb(0, 0, 0)'}[mode]
                if mode!='light':
                    assert await page.locator('#localAccess').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgba(0, 0, 0, 0)'
                    await contrast(page,['#localAccess .access-intro h2','#localAccess .access-intro p','#localAccess label','#localAccess .login-button'])
                if mobile:await page.set_viewport_size({'width':320,'height':740})
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                await page.screenshot(path=str(h.ARTIFACTS/f'acceso-local-{mode}-{mobile}.png'),full_page=True)
                await choose(page,'light' if mode!='light' else 'dark')
                await expect(page.locator('#localAccess')).to_be_visible()
                assert not state['errors'],state['errors'];assert not state['route_errors'],state['route_errors'];assert not data['errors'],data['errors']
                checks+=1;print('PASS acceso integrado '+mode+(' móvil' if mobile else ' escritorio'),flush=True);await c.close()
        await browser.close()
    print('PASS '+str(checks)+' escenarios de acceso integrado y tema.',flush=True)

if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
