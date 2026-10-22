#!/usr/bin/env python3
"""Docencia de Control Escolar y borrado completo en PostgreSQL desechable.
Sin red, credenciales ni datos reales. Storage es una fixture de RLS/metadata;
el navegador usa la API oficial para borrar los archivos físicos en producción.
"""
import json
import time
import uuid
import run_learning_local as h

S2=h.S2
T2=h.uid(31)
C2=h.uid(10)

def admin(action,data,who=h.C,commit=True):
    return h.actor(who,'select public.portal_admin_write('+h.quote(action)+','+h.quote(json.dumps(data))+'::jsonb)',commit=commit)

def preview(kind,id,who=h.C):
    return json.loads(h.sql(h.actor(who,'select public.portal_admin_delete_preview('+h.quote(kind)+','+h.quote(id)+')')).stdout)

def deletion(kind,id,token,who=h.C,confirmation='ELIMINAR',commit=True):
    return h.actor(who,'select public.portal_admin_delete('+','.join(map(h.quote,[kind,id,token,confirmation]))+')',commit=commit)

def objects(who):
    return h.actor(who,"select count(*) from storage.objects where bucket_id='portal-coursework'")

def cleanup(who=h.C,ack=True):
    return json.loads(h.sql(h.actor(who,'select public.portal_admin_cleanup_files('+str(ack).lower()+')',commit=True)).stdout)

