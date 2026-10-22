#!/usr/bin/env python3
"""Kardex en PostgreSQL desechable sin red. Nunca usa datos reales."""
import json,time,uuid,os,subprocess
from pathlib import Path
import run_learning_local as h

PROGRAM=h.uid(80);PROGRAM2=h.uid(81);T2=h.uid(31);T3=h.uid(32);E2=h.uid(42);E3=h.uid(43);E4=h.uid(44)

def read(resource,who=h.C,student=h.A,program=None,issue=None,**kwargs):
    args=[h.quote(resource),h.quote(student),h.quote(program),h.quote(kwargs.get('search','')),str(kwargs.get('offset',0)),str(kwargs.get('limit',30)),h.quote(issue)]
    return json.loads(h.sql(h.actor(who,'select public.portal_kardex_read('+','.join(args)+')')).stdout)

def query(action,data,who=h.C):return h.actor(who,'select public.portal_kardex_write('+h.quote(action)+','+h.quote(json.dumps(data))+'::jsonb)',commit=True)
def save(action,data,who=h.C):return json.loads(h.sql(query(action,data,who)).stdout)
def issue_query(token,kind='partial',req=None,who=h.C,program=None,notes=''):
    req=req or str(uuid.uuid4());return h.actor(who,'select public.portal_kardex_issue('+','.join(map(h.quote,[h.A,program,kind,token,req,notes]))+')',commit=True)

def bootstrap():
    h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
    for _ in range(100):
        logs=h.run('docker','logs',h.NAME,check=False)
        if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
        time.sleep(.2)
    else:raise AssertionError('Postgres did not start')
    h.sql(h.AUTH);h.sql(h.STORAGE)
    for p in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):h.sql(p.read_text())
    for who,name,role,active in [(h.A,'Seminarista Alfa','student',True),(h.B,'Seminarista Beta','student',False),(h.P,'Profesor','professor',True),(h.C,'Control Escolar','control_escolar',True),(h.IC,'Control inactivo','control_escolar',False),(h.N,'Sin perfil',None,True)]:
        h.sql(f"insert into auth.users values('{who}','{who}@example.invalid')")
        if role:h.sql(f"insert into public.profiles(id,full_name,role,active) values('{who}',{h.quote(name)},'{role}',{str(active).lower()})")
    h.sql(f"""
insert into public.subjects(id,code,name) values('{h.S}','HIS-101','Historia'),('{h.S2}','FIL-101','Filosofía');
insert into public.academic_periods(id,name,starts_on,ends_on) values('{h.T}','Semestre 2025','2025-01-01','2025-06-30'),('{T2}','Semestre 2026','2026-01-01','2026-06-30'),('{T3}','Semestre 2027','2027-01-01','2027-06-30');
insert into public.course_offerings(id,subject_id,period_id,active) values('{h.K}','{h.S}','{h.T}',false),('{h.L}','{h.S2}','{h.T}',true);
insert into public.enrollments(id,student_id,subject_id,period_id,active) values('{h.EA}','{h.A}','{h.S}','{h.T}',false),('{E2}','{h.A}','{h.S2}','{h.T}',true),('{E3}','{h.A}','{h.S}','{T2}',true),('{E4}','{h.A}','{h.S2}','{T3}',true);
insert into public.enrollment_grades(enrollment_id,score,published) values('{h.EA}',50,true),('{E2}',80,true),('{E3}',100,true),('{E4}',99,false);
insert into public.enrollment_grade_drafts(enrollment_id,score,revision,updated_by) values('{E2}',1,1,'{h.P}');
""")

