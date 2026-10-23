#!/usr/bin/env python3
"""Etapas formativas: PostgreSQL desechable, sin cuentas reales ni red."""
import json, uuid
import run_kardex_local as k
h=k.h

def read(resource='students',who=h.C,student=None,period=h.T,stage='',search='',offset=0,limit=30):
    return h.actor(who,'select public.portal_formation_read('+','.join([
        h.quote(resource),h.quote(student),h.quote(period),h.quote(stage),h.quote(search),str(offset),str(limit)])+')')

def save(stage='filosofia',semester=3,revision=0,who=h.C,student=h.A,period=h.T):
    return h.actor(who,'select public.portal_formation_save('+','.join([
        h.quote(student),h.quote(period),h.quote(stage),str(semester) if semester is not None else 'null',str(revision)])+')',commit=True)

def get(sql):return json.loads(h.sql(sql).stdout)

def main():
    k.bootstrap()
    settings=get(read('settings'));h.check('three stages with 2, 6 and 8 semesters',
        [(s['code'],s['semesters']) for s in settings['stages']]==[('introductorio',2),('filosofia',6),('teologia',8)])
    for table in ['formation_stages','student_formation_periods']:
        h.test('RLS '+table,f"select relrowsecurity from pg_class where oid='public.{table}'::regclass",'t')
        h.test('private '+table,f"select has_table_privilege('authenticated','public.{table}','SELECT,INSERT,UPDATE,DELETE')",'f')
    for sig in ['portal_formation_read(text,uuid,uuid,text,text,integer,integer)','portal_formation_save(uuid,uuid,text,integer,integer)']:
        h.test('anonymous denied '+sig,"select has_function_privilege('anon',"+h.quote('public.'+sig)+",'EXECUTE')",'f')
    for sig in ['_formation_history(uuid)','_kardex_write_before_formation(text,jsonb)','_kardex_record_before_formation(uuid,uuid)','_student_personal_record_before_formation(uuid)']:
        h.test('helper private '+sig,"select has_function_privilege('authenticated',"+h.quote('public.'+sig)+",'EXECUTE')",'f')
    for who in [h.A,h.P,h.IC,h.N,h.B]:
        for resource in ['settings','students','history']:
            h.test('denied admin '+resource+who[-2:],read(resource,who=who,student=h.A),error='42501')
        h.test('denied write '+who[-2:],save(who=who),error='42501')
    h.check('new student has no invented stage',get(read('own',who=h.A))['history']==[])
    h.test('student cannot read another trajectory',read('own',who=h.A,student=h.B),error='42501')
    for stage,semester in [('introductorio',3),('filosofia',7),('teologia',9),('teologia',0),('inventada',1),('teologia',None)]:
        h.test('reject semester '+str((stage,semester)),save(stage,semester),error='22023')
    h.test('cannot assign a professor',save(student=h.P),error='22023')
    h.test('unknown period rejected',save(period=str(uuid.uuid4())),error='22023')
    h.sql(save());h.check('stage stored',get(read('own',who=h.A))['history'][0]['semester']==3)
    h.test('stale updates rejected',save('filosofia',4),error='PT409')
    h.sql(save('introductorio',2,period=k.T2));history=get(read('history',student=h.A))['history']
    h.check('each period retains its own stage',len(history)==2 and history[0]['stage_code']=='introductorio' and history[1]['stage_code']=='filosofia')
    h.check('stage filter',len(get(read(stage='filosofia'))['items'])==1)
    h.check('empty stage filter',len(get(read(stage='teologia'))['items'])==0)
    for off,lim in [(-1,30),(0,0),(0,101)]:h.test('bounded lookup',read(offset=off,limit=lim),error='22023')
    h.test('bad stage filter',read(stage='inventada'),error='22023')
    h.test('unknown period filter',read(period=str(uuid.uuid4())),error='22023')
    personal=get(h.actor(h.A,"select public.portal_student_record_read()"))
    h.check('school record uses same trajectory',personal['school']['formation_history']==history)
    k.save('student_save',{'student_id':h.A,'student_number':'MR-ETAPAS','revision':0})
    report=k.read('record');h.check('Kardex links both periods',report['formation_history']==history)
    request=str(uuid.uuid4());h.sql(k.issue_query(report['token'],req=request));issued=k.read('issue',issue=request)
    h.sql(save('filosofia',4,1));h.check('stage changes invalidate Kardex preview',k.read('record')['token']!=report['token'])
    h.check('issued copy is not changed',k.read('issue',issue=request)==issued)
    h.check('grades and enrollments unchanged',k.read('record')['stats']['average']==76.67 and k.read('record')['stats']['enrollments']==4)
    h.test('same assignment does not add audit twice',save('filosofia',4,2))
    h.test('revision remains stable on identical save',f"select revision from public.student_formation_periods where student_id='{h.A}' and period_id='{h.T}'",2)
    program={'id':k.PROGRAM,'revision':0,'name':'Filosofía','plan_name':'Plan de prueba','display_scale':'100','repeat_policy':'all','weighted':False,'formation_stage':'filosofia'}
    k.save('program_save',program);h.check('program linked to formation stage',k.read('programs')['items'][0]['formation_stage']=='filosofia')
    for term in ['7','0','Segundo','',None,'1.5']:
        h.test('invalid plan semester '+str(term),k.query('curriculum_save',{'program_id':k.PROGRAM,'items':[
            {'subject_id':h.S,'included':True,'credits':3,'hours':30,'term':term,'revision':0}]}),error='22023')
    k.save('curriculum_save',{'program_id':k.PROGRAM,'items':[{'subject_id':h.S,'included':True,'credits':3,'hours':30,'term':'6','revision':0}]})
    h.test('shorter stage cannot contain semester six',k.query('program_save',{**program,'revision':1,'formation_stage':'introductorio'}),error='22023')
    h.check('failed program update is atomic',k.read('programs')['items'][0]['revision']==1)
    k.save('program_save',{key:value for key,value in {**program,'revision':1}.items() if key!='formation_stage'})
    h.check('older clients preserve stage',k.read('programs')['items'][0]['formation_stage']=='filosofia')
    h.sql(f"update public.profiles set active=false where id='{h.A}'")
    h.test('revoked student cannot read own trajectory',read('own',who=h.A),error='42501')
    h.check('Control retains historical trajectory for inactive student',len(get(read('history',student=h.A))['history'])==2)
    h.sql(f"update public.profiles set active=false where id='{h.C}'")
    h.test('revoked Control cannot save',save('teologia',8,2),error='42501')
    print(f'PASS {h.checks} formation SQL assertions; disposable fixtures only',flush=True)

if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