def main():
    h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
    for _ in range(100):
        logs=h.run('docker','logs',h.NAME,check=False)
        if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0: break
        time.sleep(.2)
    else: raise AssertionError('PostgreSQL did not start')
    h.sql(h.AUTH);h.sql(h.STORAGE)
    for p in sorted((h.ROOT/'supabase/migrations').glob('*.sql')): h.sql(p.read_text())
    for who,name,role,active in [(h.A,'Alumno','student',True),(h.P,'Profesor','professor',True),(h.C,'Control Uno','control_escolar',True),(C2,'Control Dos','control_escolar',True),(h.IC,'Control inactivo','control_escolar',False),(h.N,'Sin perfil',None,False)]:
        h.sql(f"insert into auth.users values('{who}','{who}@example.invalid')")
        if role: h.sql(f"insert into public.profiles(id,full_name,role,active) values('{who}',{h.quote(name)},'{role}',{str(active).lower()})")
    h.sql(f"insert into public.subjects(id,code,name) values('{h.S}','HIS','Historia'),('{S2}','FIL','Filosofía');insert into public.academic_periods(id,name,starts_on,ends_on) values('{h.T}','Semestre Uno','2026-01-01','2026-06-30'),('{T2}','Semestre Dos','2026-08-01','2026-12-31')")
    ids=[]
    for n,(subject,period) in enumerate([(h.S,h.T),(h.S,T2),(S2,h.T),(S2,T2)],100):
        k,e,t,m,topic,task,submission=h.uid(n),h.uid(n+10),h.uid(n+20),h.uid(n+30),h.uid(n+40),h.uid(n+50),h.uid(n+60)
        ids.append((k,e,t,m,topic,task,submission))
        h.sql(f"""
insert into public.course_offerings(id,subject_id,period_id) values('{k}','{subject}','{period}');
insert into public.enrollments(id,student_id,subject_id,period_id) values('{e}','{h.A}','{subject}','{period}');
insert into public.teaching_assignments(id,professor_id,subject_id,period_id) values('{t}','{h.P}','{subject}','{period}');
insert into public.learning_course_settings(course_id,syllabus) values('{k}','Programa');
insert into public.learning_modules(id,course_id,title,published) values('{m}','{k}','Unidad',true);
insert into public.learning_topics(id,course_id,module_id,title,published) values('{topic}','{k}','{m}','Tema',true);
insert into public.learning_topic_progress(topic_id,student_id,completed) values('{topic}','{h.A}',true);
insert into public.learning_assignments(id,course_id,title,published) values('{task}','{k}','Tarea',true);
insert into public.learning_submissions(id,assignment_id,enrollment_id,body) values('{submission}','{task}','{e}','Entrega');
insert into public.learning_submission_history(submission_id,body,url,submitted_at,late,revision) values('{submission}','Entrega anterior','',now(),false,1);
insert into public.learning_grades(assignment_id,enrollment_id,score,graded_by) values('{task}','{e}',95,'{h.P}');
insert into public.learning_announcements(course_id,author_id,title,body,published) values('{k}','{h.P}','Aviso','Aviso',true);
insert into public.learning_events(course_id,created_by,title,starts_at) values('{k}','{h.P}','Evento',now());
insert into public.learning_audit(course_id,actor_id,action,entity_id) values('{k}','{h.P}','test','{task}');
""")
        h.sql(h.actor(h.P,f"select public.save_teaching_grade('{t}','{e}',97,0); select public.publish_teaching_grade('{t}','{e}',1)",commit=True))
        path=f'{k}/{task}/{h.A}/{uuid.uuid4()}/trabajo.pdf'
        orphan=f'{k}/{task}/{h.A}/{uuid.uuid4()}/sin-adjuntar.pdf'
        h.sql(f"insert into storage.objects(bucket_id,name,owner_id) values('portal-coursework',{h.quote(path)},'{h.A}'),('portal-coursework',{h.quote(orphan)},'{h.A}'); insert into public.learning_submission_files(assignment_id,enrollment_id,object_path,name,size,mimetype,uploaded_by) values('{task}','{e}',{h.quote(path)},'trabajo.pdf',100,'application/pdf','{h.A}')")
    k,e,t,*_=ids[0]
    h.test('picker includes both active staff roles',h.actor(h.C,"select jsonb_array_length(public.portal_admin_read('professors')->'items')"),3)
    h.test('student picker excludes staff',h.actor(h.C,"select jsonb_array_length(public.portal_admin_read('students')->'items')"),1)
    h.test('Control Escolar can be assigned',admin('assign',{'class_id':k,'person_id':h.C}))
    assignment=h.sql(f"select id from public.teaching_assignments where professor_id='{h.C}'").stdout.strip()
    h.test('administrative role preserved',f"select role from public.profiles where id='{h.C}'",'control_escolar')
    h.test('staff counts include Control Escolar',h.actor(h.C,f"select r->>'professors' from jsonb_array_elements(public.portal_admin_read('classes')->'items') r where r->>'id'='{k}'"),2)
    h.test('Control reads own teaching assignment',h.actor(h.C,'select count(*) from public.teaching_assignments'),1)
    h.test('Control assigned roster',h.actor(h.C,f"select student_name from public.get_teaching_roster('{assignment}')"),'Alumno')
    h.test('Control assigned grade draft',h.actor(h.C,f"select draft_score from public.save_teaching_grade('{assignment}','{e}',100,2)",commit=True),'100.00')
    h.test('Control assigned grade publication',h.actor(h.C,f"select published_score from public.publish_teaching_grade('{assignment}','{e}',3)",commit=True),'100.00')
    h.test('Control LMS gradebook access',h.actor(h.C,f"select jsonb_array_length(public.portal_learning_read('gradebook','{k}')->'students')"),1)
    h.test('student cannot be assigned as teacher',admin('assign',{'class_id':k,'person_id':h.A}),error='22023')
    h.test('inactive staff cannot be assigned',admin('assign',{'class_id':k,'person_id':h.IC}),error='22023')
    h.test('promote teacher with teaching history',admin('person_update',{'id':h.P,'full_name':'Profesor','role':'control_escolar','active':True,'revision':0}))
    h.test('restore professor role with teaching history',admin('person_update',{'id':h.P,'full_name':'Profesor','role':'professor','active':True,'revision':1}))
    h.test('student academic history cannot become staff',admin('person_update',{'id':h.A,'full_name':'Alumno','role':'control_escolar','active':True,'revision':0}),error='22023')
    for who in [h.A,h.P,h.IC,h.N]:
        for function in [f"select public.portal_admin_delete_preview('class','{k}')",f"select public.portal_admin_delete('class','{k}','fake','ELIMINAR')","select public.portal_admin_cleanup_files(true)"]:
            h.test('unauthorized '+who[-2:]+' '+function.split('(')[0],h.actor(who,function),error='42501')
    for signature in ['portal_admin_delete_preview(text,uuid)','portal_admin_delete(text,uuid,text,text)','portal_admin_cleanup_files(boolean)']:
        h.test('anonymous cannot execute '+signature,"select has_function_privilege('anon',"+h.quote('public.'+signature)+",'EXECUTE')",'f')
    h.test('private snapshot cannot execute',"select has_function_privilege('authenticated','public._portal_delete_snapshot(text,uuid)','EXECUTE')",'f')
    h.test('no direct cleanup table access',"select has_table_privilege('authenticated','public.portal_file_cleanup','SELECT,INSERT,UPDATE,DELETE')",'f')
    h.test('no direct course deletion',h.actor(h.C,f"delete from public.course_offerings where id='{k}'"),error='42501')
    p=preview('class',k)
    for key,expected in {'classes':1,'enrollments':1,'professors':2,'announcements':1,'modules':1,'topics':1,'assignments':1,'submissions':1,'grades':3,'stored_files':2,'files':1,'events':1}.items():h.check('preview accurate '+key,p['counts'][key]==expected,p)
    h.test('wrong confirmation has no effect',deletion('class',k,p['token'],confirmation='eliminar'),error='22023')
    h.sql(f"insert into public.learning_announcements(course_id,author_id,title,body) values('{k}','{h.P}','Nuevo','Nuevo')")
    h.test('changed scope rejects stale preview',deletion('class',k,p['token']),error='PT409')
    h.test('rejected deletion preserved enrollment',f"select count(*) from public.enrollments where id='{e}'",1)
    p=preview('class',k)
    # Un escritor de notas que ya fue autorizado debe terminar antes del borrado.
    blocker=h.background(h.actor(h.P,f"set local application_name='staff-grade-lock'; select public.save_teaching_grade('{t}','{e}',99,4); select pg_sleep(1.5)",commit=True))
    h.wait_sleep('staff-grade-lock')
    h.test('deletion waits for in-flight grade writer',"set lock_timeout='150ms';"+deletion('class',k,p['token']),error='55P03')
    blocker.wait(timeout=10);assert blocker.returncode==0,blocker.stderr.read()
    h.test('lock timeout preserved class and history',f"select count(*) from public.course_offerings where id='{k}'",1)
    h.test('completed concurrent grade changes require a fresh preview',deletion('class',k,p['token']),error='PT409')
    p=preview('class',k)
    h.test('full class deletion',deletion('class',k,p['token']))
    h.test('neighbor classes preserved','select count(*) from public.course_offerings',3)
    h.test('class removal preserves catalogs','select (select count(*) from public.subjects)+(select count(*) from public.academic_periods)',4)
    h.test('class enrollments actually removed',f"select count(*) from public.enrollments where id='{e}'",0)
    h.test('people preserved','select count(*) from public.profiles',5)
    h.test('minimal audit preserved',"select count(*) from public.management_events where action='class_delete'",1)
    h.test('LMS audit detached',f"select count(*) from public.learning_audit where details->>'deleted_course_id'='{k}' and course_id is null",1)
    h.test('deleted class denies old teacher',h.actor(h.P,f"select public.portal_learning_read('course','{k}')"),error='42501')
    for table in ['learning_course_settings','learning_announcements','learning_modules','learning_topics','learning_assignments','learning_events']:
        h.test('class child rows removed '+table,f"select count(*) from public.{table} where course_id='{k}'",0)
    for table in ['enrollment_grades','enrollment_grade_drafts','enrollment_grade_events','learning_grades','learning_submission_files','learning_submissions']:
        h.test('enrollment child rows removed '+table,f"select count(*) from public.{table} where enrollment_id='{e}'",0)
    queue=cleanup();h.check('registered and orphan objects queued',queue['remaining']==2,queue)
    h.test('students cannot read queued files',objects(h.A),6)
    h.test('professors cannot read queued files',objects(h.P),3)
    path=queue['paths'][0]
    h.test('student cannot delete queued files',h.actor(h.A,'delete from storage.objects where name='+h.quote(path)+' returning name'),'')
    h.test('teacher cannot delete queued files',h.actor(h.P,'delete from storage.objects where name='+h.quote(path)+' returning name'),'')
    other=h.sql("select name from storage.objects where name not in(select object_path from public.portal_file_cleanup) limit 1").stdout.strip()
    h.test('Control cannot delete live coursework',h.actor(h.C,'delete from storage.objects where name='+h.quote(other)+' returning name'),'')
    h.check('ack cannot discard pending files',cleanup()['remaining']==2)
    h.sql(h.actor(h.C,'delete from storage.objects where name='+h.quote(path),commit=True))
    h.check('partial Storage success resumable',cleanup()['remaining']==1)
    remaining=cleanup()['paths'][0]
    h.sql(h.actor(C2,'delete from storage.objects where name='+h.quote(remaining),commit=True))
    h.check('another administrator can finish cleanup',cleanup(C2)['remaining']==0)
    h.test('class cannot be deleted twice',deletion('class',k,p['token']),error='22023')
    # Una materia borra sus clases en todos los periodos; conserva otras materias.
    # Se puede reabrir el mismo par después de eliminar la clase antigua.
    h.sql(admin('class_create',{'subject_id':h.S,'period_id':h.T}))
    p=preview('subject',h.S);h.check('subject preview across periods',p['counts']['classes']==2,p)
    h.test('delete subject with full academic content',deletion('subject',h.S,p['token']))
    h.test('other subject preserved','select count(*) from public.subjects',1)
    h.test('both periods preserved','select count(*) from public.academic_periods',2)
    h.test('other subject classes preserved','select count(*) from public.course_offerings',2)
    s3=h.uid(22)
    h.sql(f"insert into public.subjects(id,code,name) values('{s3}','NUEVA','Materia adicional')")
    h.sql(admin('class_create',{'subject_id':s3,'period_id':h.T}))
    p=preview('period',h.T);h.check('period preview spans all its subjects',p['counts']['classes']==2,p)
    h.test('delete period and its classes',deletion('period',h.T,p['token']))
    h.test('other period preserved','select count(*) from public.academic_periods',1)
    h.test('other period class preserved','select count(*) from public.course_offerings',1)
    # Periodo final elimina todo el contenido restante; la materia se conserva.
    p=preview('period',T2);h.test('final period deletion',deletion('period',T2,p['token']))
    for table in ['course_offerings','enrollments','teaching_assignments','enrollment_grades','enrollment_grade_drafts','enrollment_grade_events','learning_course_settings','learning_announcements','learning_modules','learning_topics','learning_topic_progress','learning_assignments','learning_submissions','learning_submission_history','learning_grades','learning_events','learning_submission_files']:
        h.test('complete academic purge '+table,'select count(*) from public.'+table,0)
    p=preview('subject',S2);h.test('empty subject deletion',deletion('subject',S2,p['token']))
    h.check('pending physical files remain tracked until API removal',cleanup()['remaining']==6)
    h.test('all student access to remaining files revoked',objects(h.A),0)
    h.test('all teacher access to remaining files revoked',objects(h.P),0)
    h.test('inactive Control cannot delete queued Storage objects',h.actor(h.IC,"delete from storage.objects returning name"),'')
    h.sql(h.actor(h.C,"delete from storage.objects where bucket_id='portal-coursework'",commit=True))
    h.check('all physical object removals acknowledged',cleanup()['remaining']==0)
    h.test('all object metadata gone','select count(*) from storage.objects',0)
    print(f'PASS {h.checks} SQL assertions; disposable database only',flush=True)

if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