def main():
    bootstrap()
    for who in [h.A,h.P,h.IC,h.N]:
        for resource in ['students','record','settings','programs','curriculum','issues','issue']:
            h.test('deny '+who[-2:]+' '+resource,h.actor(who,"select public.portal_kardex_read("+h.quote(resource)+','+h.quote(h.A)+')'),error='42501')
        h.test('deny write '+who[-2:],query('student_save',{'student_id':h.A,'revision':0},who),error='42501')
        h.test('deny issue '+who[-2:],issue_query('x',who=who),error='42501')
    for table in ['kardex_institution','kardex_programs','kardex_students','kardex_plan_subjects','kardex_enrollment_details','kardex_issues']:
        h.test('RLS '+table,f"select relrowsecurity from pg_class where oid='public.{table}'::regclass",'t')
        h.test('private table '+table,f"select has_table_privilege('authenticated','public.{table}','SELECT,INSERT,UPDATE,DELETE')",'f')
    for sig in ['portal_kardex_read(text,uuid,uuid,text,integer,integer,uuid)','portal_kardex_write(text,jsonb)','portal_kardex_issue(uuid,uuid,text,text,uuid,text)']:
        h.test('anonymous cannot execute '+sig,"select has_function_privilege('anon',"+h.quote('public.'+sig)+",'EXECUTE')",'f')
    h.test('record helper private',"select has_function_privilege('authenticated','public._kardex_record(uuid,uuid)','EXECUTE')",'f')
    students=read('students');h.check('lookup includes inactive former students',len(students['items'])==2,students)
    report=read('record');h.check('all periods and inactive enrollments retained',len(report['rows'])==4,report)
    h.check('unpublished finals excluded',report['rows'][-1]['score'] is None)
    h.check('draft does not replace published grade',next(r for r in report['rows'] if r['enrollment_id']==E2)['score']==80)
    h.check('arithmetic average includes published repeats/failures only',report['stats']['average']==76.67,report['stats'])
    h.check('pending grade not treated as zero',report['stats']['pending']==1 and report['stats']['graded']==3)
    h.test('cannot issue without matricula',issue_query(report['token']),error='22023')
    h.sql(f"update public.profiles set role='professor' where id='{h.A}'")
    h.check('former student remains searchable after role change',any(p['id']==h.A for p in read('students')['items']))
    h.check('former student retains history after role change',len(read('record')['rows'])==4)
    student={'student_id':h.A,'student_number':'MR-001','curp':'PEIA040127HTSNRNA1','birth_date':'2004-01-27','entered_on':'2025-01-01','completed_on':'','revision':0}
    # CURP uses a structurally valid sample, not a real identity.
    student['curp']='XEXX040127HTSXXX01'
    save('student_save',student);h.sql(f"update public.profiles set role='student' where id='{h.A}'");h.check('student data saved',read('record')['student']['student_number']=='MR-001')
    h.test('optimistic student conflict',query('student_save',student),error='PT409')
    h.test('duplicate matricula rejected',query('student_save',{'student_id':h.B,'student_number':'MR-001','revision':0}),error='PT409')
    h.test('invalid CURP rejected',query('student_save',{**student,'revision':1,'curp':'invalid'}),error='22023')
    h.test('invalid date rejected',query('student_save',{**student,'revision':1,'birth_date':'infinity'}),error='22023')
    h.test('exit before entry rejected',query('student_save',{**student,'revision':1,'completed_on':'2024-01-01'}),error='22023')
    h.check('search by student number',len(read('students',search='mr-001')['items'])==1)
    for offset,limit in [(-1,30),(0,0),(0,101)]:h.test('bounded lookup '+str((offset,limit)),h.actor(h.C,f"select public.portal_kardex_read('students',null,null,'',{offset},{limit})"),error='22023')
    program={'id':PROGRAM,'revision':0,'name':'Formación filosófica','plan_name':'Plan institucional 2026','education_level':'Formación superior','modality':'Escolarizada','rvoe_number':'','rvoe_date':'','rvoe_authority':'','pass_mark':70,'display_scale':'100','repeat_policy':'all','weighted':False}
    save('program_save',program)
    save('program_save',{**program,'id':PROGRAM2,'name':'Formación teológica'})
    items=[{'enrollment_id':eid,'revision':0,'program_id':PROGRAM,'exam_type':'ORD','notes':''} for eid in [h.EA,E2,E3,E4]]
    save('academic_save',{'student_id':h.A,'items':items})
    h.test('stale academic metadata rejected',query('academic_save',{'student_id':h.A,'items':items}),error='PT409')
    h.test('cannot classify another student enrollment',query('academic_save',{'student_id':h.B,'items':[{**items[0],'revision':1}]}),error='22023')
    save('curriculum_save',{'program_id':PROGRAM,'items':[{'subject_id':h.S,'included':True,'credits':6,'hours':60,'term':'Primero','revision':0},{'subject_id':h.S2,'included':True,'credits':3,'hours':30,'term':'Primero','revision':0}]})
    report=read('record',program=PROGRAM);h.check('credits counted once after repeated subject passed',report['stats']['credits_earned']==9,report['stats'])
    h.check('program average selected correctly',report['stats']['average']==76.67)
    h.check('pending final prevents final issue',not report['final_ready'])
    h.test('server blocks final with pending grade',issue_query(report['token'],kind='final',program=PROGRAM),error='22023')
    save('program_save',{**program,'revision':1,'repeat_policy':'latest'})
    report=read('record',program=PROGRAM);h.check('latest repeat policy',report['stats']['average']==90 and report['stats']['counted']==2,report['stats'])
    save('program_save',{**program,'revision':2,'repeat_policy':'best','weighted':True,'display_scale':'10'})
    report=read('record',program=PROGRAM);h.check('weighted best policy',report['stats']['average']==93.33,report['stats'])
    # Una nota posterior inferior distingue la política de mejor de la última.
    h.sql(f"update public.enrollment_grades set score=60,published=true where enrollment_id='{E4}'")
    report=read('record',program=PROGRAM);h.check('best retains higher earlier final',report['stats']['average']==93.33 and report['stats']['graded']==4,report['stats'])
    h.check('final eligibility based on complete mapped plan',report['final_ready'],report['final_reasons'])
    save('program_save',{**program,'revision':3,'repeat_policy':'latest','weighted':True})
    report=read('record',program=PROGRAM);h.check('weighted latest uses lower final',report['stats']['average']==86.67,report['stats'])
    save('curriculum_save',{'program_id':PROGRAM,'items':[{'subject_id':h.S,'included':True,'credits':None,'hours':60,'term':'Primero','revision':1}]})
    report=read('record',program=PROGRAM);h.check('missing weights never calculate a misleading partial average',report['stats']['average'] is None and report['stats']['missing_weights']==1)
    save('curriculum_save',{'program_id':PROGRAM,'items':[{'subject_id':h.S,'included':True,'credits':6,'hours':60,'term':'Primero','revision':2}]})
    report=read('record',program=PROGRAM)
    stale=report['token'];h.sql(f"update public.enrollment_grades set score=0 where enrollment_id='{E4}'")
    h.test('stale issue does not freeze changed grades',issue_query(stale,program=PROGRAM),error='PT409')
    report=read('record',program=PROGRAM);h.check('published zero is an actual grade',report['stats']['average']==66.67,report['stats'])
    h.sql(f"update public.enrollment_grades set score=90 where enrollment_id='{E4}'")
    report=read('record',program=PROGRAM)
    # A final published concurrently must finish before we freeze the report.
    offering=h.uid(90);teacher_assignment=h.uid(91)
    h.sql(f"insert into public.course_offerings(id,subject_id,period_id,active) values('{offering}','{h.S2}','{T3}',true); insert into public.teaching_assignments(id,professor_id,subject_id,period_id,active) values('{teacher_assignment}','{h.P}','{h.S2}','{T3}',true)")
    writer=h.actor(h.P,f"set local application_name='kardex-grade-lock'; select public.save_teaching_grade('{teacher_assignment}','{E4}',87,0); select public.publish_teaching_grade('{teacher_assignment}','{E4}',1); select pg_sleep(1.5)",commit=True)
    blocker=subprocess.Popen(['docker','exec','-i',h.NAME,'psql','-U','postgres','-d','postgres','-X','-q','-t','-A','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    blocker.stdin.write(writer);blocker.stdin.close()
    for _ in range(100):
        if h.sql("select count(*) from pg_stat_activity where application_name='kardex-grade-lock' and wait_event='PgSleep'").stdout.strip()=='1':break
        time.sleep(.02)
    else:raise AssertionError('Concurrent grade writer never acquired its locks')
    h.test('issue waits for already authorized grade publication',"set lock_timeout='150ms';"+issue_query(report['token'],program=PROGRAM),error='55P03')
    blocker.wait(timeout=10);h.check('concurrent grade publication completed',blocker.returncode==0,blocker.stderr.read())
    h.test('changed concurrent final rejects old preview',issue_query(report['token'],program=PROGRAM),error='PT409')
    h.test('failed stale requests created no document','select count(*) from public.kardex_issues',0)
    h.sql(f"update public.enrollment_grades set score=90 where enrollment_id='{E4}'");report=read('record',program=PROGRAM)
    req=str(uuid.uuid4());issued=json.loads(h.sql(issue_query(report['token'],'final',req,program=PROGRAM,notes='Documento de prueba')).stdout)
    h.check('internal folio issued',issued['saved'] and issued['folio'].startswith('KDX-'),issued)
    h.test('same request can safely retry lost reply',issue_query(report['token'],'final',req,program=PROGRAM,notes='Documento de prueba'))
    h.test('no duplicate folio on retry','select count(*) from public.kardex_issues',1)
    h.test('request id cannot change contents',issue_query(report['token'],'partial',req,program=PROGRAM,notes='Documento de prueba'),error='PT409')
    original=read('issue',issue=req)
    h.sql(f"update public.enrollment_grades set score=12 where enrollment_id='{E4}'")
    h.check('issued copy retains original grade',read('issue',issue=req)==original)
    h.check('live report reflects new grade separately',read('record',program=PROGRAM)['stats']['average']!=original['snapshot']['stats']['average'])
    # Borrado explícito conserva la copia emitida, pero elimina metadata dependiente.
    preview=json.loads(h.sql(h.actor(h.C,f"select public.portal_admin_delete_preview('class','{h.K}')")).stdout)
    h.sql(h.actor(h.C,f"select public.portal_admin_delete('class','{h.K}','{preview['token']}','ELIMINAR')",commit=True))
    h.check('issued copy survives complete class deletion',read('issue',issue=req)==original)
    h.test('deleted enrollment metadata cascades',f"select count(*) from public.kardex_enrollment_details where enrollment_id='{h.EA}'",0)
    h.sql(f"update public.profiles set active=false where id='{h.C}'")
    h.test('revoked Control cannot reprint or export',h.actor(h.C,f"select public.portal_kardex_read('issue',null,null,'',0,30,'{req}')"),error='42501')
    h.test('revoked Control cannot retry issued request',issue_query(report['token'],'final',req,program=PROGRAM,notes='Documento de prueba'),error='42501')
    if os.environ.get('KARDEX_TEST_FIXTURE'):
        Path(os.environ['KARDEX_TEST_FIXTURE']).write_text(json.dumps({'record':original['snapshot'],'issue':original,'program':{**program,'revision':5},'student':original['snapshot']['student']},ensure_ascii=False))
    print(f'PASS {h.checks} kardex SQL assertions; disposable fixtures only',flush=True)

if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
