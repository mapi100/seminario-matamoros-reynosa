#!/usr/bin/env python3
"""Expediente personal: PostgreSQL desechable, identidades ficticias y sin red."""
import copy,json,uuid
from datetime import date,timedelta
import run_kardex_local as k
h=k.h


def read(who=h.A,student=None,resource='record',**kw):
    return json.loads(h.sql(read_query(who,student,resource,**kw)).stdout)

def read_query(who=h.A,student=None,resource='record',search='',offset=0,limit=30):
    return h.actor(who,'select public.portal_student_record_read('+','.join([h.quote(resource),h.quote(student),h.quote(search),str(offset),str(limit)])+')')

def query(data,who=h.A,student=None,token=None):
    token=token if token is not None else read(who,student)['token']
    return h.actor(who,'select public.portal_student_record_save('+','.join([h.quote(student),h.quote(token),h.quote(json.dumps(data))+'::jsonb'])+')',commit=True)

def save(data,who=h.A,student=None,token=None):return json.loads(h.sql(query(data,who,student,token)).stdout)

def review_query(who=h.C,student=h.A,token=None):
    token=token if token is not None else read(who,student)['token']
    return h.actor(who,'select public.portal_student_record_review('+h.quote(student)+','+h.quote(token)+')',commit=True)


def main():
    k.bootstrap()
    sigs=['portal_student_record_read(text,uuid,text,integer,integer)','portal_student_record_save(uuid,text,jsonb)','portal_student_record_review(uuid,text)']
    for sig in sigs:h.test('anonymous cannot execute '+sig,"select has_function_privilege('anon',"+h.quote('public.'+sig)+",'EXECUTE')",'f')
    for sig in ['_student_record_target(uuid)','_student_record_age(date,date)','_student_personal_record(uuid)']:
        h.test('helper is private '+sig,"select has_function_privilege('authenticated',"+h.quote('public.'+sig)+",'EXECUTE')",'f')
    h.test('personal table RLS',"select relrowsecurity from pg_class where oid='public.student_personal_records'::regclass",'t')
    h.test('table cannot be accessed directly',"select has_table_privilege('authenticated','public.student_personal_records','SELECT,INSERT,UPDATE,DELETE')",'f')
    h.test('profiles still cannot be updated directly',h.actor(h.A,f"update public.profiles set role='control_escolar' where id='{h.A}'"),error='42501')
    for who in [h.P,h.IC,h.N,h.B]:
        h.test('unauthorized own record '+who[-2:],read_query(who),error='42501')
        h.test('unauthorized records list '+who[-2:],read_query(who,resource='students'),error='42501')
        h.test('unauthorized write '+who[-2:],query({},who,token='fake'),error='42501')
        h.test('unauthorized review '+who[-2:],review_query(who,token='fake'),error='42501')
    h.test('student cannot read another active user',read_query(h.A,h.P),error='42501')
    h.test('student cannot read another student',read_query(h.A,h.B),error='42501')
    h.test('student cannot list personal records',read_query(h.A,resource='students'),error='42501')
    h.test('student cannot edit another student',query({},h.A,h.B,token='fake'),error='42501')
    h.test('student cannot approve own data',review_query(h.A,token='fake'),error='42501')
    first=read();h.check('self read resolves authenticated id',first['student']['id']==h.A and not first['can_review'])
    h.check('new record has no invented personal data',first['details']=={} and first['identity']['curp'] is None and first['identity']['age'] is None)
    h.check('age is derived and missing data are listed',first['completion']['completed']==0 and first['completion']['total']==9)
    h.check('existing enrollments linked automatically',first['school']['enrollments']==4)
    h.sql(f"update public.profiles set full_name={h.quote(first['student']['full_name'])} where id='{h.B}'")
    h.check('same-name empty records have distinct student-bound tokens',read(h.C,h.B)['token']!=first['token'])
    h.test('Control cannot reuse another student preview token',query({'full_name':'Nombre mixto','curp':'','birth_date':'','details':{}},h.C,h.B,first['token']),error='PT409')
    h.sql(f"update public.profiles set full_name='Seminarista Beta' where id='{h.B}'")
    data={'full_name':'Seminarista de prueba actualizado','curp':'XEXX040127HTSXXX01','birth_date':'2004-01-27','details':{
        'birth_country':'México','birth_state':'Tamaulipas','birth_city':'Matamoros','nationality':'Mexicana','registered_sex':'H',
        'phone':'+52 868 100 0000','contact_email':'alumno@example.invalid','street':'Calle de prueba','exterior_number':'10',
        'neighborhood':'Colonia de prueba','postal_code':'87300','city':'Matamoros','state':'Tamaulipas','country':'México',
        'emergency_name':'Contacto de prueba','emergency_relationship':'Familiar','emergency_phone':'+52 868 200 0000',
        'mother_name':'Madre de prueba','father_name':'Padre de prueba','home_diocese':'Diócesis de prueba','home_parish':'Parroquia de prueba',
        'previous_school':'Escuela de prueba','previous_level':'Bachillerato','previous_qualification':'Certificado','previous_graduation_year':'2024'}}
    saved=save(data,token=first['token'])
    h.check('student can save own personal data',saved['saved'] and saved['details']['street']==data['details']['street'])
    h.check('age computed in Matamoros, never accepted from client',saved['identity']['age']>=22 and saved['identity']['age_as_of'])
    h.check('basic suggested data completion',saved['completion']['completed']==9 and not saved['completion']['missing'])
    h.test('shared name updated in profile',f"select full_name from public.profiles where id='{h.A}'",data['full_name'])
    h.test('shared CURP and birth in kardex',f"select curp||'|'||birth_date from public.kardex_students where student_id='{h.A}'",data['curp']+'|'+data['birth_date'])
    kr=k.read('record');h.check('kardex reads new identity immediately',kr['student']['full_name']==data['full_name'] and kr['student']['curp']==data['curp'])
    h.sql(f"insert into public.kardex_students(student_id,curp,birth_date) values('{h.B}','XEXX050101HTSXXX02','2005-01-01')")
    h.test('duplicate CURP rejected atomically',query({**data,'full_name':'Nombre que no debe guardarse','curp':'XEXX050101HTSXXX02','birth_date':'2005-01-01'}),error='PT409')
    h.test('failed duplicate preserves shared name',f"select full_name from public.profiles where id='{h.A}'",data['full_name'])
    h.check('failed duplicate preserves all original fields',read()['token']==saved['token'])
    h.test('roles not changed by self-service',f"select role from public.profiles where id='{h.A}'",'student')
    h.test('stale form cannot overwrite newer data',query(data,token=first['token']),error='PT409')
    h.test('no full PII in generic audit',"select count(*) from public.management_events where action='student_record_saved' and details::text like '%XEXX%'",0)
    again=save(data);h.check('unchanged save does not create extra revisions',again['revision']==saved['revision'])
    for key in ['role','active','student_number','entered_on','completed_on','age','grades','email','reviewed_by']:
        h.test('reject privileged field '+key,query({**data,key:'forged'}),error='22023')
    for details in [{'role':'control_escolar'},{'phone':123},{'phone':{'x':'y'}},{'phone':'123'},{'phone':'text only'},{'phone':'1'*21},
                    {'contact_email':'a @bad.com'},{'registered_sex':'inventado'},{'previous_graduation_year':'20ab'},{'previous_graduation_year':'9999'},
                    {'street':'x'*181},{'emergency_name':'Nombre\nincorrecto'}]:
        h.test('invalid field rejected '+str(details)[:45],query({**data,'details':details}),error='22023')
    for changes in [{'birth_date':'infinity'},{'birth_date':'2026-02-30'},{'birth_date':'9999-01-01'},{'birth_date':'1800-01-01'},
                    {'curp':'invalid'},{'birth_date':'2004-02-27'},{'full_name':'\u00a0'},{'full_name':'a'*161}]:
        h.test('invalid identity rejected '+str(changes)[:45],query({**data,**changes}),error='22023')
    h.check('failed saves did not partially change record',read()['token']==again['token'])
    h.test('age before birthday',"select public._student_record_age('2004-10-23','2026-10-22')",21)
    h.test('age on birthday',"select public._student_record_age('2004-10-22','2026-10-22')",22)
    h.test('age after birthday',"select public._student_record_age('2004-10-21','2026-10-22')",22)
    h.test('leap-day before anniversary',"select public._student_record_age('2004-02-29','2026-02-28')",21)
    h.test('leap-day after anniversary',"select public._student_record_age('2004-02-29','2026-03-01')",22)
    h.check('Control can read inactive former student',read(h.C,h.B)['student']['active'] is False)
    listed=read(h.C,resource='students');h.check('Control lookup includes active and inactive',len(listed['items'])==2)
    h.check('Control search by CURP',len(read(h.C,resource='students',search='xexx040127')['items'])==1)
    for off,lim in [(-1,30),(0,0),(0,101)]:h.test('bounded lookup '+str((off,lim)),read_query(h.C,resource='students',offset=off,limit=lim),error='22023')
    # School-owned fields survive all personal edits.
    kd=k.read('record')['student'];k.save('student_save',{'student_id':h.A,'student_number':'MR-001','curp':data['curp'],'birth_date':data['birth_date'],'entered_on':'2025-01-01','completed_on':'','revision':kd['revision']})
    changed=copy.deepcopy(data);changed['details']['phone']='+52 868 300 0000';updated=save(changed)
    h.check('self save preserves assigned matricula and entry date',updated['school']['student_number']=='MR-001' and updated['school']['entered_on']=='2025-01-01')
    reviewed=json.loads(h.sql(review_query()).stdout);h.check('Control can mark current data as reviewed',reviewed['review']['reviewed'])
    h.check('review identity visible to owner',read()['review']['reviewer']=='Control Escolar')
    h.test('review idempotent',review_query())
    h.test('no duplicate review event',"select count(*) from public.management_events where action='student_record_reviewed'",1)
    same=save(changed);h.check('unchanged self save retains review',same['review']['reviewed'])
    changed['details']['emergency_phone']='+52 868 400 0000';pending=save(changed)
    h.check('changed personal data return to pending review',not pending['review']['reviewed'])
    h.test('stale review cannot approve changed data',review_query(token=reviewed['token']),error='PT409')
    h.sql(review_query());h.sql(f"update public.profiles set full_name='Nombre corregido por Control' where id='{h.A}'")
    h.check('external name changes invalidate personal review',not read()['review']['reviewed'])
    # Mark and then change shared CURP/birth through existing Kardex API.
    h.sql(review_query());current=k.read('record')['student'];k.save('student_save',{'student_id':h.A,'student_number':'MR-001','curp':'XEXX040128HTSXXX01','birth_date':'2004-01-28','entered_on':'2025-01-01','completed_on':'','revision':current['revision']})
    h.check('Kardex identity edit reaches personal form and invalidates review',read()['identity']['birth_date']=='2004-01-28' and not read()['review']['reviewed'])
    h.test('old personal form cannot overwrite Kardex edit',query(changed,token=pending['token']),error='PT409')
    # Keep issued copies fixed while later personal updates reach the live Kardex.
    report=k.read('record');req=str(uuid.uuid4());issued=json.loads(h.sql(k.issue_query(report['token'],req=req)).stdout);original=k.read('issue',issue=issued['id'])
    next_data={'full_name':'Nombre posterior','curp':'XEXX040128HTSXXX01','birth_date':'2004-01-28','details':{'phone':'8681000000'}};save(next_data)
    h.check('issued Kardex is unchanged after self-service update',k.read('issue',issue=issued['id'])==original)
    h.check('live Kardex uses latest full name',k.read('record')['student']['full_name']=='Nombre posterior')
    partial=save({'full_name':'Nombre posterior','curp':'','birth_date':'','details':{}})
    h.check('partial data can be saved without fabricating missing fields',partial['identity']['curp'] is None and partial['identity']['birth_date'] is None and partial['completion']['completed']==0)
    # No user may read the form after their profile is revoked.
    h.sql(f"update public.profiles set active=false where id='{h.A}'")
    h.test('revoked student cannot read own data',read_query(),error='42501')
    h.test('revoked student cannot save own data',query(next_data,token=partial['token']),error='42501')
    h.check('Control can still consult inactive historical record',read(h.C,h.A)['student']['active'] is False)
    h.sql(f"update public.profiles set active=false where id='{h.C}'")
    h.test('revoked Control cannot read others',read_query(h.C,h.A),error='42501')
    print(f'PASS {h.checks} personal-record SQL assertions; disposable fixtures only',flush=True)

if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
