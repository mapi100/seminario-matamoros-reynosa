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

async def fixture(browser, *, mobile=False, session=True, profile=None, rows=None, enrollment_status=200, enrollment_gate=None, start='panel.html', user_status=200, initial_hidden=False, grades=None, grade_status=200, grade_gate=None, grade_unfiltered=False, teaching=None, teaching_status=200, teaching_gate=None, rosters=None, roster_status=200, roster_gate=None, capture=None, catalog=None):
    state={'profile':copy.deepcopy(DEFAULT_PROFILE) if profile is None else profile,'user_status':user_status,'rows':copy.deepcopy(rows) if rows is not None else [subject(1),subject(2)],'enrollment_status':enrollment_status,'enrollment_gate':enrollment_gate,'enrollment_started':asyncio.Event(),'enrollment_requests':[],'requests':[],'errors':[],'route_errors':[], 'grades':copy.deepcopy(grades) if grades is not None else [], 'grade_status':grade_status, 'grade_gate':grade_gate, 'grade_started':asyncio.Event(), 'grade_requests':[], 'grade_unfiltered':grade_unfiltered}
    state.update({'teaching':copy.deepcopy(teaching) if teaching is not None else [], 'teaching_status':teaching_status, 'teaching_gate':teaching_gate, 'teaching_started':asyncio.Event(), 'teaching_requests':[], 'rosters':copy.deepcopy(rosters) if rosters is not None else {}, 'roster_status':roster_status, 'roster_gate':roster_gate, 'roster_started':asyncio.Event(), 'roster_requests':[]})
    capture = capture or {}
    state['capture_records'] = copy.deepcopy(capture.get('records', {}))
    state['capture_calls'] = []
    state['capture_audit'] = []
    for action in ['get', 'save', 'publish']:
        state['capture_' + action + '_status'] = capture.get(action + '_status', 200)
        state['capture_' + action + '_gate'] = capture.get(action + '_gate')
        state['capture_' + action + '_started'] = asyncio.Event()
        state['capture_' + action + '_requests'] = []
    state['capture_get_override'] = capture.get('get_override')
    state['capture_save_override'] = capture.get('save_override')
    state['capture_publish_override'] = capture.get('publish_override')
    state['capture_commit_then_abort'] = capture.get('commit_then_abort', False)
    catalog = catalog or {}
    state['catalog_calls'] = []
    state['catalog_audit'] = []
    for kind in ['subjects', 'periods']:
        state['catalog_' + kind] = copy.deepcopy(catalog.get(kind, []))
        state['catalog_' + kind + '_status'] = catalog.get(kind + '_status', 200)
        state['catalog_' + kind + '_gate'] = catalog.get(kind + '_gate')
        state['catalog_' + kind + '_started'] = asyncio.Event()
        state['catalog_' + kind + '_requests'] = []
        state['catalog_' + kind + '_create_status'] = catalog.get(kind + '_create_status', 200)
        state['catalog_' + kind + '_create_gate'] = catalog.get(kind + '_create_gate')
        state['catalog_' + kind + '_create_started'] = asyncio.Event()
        state['catalog_' + kind + '_create_requests'] = []
        state['catalog_' + kind + '_create_override'] = catalog.get(kind + '_create_override')
        state['catalog_' + kind + '_commit_then_abort'] = catalog.get(kind + '_commit_then_abort', False)
    context=await browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':900})
    if initial_hidden:
        await context.add_init_script('Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"})')
    page=await context.new_page()
    page.on('pageerror',lambda err:state['errors'].append(str(err)))
    await context.route('https://cdn.jsdelivr.net/**',lambda route:route.fulfill(status=200,body=SDK,headers={'Content-Type':'application/javascript','Access-Control-Allow-Origin':'*'}))
    config='window.PORTAL_SUPABASE_CONFIG = Object.freeze('+json.dumps({'url':API,'publishableKey':'sb_publishable_fixture_only'})+');'
    await context.route('**/supabase-config.js*',lambda route:route.fulfill(status=200,body=config,content_type='application/javascript'))
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
            elif path in ['/rest/v1/subjects', '/rest/v1/academic_periods']:
                assert request.method == 'GET', request.method
                kind = 'subjects' if path.endswith('/subjects') else 'periods'
                expected_select = 'id,code,name,created_at' if kind == 'subjects' else 'id,name,starts_on,ends_on,created_at'
                expected_order = 'code.asc,id.asc' if kind == 'subjects' else 'starts_on.desc,id.asc'
                assert query.get('select') == [expected_select], query
                assert query.get('order') == [expected_order], query
                assert query.get('limit') == ['21'], query
                state['catalog_' + kind + '_requests'].append(copy.deepcopy(query))
                state['catalog_calls'].append(('read_' + kind, copy.deepcopy(query)))
                state['catalog_' + kind + '_started'].set()
                status = state['catalog_' + kind + '_status']
                rows = copy.deepcopy(state['catalog_' + kind])
                if isinstance(rows, list):
                    rows.sort(key=lambda row: row.get('id', ''))
                    rows.sort(key=lambda row: row.get('code', '') if kind == 'subjects' else row.get('starts_on', ''), reverse=kind == 'periods')
                gate = state['catalog_' + kind + '_gate']
                if gate:
                    await gate.wait()
                offset = int(query.get('offset', ['0'])[0])
                data = rows[offset:offset + 21] if isinstance(rows, list) else rows
                if status != 200:
                    data = {'code': '42501' if status == 403 else '42P01', 'message': 'Fixture catalog list error'}
            elif path in ['/rest/v1/rpc/create_subject', '/rest/v1/rpc/create_academic_period']:
                assert request.method == 'POST', request.method
                kind = 'subjects' if path.endswith('/create_subject') else 'periods'
                args = request.post_data_json
                expected = {'p_code', 'p_name'} if kind == 'subjects' else {'p_name', 'p_starts_on', 'p_ends_on'}
                assert set(args) == expected, args
                assert all(isinstance(value, str) for value in args.values()), args
                state['catalog_' + kind + '_create_requests'].append(copy.deepcopy(args))
                state['catalog_calls'].append(('create_' + kind, copy.deepcopy(args)))
                state['catalog_' + kind + '_create_started'].set()
                status = state['catalog_' + kind + '_create_status']
                profile = state['profile']
                if not profile or profile.get('role') != 'control_escolar' or profile.get('active') is not True:
                    status = 403
                rows = state['catalog_' + kind]
                canonical = args.get('p_code', '').strip().upper() if kind == 'subjects' else args['p_name'].strip()
                if status == 200:
                    duplicate = any((row.get('code', '').strip().casefold() if kind == 'subjects' else row.get('name', '').strip().casefold()) == canonical.casefold() for row in rows)
                    if duplicate:
                        status = 409
                if status == 200:
                    number = len(rows) + 100
                    record = {'id': f'55555555-5555-4555-8555-{number:012d}',
                              'name': args['p_name'].strip(), 'created_at': '2026-10-21T12:00:00+00:00'}
                    if kind == 'subjects':
                        record['code'] = canonical
                    else:
                        record['starts_on'] = args['p_starts_on']
                        record['ends_on'] = args['p_ends_on']
                    rows.append(copy.deepcopy(record))
                    state['catalog_audit'].append((kind, copy.deepcopy(record)))
                    data = [record]
                    override = state['catalog_' + kind + '_create_override']
                    if override is not None:
                        data = copy.deepcopy(override)
                else:
                    data = {'code': 'PT409' if status == 409 else '42501' if status == 403 else 'XX000', 'message': 'Ya existe un registro con ese código o nombre' if status == 409 else 'Fixture catalog create error'}
                gate = state['catalog_' + kind + '_create_gate']
                if gate:
                    await gate.wait()
                if state['catalog_' + kind + '_commit_then_abort'] and status == 200:
                    return await route.abort()
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
            elif path=='/rest/v1/enrollment_grades':
                assert request.method=='GET',request.method
                assert query.get('select')==['enrollment_id,score'],query
                filters=query.get('enrollment_id',[])
                assert len(filters)==1 and filters[0].startswith('in.(') and filters[0].endswith(')'),query
                ids=filters[0][4:-1].split(',')
                assert ids and all(ids) and len(ids)==len(set(ids)),ids
                state['grade_requests'].append({'query':query,'ids':ids})
                state['grade_started'].set()
                status=state['grade_status']
                rows=copy.deepcopy(state['grades'])
                if not state['grade_unfiltered']:
                    rows=[row for row in rows if row.get('enrollment_id') in ids]
                gate=state['grade_gate']
                if gate: await gate.wait()
                data=rows if status==200 else {'code':'42501' if status==403 else '42P01','message':'Fixture grades API error'}
            elif path=='/rest/v1/teaching_assignments':
                assert request.method=='GET',request.method
                assert query.get('select')==['id,subjects(code,name),academic_periods(name,starts_on,ends_on)'],query
                state['teaching_requests'].append({'query':query,'headers':request.headers})
                state['teaching_started'].set()
                status=state['teaching_status']
                rows=copy.deepcopy(state['teaching'])
                gate=state['teaching_gate']
                if gate: await gate.wait()
                offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',[str(len(rows))])[0])
                data=rows[offset:offset+limit] if status==200 else {'code':'42501' if status==403 else '42P01','message':'Fixture teaching API error'}
            elif path=='/rest/v1/rpc/get_teaching_roster':
                assert request.method=='POST',request.method
                args=request.post_data_json
                assert set(args)=={'p_assignment_id','p_offset','p_limit'},args
                assert isinstance(args['p_offset'],int) and args['p_offset']>=0,args
                assert args['p_limit']==21,args
                state['roster_requests'].append(args)
                state['roster_started'].set()
                status=state['roster_status']
                rows=copy.deepcopy(state['rosters'].get(args['p_assignment_id'],[]))
                gate=state['roster_gate']
                if gate: await gate.wait()
                if status==200:
                    data=rows[args['p_offset']:args['p_offset']+args['p_limit']] if isinstance(rows,list) else rows
                else:
                    data={'code':'42501' if status==403 else 'PGRST202','message':'Fixture roster API error'}
            elif path in ['/rest/v1/rpc/get_teaching_grade', '/rest/v1/rpc/save_teaching_grade', '/rest/v1/rpc/publish_teaching_grade']:
                assert request.method == 'POST', request.method
                action = path.rsplit('/', 1)[-1].split('_', 1)[0]
                args = request.post_data_json
                expected_args = {'p_assignment_id', 'p_enrollment_id'}
                if action in ['save', 'publish']:
                    expected_args.add('p_expected_revision')
                if action == 'save':
                    expected_args.add('p_score')
                assert set(args) == expected_args, args
                state['capture_calls'].append((action, copy.deepcopy(args)))
                state['capture_' + action + '_requests'].append(copy.deepcopy(args))
                state['capture_' + action + '_started'].set()
                enrollment_id = args['p_enrollment_id']
                current = state['capture_records'].setdefault(enrollment_id, {
                    'enrollment_id': enrollment_id, 'published_score': None,
                    'draft_score': None, 'revision': 0, 'has_unpublished_changes': False
                })
                status = state['capture_' + action + '_status']
                if action in ['save', 'publish'] and status == 200:
                    if args['p_expected_revision'] != current['revision']:
                        status = 409
                    elif action == 'save':
                        assert isinstance(args['p_score'], (int, float)), args
                        assert 0 <= args['p_score'] <= 100, args
                        current['draft_score'] = args['p_score']
                        current['revision'] += 1
                        current['has_unpublished_changes'] = True
                        state['capture_audit'].append(('save_draft', enrollment_id, args['p_score']))
                    elif not current['has_unpublished_changes'] or current['revision'] < 1:
                        status = 400
                    else:
                        current['published_score'] = current['draft_score']
                        current['revision'] += 1
                        current['has_unpublished_changes'] = False
                        state['capture_audit'].append(('publish', enrollment_id, current['published_score']))
                data = copy.deepcopy([current])
                override = state['capture_' + action + '_override']
                if override is not None:
                    data = copy.deepcopy(override)
                if status != 200:
                    data = {'code': 'PT409' if status == 409 else '42501' if status == 403 else 'PGRST202' if status == 404 else 'XX000', 'message': 'Fixture grade capture error'}
                gate = state['capture_' + action + '_gate']
                if gate:
                    await gate.wait()
                if action in ['save', 'publish'] and state['capture_commit_then_abort']:
                    return await route.abort()
            elif path=='/rest/v1/rpc/portal_admin_cleanup_files':
                # New deletion banner checks resumable cleanup without live Storage.
                status=200; data={'paths':[], 'remaining':0}
            elif path=='/rest/v1/rpc/portal_learning_read':
                # The new home widgets use a read-only RPC. Legacy scenarios
                # keep an empty LMS fixture; dedicated tests cover its payloads.
                assert request.method == 'POST', request.method
                assert request.post_data_json['p_resource'] == 'dashboard'
                status=200
                data={'courses':[], 'announcements':[], 'work':[], 'events':[],
                      'institutional_announcements':[], 'has_more_courses':False}
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
    if start == 'panel.html' and state['profile'] and state['profile'].get('role') == 'control_escolar':
        start += '#catalogos-academicos'
    await page.goto(BASE+'/portal/'+start,wait_until='domcontentloaded')
    return context,page,state

async def visible(page):
    await expect(page.locator('#panelContent')).to_be_visible()
    await expect(page.locator('#subjectsSection')).to_be_visible()

async def finished(context,state,label):
    global checks
    assert not state['errors'],state['errors']
    assert not state['route_errors'],state['route_errors']
    assert all(method in ['GET','OPTIONS'] or '/auth/v1/' in url
               # Inicio del campus: lectura LMS y comprobación de limpieza de
               # archivos ya autorizada; esta fixture siempre tiene cola vacía.
               or (method == 'POST' and url.endswith(('/rpc/portal_learning_read','/rpc/portal_admin_cleanup_files')))
               for method,url in state['requests']),state['requests']
    checks+=1
    print('PASS '+label,flush=True)
    if state['enrollment_gate']: state['enrollment_gate'].set()
    if state['grade_gate']: state['grade_gate'].set()
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
