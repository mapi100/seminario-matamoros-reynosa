// Node 24 executes the dependency-free Edge handler; all network calls are mocked.
import assert from 'node:assert/strict';
import {createHandler} from '../supabase/functions/invite-person/handler.ts';
const actor='10000000-0000-4000-8000-000000000001',created='10000000-0000-4000-8000-000000000002';
const config={PORTAL_ORIGIN:'https://seminariomr.org',SUPABASE_URL:'https://fixture.supabase.co',SUPABASE_SERVICE_ROLE_KEY:'fixture-server-only-secret',PORTAL_INVITES_ENABLED:'true'};
const valid={email:'new@example.org',full_name:'Nueva Persona',role:'professor',request_id:'20000000-0000-4000-8000-000000000001'};
let checks=0;
async function scenario(name,options={},verify=()=>{}){
 const calls=[];const handler=createHandler({get:key=>({...config,...options.env})[key]},async(url,args)=>{
   const path=new URL(url).pathname;const body=args.body?JSON.parse(args.body):undefined;calls.push({path,args,body});
   let status=200,data;
   if(path==='/auth/v1/user'){status=options.authStatus||200;data={id:actor,user_metadata:{role:'control_escolar'}};}
   else if(path==='/rest/v1/profiles')data=options.profiles||[{role:'control_escolar',active:true}];
   else if(path.endsWith('/portal_prepare_invite')){status=options.prepareStatus||200;data={state:options.state||'claimed',code:options.prepareCode};}
   else if(path==='/auth/v1/invite'){status=options.mailStatus||200;data=status===200?{id:created}:{error:'SMTP fixture error'};assert.equal(new URL(url).searchParams.get('redirect_to'),'https://seminariomr.org/portal/activar.html');assert.deepEqual(body,{email:valid.email});}
   else if(path.endsWith('/portal_finish_invite')){if(options.finishTimeout)throw new Error('Simulated timeout after possible commit');status=options.finishStatus||200;data={sent:status===200,code:options.finishCode};}
   else if(path.includes('/auth/v1/admin/users/'))data={};
   else if(path.endsWith('/portal_fail_invite'))data=null;
   else throw new Error('Unexpected request '+path);
   return new Response(data===null?'null':JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
 });
 const request=new Request('https://fixture.supabase.co/functions/v1/invite-person',{method:options.method||'POST',headers:{Origin:options.origin||config.PORTAL_ORIGIN,Authorization:options.authorization||'Bearer fixture.jwt.token','Content-Type':'application/json'},...(['GET','OPTIONS'].includes(options.method)?{}:{body:options.raw||JSON.stringify(options.body||valid)})});
 const response=await handler(request);const content=await response.json();
 assert.equal(response.headers.get('Cache-Control'),'no-store');assert(!JSON.stringify(content).includes(config.SUPABASE_SERVICE_ROLE_KEY));
 await verify(response,content,calls);checks++;console.log('PASS '+name);
}
await scenario('successful invite uses verified identity and no client-selected redirect',{},(r,b,c)=>{assert.equal(r.status,200);assert.equal(b.sent,true);assert.equal(c.find(x=>x.path.endsWith('portal_prepare_invite')).body.p_actor,actor);assert(c.every(x=>x.args.headers.apikey===config.SUPABASE_SERVICE_ROLE_KEY));});
await scenario('cross-origin denied before API calls',{origin:'https://attacker.invalid'},(r,b,c)=>{assert.equal(r.status,403);assert.equal(c.length,0);});
await scenario('preflight requires no access token',{method:'OPTIONS'},(r,b,c)=>{assert.equal(r.status,200);assert.equal(c.length,0);});
await scenario('GET never mutates',{method:'GET'},(r,b,c)=>{assert.equal(r.status,405);assert.equal(c.length,0);});
await scenario('invalid token syntax rejected',{authorization:'not-a-bearer'},(r,b,c)=>{assert.equal(r.status,401);assert.equal(c.length,0);});
await scenario('Auth rejects forged JWT',{authStatus:401},(r,b,c)=>{assert.equal(r.status,401);assert.equal(c.length,1);});
for(const p of [[{role:'student',active:true}],[{role:'professor',active:true}],[{role:'control_escolar',active:false}],[]])await scenario('database role overrides forged user metadata '+JSON.stringify(p),{profiles:p},(r,b,c)=>{assert.equal(r.status,403);assert.equal(c.length,2);});
await scenario('mail explicitly gated until SMTP setup',{env:{PORTAL_INVITES_ENABLED:'false'}},(r,b,c)=>{assert.equal(r.status,503);assert.equal(c.length,2);});
await scenario('request cannot override redirect or actor',{body:{...valid,redirect_to:'https://attacker.invalid'}},(r,b,c)=>{assert.equal(r.status,400);assert.equal(c.length,2);});
await scenario('unrecognized role rejected',{body:{...valid,role:'owner'}},(r,b,c)=>assert.equal(r.status,400));
await scenario('invalid JSON rejected',{raw:'{'},(r,b,c)=>assert.equal(r.status,400));
await scenario('oversized body rejected',{raw:'x'.repeat(5000)},(r,b,c)=>assert.equal(r.status,413));
await scenario('busy claim cannot send twice',{state:'busy'},(r,b,c)=>{assert.equal(r.status,409);assert(!c.some(x=>x.path==='/auth/v1/invite'));});
await scenario('completed request idempotent',{state:'sent'},(r,b,c)=>{assert.equal(b.sent,true);assert(!c.some(x=>x.path==='/auth/v1/invite'));});
await scenario('rate limited by database',{prepareStatus:429,prepareCode:'PT429'},(r,b,c)=>assert.equal(r.status,429));
await scenario('SMTP uncertainty cannot enable account',{mailStatus:500},(r,b,c)=>{assert.equal(r.status,502);assert.equal(c.at(-1).body.p_state,'uncertain');assert(!c.some(x=>x.path.endsWith('portal_finish_invite')));});
await scenario('privilege revoked before profile creation compensates new auth identity',{finishStatus:403,finishCode:'42501'},(r,b,c)=>{assert.equal(r.status,409);assert(c.some(x=>x.path==='/auth/v1/admin/users/'+created&&x.args.method==='DELETE'));assert.equal(c.at(-1).body.p_state,'failed');});
await scenario('network uncertainty never deletes a possibly committed user',{finishTimeout:true},(r,b,c)=>{assert.equal(r.status,503);assert(!c.some(x=>x.args.method==='DELETE'));assert.equal(c.at(-1).body.p_state,'uncertain');});
await scenario('upstream 5xx never deletes a possibly committed user',{finishStatus:502},(r,b,c)=>{assert.equal(r.status,503);assert(!c.some(x=>x.args.method==='DELETE'));});
console.log(`PASS ${checks} Edge Function scenarios; no live Auth or email requests`);
