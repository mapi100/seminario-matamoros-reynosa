"""Functional checks for Mis materias: real pinned SDK, simulated API only.

Prerequisites: Python 3, `python3 -m pip install playwright`, and Chromium.
Run from any directory: `python3 tests/portal_subjects.py`.
CHROMIUM_PATH optionally selects an installed browser; otherwise the test uses
chromium/chromium-browser on PATH, or the Playwright-managed Chromium install.
PORTAL_TEST_ARTIFACTS optionally keeps screenshots in that directory. The server
and its document root use a temporary directory and stop after every run.
The SDK is downloaded over verified HTTPS and checked against panel.html's SRI.
All Auth and PostgreSQL API traffic is mocked; no real credentials/data are used.
"""
import asyncio, base64, copy, functools, hashlib, json, os, shutil, tempfile, threading, time
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
API = 'https://fixture.supabase.co'

class SDKScriptParser(HTMLParser):
    sdk = None
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script' and '@supabase/supabase-js@' in attributes.get('src', ''):
            self.sdk = attributes

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

def prepare():
    global TEMP, OUT, ARTIFACTS, BASE, SDK, server
    parser = SDKScriptParser()
    parser.feed((ROOT/'portal/panel.html').read_text())
    assert parser.sdk, 'panel.html must contain the pinned Supabase SDK'
    url = parser.sdk['src']
    assert urlparse(url).scheme == 'https', 'SDK download must use HTTPS'
    integrity = parser.sdk.get('integrity', '')
    algorithm, separator, expected = integrity.partition('-')
    assert algorithm == 'sha384' and separator and expected, 'Expected SHA384 SRI'
    with urlopen(url, timeout=30) as response:
        SDK = response.read()
    actual = base64.b64encode(hashlib.sha384(SDK).digest()).decode()
    assert actual == expected, 'Downloaded Supabase SDK does not match panel.html SRI'
    TEMP = tempfile.TemporaryDirectory(prefix='seminario-subject-tests-')
    OUT = Path(TEMP.name)
    ARTIFACTS = Path(os.environ.get('PORTAL_TEST_ARTIFACTS', str(OUT)))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    www = OUT/'www'
    www.mkdir()
    (www/'seminario-matamoros-reynosa').symlink_to(ROOT, target_is_directory=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(www)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    BASE = f'http://127.0.0.1:{server.server_port}/seminario-matamoros-reynosa'

UID = '11111111-1111-4111-8111-111111111111'
USER = {'id':UID,'aud':'authenticated','role':'authenticated','email':'fixture@example.invalid','email_confirmed_at':'2026-01-01T00:00:00Z','app_metadata':{'provider':'email','providers':['email']},'user_metadata':{'role':'control_escolar'},'created_at':'2026-01-01T00:00:00Z'}
def enc(data): return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
TOKEN = enc({'alg':'HS256','typ':'JWT'})+'.'+enc({'sub':UID,'role':'authenticated','aud':'authenticated','exp':int(time.time())+3600})+'.fixture-signature'
SESSION = {'access_token':TOKEN,'refresh_token':'fixture-refresh-token','token_type':'bearer','expires_in':3600,'expires_at':int(time.time())+3600,'user':USER}
DEFAULT_PROFILE = {'full_name':'Usuario de prueba','role':'student','active':True}
def subject(i, *, name=None):
    return {'id':f'22222222-2222-4222-8222-{i:012d}', 'subjects':{'code':f'MAT-{i:03d}','name':name or f'Materia de ejemplo {i}'},'academic_periods':{'name':'Periodo de prueba 2026','starts_on':'2026-08-01','ends_on':'2026-12-18'}}
checks = 0

async def fixture(browser, *, mobile=False, session=True, profile=None, rows=None, enrollment_status=200, enrollment_gate=None, start='panel.html', user_status=200, initial_hidden=False):
    state={'profile':copy.deepcopy(DEFAULT_PROFILE) if profile is None else profile,'user_status':user_status,'rows':copy.deepcopy(rows) if rows is not None else [subject(1),subject(2)],'enrollment_status':enrollment_status,'enrollment_gate':enrollment_gate,'enrollment_started':asyncio.Event(),'enrollment_requests':[],'requests':[],'errors':[],'route_errors':[]}
    context=await browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':900})
    if initial_hidden:
        await context.add_init_script('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"})')
    page=await context.new_page()
    page.on('pageerror',lambda err:state['errors'].append(str(err)))
    await context.route('https://cdn.jsdelivr.net/**',lambda route:route.fulfill(status=200,body=SDK,headers={'Content-Type':'application/javascript','Access-Control-Allow-Origin':'*'}))
    config='window.PORTAL_SUPABASE_CONFIG = Object.freeze('+json.dumps({'url':API,'publishableKey':'sb_publishable_fixture_only'})+');'
    await context.route('**/supabase-config.js',lambda route:route.fulfill(status=200,body=config,content_type='application/javascript'))
    async def api_route(route):
        request=route.request
        path=urlparse(request.url).path
        query=parse_qs(urlparse(request.url).query)
        state['requests'].append((request.method,request.url))
        headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Content-Type':'application/json','Access-Control-Expose-Headers':'Content-Range'}
        if request.method=='OPTIONS': return await route.fulfill(status=204,headers=headers)
        try:
            if path=='/auth/v1/token':
                status=200; data=SESSION
            elif path=='/auth/v1/user':
                status=state['user_status']; data=USER if status==200 else {'code':'bad_jwt','message':'Invalid token'}
            elif path=='/rest/v1/profiles':
                assert query=={'select':['full_name,role,active'],'id':['eq.'+UID]},query
                status=200; data=[state['profile']] if state['profile'] else []
            elif path=='/rest/v1/enrollments':
                assert request.method=='GET',request.method
                assert query.get('select')==['id,subjects(code,name),academic_periods(name,starts_on,ends_on)'],query
                state['enrollment_requests'].append({'query':query,'headers':request.headers})
                state['enrollment_started'].set()
                gate=state['enrollment_gate']
                status=state['enrollment_status']
                rows=copy.deepcopy(state['rows'])
                if gate: await gate.wait()
                offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',[str(len(rows))])[0])
                if 'range' in request.headers:
                    start,end=request.headers['range'].split('-');offset=int(start);limit=int(end)-offset+1
                data=rows[offset:offset+limit] if status==200 else {'code':'42501' if status==403 else '42P01','message':'Fixture API error'}
                headers['Content-Range']=f'{offset}-{max(offset,len(data)+offset-1)}/{len(rows)}' if status==200 else '*/*'
            elif path=='/auth/v1/logout':
                status=204; data=None
            else: raise AssertionError('Unexpected API request '+request.url)
            await route.fulfill(status=status,headers=headers,body='' if data is None else json.dumps(data))
        except Exception as exc:
            # Aborted browser requests during signout are expected. Assertions are not.
            if isinstance(exc,AssertionError): state['route_errors'].append(str(exc))
            if 'Target page, context or browser has been closed' not in str(exc):
                if not isinstance(exc,AssertionError): state['route_errors'].append(str(exc))
            try: await route.abort()
            except Exception: pass
    await context.route(API+'/**',api_route)
    if session:
        await page.goto(BASE+'/index.html')
        await page.evaluate('(session) => localStorage.setItem("seminario-mr-auth", JSON.stringify(session))',SESSION)
    await page.goto(BASE+'/portal/'+start,wait_until='domcontentloaded')
    return context,page,state

async def visible(page):
    await expect(page.locator('#panelContent')).to_be_visible()
    await expect(page.locator('#subjectsSection')).to_be_visible()

async def finished(context,state,label):
    global checks
    assert not state['errors'],state['errors']
    assert not state['route_errors'],state['route_errors']
    assert all(method in ['GET','OPTIONS'] or '/auth/v1/' in url for method,url in state['requests']),state['requests']
    checks+=1
    print('PASS '+label,flush=True)
    if state['enrollment_gate']: state['enrollment_gate'].set()
    await context.close()

async def main():
    async with async_playwright() as pw:
        browser_path = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        browser=await pw.chromium.launch(executable_path=browser_path,headless=True)
        context,page,state=await fixture(browser)
        await visible(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
        await expect(page.locator('.subject-name').first).to_have_text('Materia de ejemplo 1')
        await expect(page.locator('.subject-code').first).to_contain_text('MAT-001')
        await expect(page.locator('.subject-period').first).to_contain_text('Periodo de prueba 2026')
        assert state['enrollment_requests'][0]['query']['order']==['created_at.desc,id.asc']
        await page.screenshot(path=str(ARTIFACTS/'subjects-desktop.png'),full_page=True)
        before=len(state['enrollment_requests'])
        await page.reload(wait_until='networkidle')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
        assert len(state['enrollment_requests'])>before
        await finished(context,state,'student renders own subjects and reload fetches again')

        context,page,state=await fixture(browser,rows=[])
        await visible(page)
        await expect(page.locator('#subjectsStatus')).to_contain_text('Todavía no tienes materias inscritas.')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
        await finished(context,state,'valid empty enrollment response shows empty state')

        for status in [403,404,500]:
            context,page,state=await fixture(browser,enrollment_status=status)
            await visible(page)
            await expect(page.locator('#subjectsRetry')).to_be_visible()
            await expect(page.locator('#subjectsStatus')).not_to_contain_text('Todavía no tienes materias inscritas.')
            await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
            state['enrollment_status']=200
            await page.locator('#subjectsRetry').click()
            await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
            await expect(page.locator('#subjectsRetry')).to_be_hidden()
            await finished(context,state,f'HTTP {status} distinct error state and retry succeeds')

        for role in ['professor','control_escolar']:
            context,page,state=await fixture(browser,profile={'full_name':'Otra función','role':role,'active':True})
            await expect(page.locator('#panelContent')).to_be_visible()
            await expect(page.locator('#subjectsSection')).to_be_hidden()
            assert not state['enrollment_requests']
            await finished(context,state,'no student query for '+role)

        for options,label in [({'session':False},'anonymous'),({'profile':[]},'missing profile'),({'profile':{'full_name':'Desactivado','role':'student','active':False}},'inactive profile'),({'user_status':401},'invalid identity')]:
            context,page,state=await fixture(browser,**options)
            await expect(page).to_have_url(__import__('re').compile(r'/portal/index\.html'))
            assert not state['enrollment_requests']
            await finished(context,state,'denied '+label+' never queries enrollments')

        rows=[subject(1,name='<img src=x onerror=alert(1)>')]
        rows[0]['subjects']['code']='<svg onload=alert(2)>'
        rows[0]['academic_periods']['name']='<script>alert(3)</script>'
        context,page,state=await fixture(browser,mobile=True,rows=rows)
        await visible(page)
        await expect(page.locator('.subject-name')).to_have_text('<img src=x onerror=alert(1)>')
        await expect(page.locator('.subject-code')).to_contain_text('<svg onload=alert(2)>')
        await expect(page.locator('.subject-period')).to_contain_text('<script>alert(3)</script>')
        assert await page.locator('#subjectsList img, #subjectsList svg, #subjectsList script').count()==0
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(ARTIFACTS/'subjects-mobile.png'),full_page=True)
        await finished(context,state,'subject strings remain text and mobile does not overflow')

        context,page,state=await fixture(browser,rows=[subject(i) for i in range(1,24)])
        await visible(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(20)
        await expect(page.locator('#subjectsMore')).to_be_visible()
        assert state['enrollment_requests'][0]['query'].get('offset')==['0']
        assert state['enrollment_requests'][0]['query'].get('limit')==['21']
        await page.locator('#subjectsMore').click()
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(23)
        await expect(page.locator('#subjectsMore')).to_be_hidden()
        assert state['enrollment_requests'][1]['query'].get('offset')==['20']
        assert await page.locator('.subject-name').all_text_contents()==[f'Materia de ejemplo {i}' for i in range(1,24)]
        await finished(context,state,'pagination renders 20 then remaining 3 with no duplicate sentinel')

        context,page,state=await fixture(browser,rows=[subject(i) for i in range(1,24)])
        await visible(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(20)
        state['enrollment_status']=500
        await page.locator('#subjectsMore').click()
        await expect(page.locator('#subjectsRetry')).to_be_visible()
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(20)
        before_profiles=len([u for _,u in state['requests'] if '/rest/v1/profiles' in u])
        state['enrollment_status']=200
        await page.locator('#subjectsRetry').click()
        await expect(page.locator('#subjectsRetry')).to_be_hidden()
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(20)
        assert len([u for _,u in state['requests'] if '/rest/v1/profiles' in u])>before_profiles
        assert state['enrollment_requests'][-1]['query'].get('offset')==['0']
        await finished(context,state,'pagination error retains visible cards; retry revalidates profile and restarts')

        gate=asyncio.Event()
        context,page,state=await fixture(browser,enrollment_gate=gate)
        await visible(page)
        await asyncio.wait_for(state['enrollment_started'].wait(),5)
        await expect(page.locator('#logoutButton')).to_be_enabled()
        await page.locator('#logoutButton').click()
        await expect(page).to_have_url(BASE+'/portal/index.html?estado=sesion_cerrada')
        gate.set()
        await page.wait_for_timeout(100)
        assert await page.locator('#subjectsList').count()==0
        assert await page.evaluate('localStorage.getItem("seminario-mr-auth")') is None
        await finished(context,state,'logout remains available during request; late response cannot show subjects')

        gate=asyncio.Event()
        context,page,state=await fixture(browser,enrollment_gate=gate)
        await visible(page)
        await asyncio.wait_for(state['enrollment_started'].wait(),5)
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page.locator('#panelContent')).to_be_hidden()
        gate.set()
        await page.wait_for_timeout(100)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
        await expect(page.locator('#subjectsSection')).to_be_hidden()
        state['profile']=[]
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page).to_have_url(BASE+'/portal/index.html?estado=sin_acceso')
        assert len(state['enrollment_requests'])==1
        await finished(context,state,'hidden tab clears and rejects late response; changed profile denied on return')

        context,page,state=await fixture(browser)
        await visible(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
        await page.evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted:true}))')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
        await expect(page.locator('#subjectsSection')).to_be_hidden()
        state['rows']=[subject(3)]
        await page.evaluate('window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted:true}))')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(1)
        await expect(page.locator('.subject-name')).to_have_text('Materia de ejemplo 3')
        await finished(context,state,'page cache restore rechecks access and fetches updated enrollment data')
        context,page,state=await fixture(browser)
        await visible(page)
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page.locator('#panelContent')).to_be_hidden()
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
        request_count=len(state['requests'])
        await page.evaluate('async session => { for (const event of ["TOKEN_REFRESHED", "SIGNED_IN", "USER_UPDATED"]) await window.PortalAuth.getClient().auth._notifyAllSubscribers(event, session, false); }', SESSION)
        await page.wait_for_timeout(100)
        assert len(state['requests'])==request_count
        await expect(page.locator('#panelContent')).to_be_hidden()
        await expect(page.locator('#profileName')).to_have_text('')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
        assert len(state['enrollment_requests'])==2
        await finished(context,state,'background SDK auth events cannot repopulate hidden tab; visible return revalidates')

        context,page,state=await fixture(browser,initial_hidden=True)
        await expect(page.locator('#panelContent')).to_be_hidden()
        await page.wait_for_timeout(100)
        assert not state['requests']
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(0)
        await page.evaluate('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"}); document.dispatchEvent(new Event("visibilitychange"))')
        await expect(page.locator('#subjectsList .subject-item')).to_have_count(2)
        assert len(state['enrollment_requests'])==1
        await finished(context,state,'initially hidden page defers access and subjects requests until visible')

        await browser.close()
        print(f'PASS {checks} subjects browser scenarios; real pinned SDK with simulated API, no live data modified',flush=True)
if __name__ == '__main__':
    prepare()
    try:
        asyncio.run(main())
        if os.environ.get('PORTAL_TEST_ARTIFACTS'):
            print('Screenshots: '+str(ARTIFACTS/'subjects-desktop.png')+', '+str(ARTIFACTS/'subjects-mobile.png'))
    finally:
        server.shutdown()
        server.server_close()
        TEMP.cleanup()
