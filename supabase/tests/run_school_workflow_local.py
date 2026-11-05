"""Control Escolar: notas finales y boletas en lote en PostgreSQL aislado."""
import json,uuid
import run_kardex_local as k
h=k.h;q=h.quote
h.EB=h.uid(101);h.EB2=h.uid(102)
B1=str(uuid.uuid4());B2=str(uuid.uuid4())
def finals(course=h.K,who=h.C):return json.loads(h.sql(h.actor(who,f"select public.portal_school_finals_read('{course}')")).stdout)
def save(course,rows,token=None,who=h.C,reason='Captura final proporcionada por el docente'):
 token=token or finals(course,who)['token']
 return h.actor(who,'select public.portal_school_finals_save('+','.join([q(course),q(token),q(json.dumps(rows))+'::jsonb',q(reason)])+')',commit=True)
def group(who=h.C,sem=1):return json.loads(h.sql(h.actor(who,f"select public.portal_report_group_read('{h.T}','introductorio',{sem})")).stdout)
def batch(plan,request=B1,who=h.C):return h.actor(who,'select public.portal_report_group_issue('+','.join([q(h.T),q('introductorio'),'1',q(plan['token']),q(request),'true'])+')',commit=True)
try:
 k.bootstrap()
 h.sql(f"update public.course_offerings set active=true where id='{h.K}';update public.profiles set active=true where id='{h.B}';update public.enrollments set active=true where id='{h.EA}';insert into public.enrollments(id,student_id,subject_id,period_id)values('{h.EB}','{h.B}','{h.S}','{h.T}'),('{h.EB2}','{h.B}','{h.S2}','{h.T}');insert into public.course_formation_groups(course_id,group_code)values('{h.K}','CI-1'),('{h.L}','CI-1');insert into public.student_formation_periods(student_id,period_id,stage_code,semester,updated_by)values('{h.A}','{h.T}','introductorio',1,'{h.C}'),('{h.B}','{h.T}','introductorio',1,'{h.C}');insert into public.kardex_students(student_id,student_number)values('{h.A}','TEST-A'),('{h.B}','TEST-B');update public.kardex_institution set rector_name='Rector ficticio',prefect_name='Prefecto ficticio' where id=true;")
 h.test('CE lee sin asignación docente',"select count(*) from public.teaching_assignments",'0')
 data=finals();h.check('tiene acceso final de toda la clase',len(data['students'])==2)
 for actor in [h.A,h.P,h.IC,h.N]:h.test('otro rol/inactivo no captura finales',h.actor(actor,f"select public.portal_school_finals_read('{h.K}')"),error='42501')
 for fn in ['portal_school_finals_read(uuid)','portal_school_finals_save(uuid,text,jsonb,text)','portal_report_group_read(uuid,text,integer)','portal_report_group_issue(uuid,text,integer,text,uuid,boolean)']:
  h.test('anon sin permiso '+fn,"select has_function_privilege('anon',"+q('public.'+fn)+",'execute')",'f')
 first_token=data['token'];rows=[{'enrollment_id':h.EA,'score':88},{'enrollment_id':h.EB,'score':91}]
 h.test('no cruza notas de otra clase',save(h.K,[{'enrollment_id':k.E2,'score':90}]),error='42501')
 h.test('nota fuera de escala rechaza lote entero',save(h.K,[{'enrollment_id':h.EA,'score':101},{'enrollment_id':h.EB,'score':90}]),error='22023')
 h.test('no alumnos duplicados',save(h.K,[rows[0],rows[0]]),error='22023')
 h.test('corrección requiere motivo',save(h.K,rows,reason=''),error='22023')
 h.sql(save(h.K,rows));h.test('nota final publicada por CE',f"select score from public.enrollment_grades where enrollment_id='{h.EA}'",'88.00')
 h.test('no usa una revisión antigua',save(h.K,rows,token=first_token),error='PT409')
 h.test('auditoría conserva responsable CE',f"select actor_id from public.enrollment_grade_events where enrollment_id='{h.EA}' order by revision desc limit 1",h.C)
 h.test('no crea asignaciones docentes para dar acceso',"select count(*) from public.teaching_assignments",'0')
 # Una actividad con criterio publicado puede quedar pendiente: la captura del
 # docente por Control Escolar sigue disponible sin alterar la ponderación.
 activity=h.write(h.C,'assignment_save',h.L,{'title':'Examen pendiente','published':True,'grading_category':'tasks','requires_submission':False})['id']
 scheme={'categories':[{'code':name,'weight':100 if name=='tasks' else 0,'mode':'equal'} for name in ['tasks','exams','projects','participation']],'items':[{'id':activity,'category':'tasks','share':1}]}
 h.sql(h.actor(h.C,"select public.portal_gradebook_write("+q(h.L)+",'scheme_save',"+q(json.dumps({'schema':scheme,'revision':0}))+"::jsonb)",commit=True))
 h.sql(h.actor(h.C,"select public.portal_gradebook_write("+q(h.L)+",'scheme_publish',"+q(json.dumps({'schema':scheme,'revision':1,'confirmed':True}))+"::jsonb)",commit=True))
 h.check('ponderación publicada pendiente no inventa notas',not finals(h.L)['students'][0]['calculation']['ready'])
 h.test('captura manual ponderada exige motivo',save(h.L,[{'enrollment_id':k.E2,'score':75}],reason=''),error='22023')
 current=group();h.check('alumno incompleto no se emite',any(p['action']=='pending' for p in current['items']))
 h.sql(save(h.L,[{'enrollment_id':k.E2,'score':75},{'enrollment_id':h.EB2,'score':82}]))
 plan=group();h.check('dos alumnos listos para emitir',len(plan['items'])==2 and all(p['action']=='issue' for p in plan['items']))
 for actor in [h.A,h.P,h.IC]:h.test('boletas en lote solo CE',h.actor(actor,f"select public.portal_report_group_read('{h.T}','introductorio',1)"),error='42501')
 stale=plan
 h.sql(save(h.K,[{'enrollment_id':h.EA,'score':89}]))
 h.test('cambio de nota invalida lote revisado',batch(stale),error='PT409')
 h.test('todavía no se emitieron copias parciales',"select count(*) from public.report_card_issues",'0')
 # Si falla una emisión, ninguna otra copia del mismo lote queda guardada.
 h.sql("create function public.test_batch_failure() returns trigger language plpgsql as $$begin if new.student_id='"+h.B+"'::uuid then raise exception 'fallo simulado';end if;return new;end;$$;create trigger test_batch_failure before insert on public.report_card_issues for each row execute function public.test_batch_failure();")
 plan=group();h.test('fallo en segunda boleta revierte todo el lote',batch(plan),error='P0001')
 h.test('lote fallido no deja boletas parciales',"select count(*) from public.report_card_issues",'0')
 h.test('lote fallido no queda marcado como emitido',"select count(*) from public.report_card_group_batches",'0')
 h.sql('drop trigger test_batch_failure on public.report_card_issues;drop function public.test_batch_failure()')
 plan=group();result=json.loads(h.sql(batch(plan)).stdout)
 h.check('lote emite dos copias',result['newly_issued']==2 and len(result['documents'])==2)
 again=json.loads(h.sql(batch(plan)).stdout);h.check('reintento incierto devuelve mismo lote/folios',again==result)
 h.test('no duplica boletas al reintentar',"select count(*) from public.report_card_issues",'2')
 new=group();h.check('boletas actuales se reutilizan',all(x['action']=='reuse' for x in new['items']))
 reused=json.loads(h.sql(batch(new,B2)).stdout);h.check('nueva descarga reutiliza sin folios extra',reused['newly_issued']==0 and reused['reused']==2)
 old_snapshot=h.sql("select snapshot::text from public.report_card_issues where student_id='"+h.A+"' order by issued_at desc limit 1").stdout
 h.sql(save(h.K,[{'enrollment_id':h.EA,'score':90}]))
 h.check('corregir nota conserva boleta emitida íntegra',old_snapshot==h.sql("select snapshot::text from public.report_card_issues where student_id='"+h.A+"' order by issued_at desc limit 1").stdout)
 h.test('motivo manual registrado sin tocar tareas',"select count(*) from public.learning_grades",'0')
 h.check('las ponderaciones permanecen publicadas',finals(h.L)['students'][0]['calculation']['configured'])
 corrected=group();h.check('nota corregida prepara copia nueva solo del afectado',sum(x['action']=='issue' for x in corrected['items'])==1)
 # Otro usuario que recibe el rol CE también hereda clases nuevas, sin filas
 # docentes. Los lotes confirmados siguen vinculados a su responsable.
 h.sql(f"insert into public.profiles(id,full_name,role,active)values('{h.N}','Segundo Control Escolar','control_escolar',true)")
 h.check('nuevo Control Escolar hereda las clases sin asignarse',len(finals(who=h.N)['students'])==2)
 h.test('otro CE no reutiliza ID de lote ajeno',batch(plan,who=h.N),error='PT409')
 future_subject=h.uid(130);future_course=h.uid(131);future_enrollment=h.uid(132)
 h.sql(f"insert into public.subjects(id,code,name)values('{future_subject}','NUEVA','Materia futura');insert into public.course_offerings(id,subject_id,period_id,active)values('{future_course}','{future_subject}','{h.T}',true);insert into public.enrollments(id,student_id,subject_id,period_id)values('{future_enrollment}','{h.A}','{future_subject}','{h.T}')")
 h.check('materia nueva accesible automáticamente a ambos CE',len(finals(future_course)['students'])==1 and len(finals(future_course,who=h.N)['students'])==1)
 h.test('crear curso y CE no crea titularidades falsas',"select count(*) from public.teaching_assignments",'0')
 h.sql(f"update public.profiles set active=false where id='{h.C}'")
 h.test('revocar CE bloquea incluso descarga confirmada',batch(plan),error='42501')
 h.sql(f"update public.profiles set active=true where id='{h.C}'")
 h.sql((h.ROOT/'supabase/migrations/20261105010000_control_school_workflow.sql').read_text())
 h.test('reinstalar conserva boletas y lotes',"select count(*) from public.report_card_issues",'2')
 print('PASS acceso automático CE, captura directa, permisos y lotes idempotentes')
finally:h.run('docker','rm','-f',h.NAME,check=False)
