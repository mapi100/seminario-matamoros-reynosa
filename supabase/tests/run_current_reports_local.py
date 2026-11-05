"""Boletas vigentes e historial: PostgreSQL desechable, con/sin extensión antigua."""
import json,sys,time
import run_learning_local as h
LEGACY='--sin-extension-anterior' in sys.argv

def preview():return json.loads(h.sql(h.actor(h.C,f"select public.portal_report_card_read('preview','{h.A}','{h.T}')")).stdout)
try:
 h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
 for _ in range(100):
  logs=h.run('docker','logs',h.NAME,check=False)
  if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
  time.sleep(.2)
 else:raise AssertionError('PostgreSQL no arrancó')
 h.sql(h.AUTH);h.sql(h.STORAGE)
 for p in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):
  if LEGACY and p.name=='20261027000000_semester_report_cards.sql':continue
  h.sql(p.read_text())
 # Reinstalación repetible, sin tocar wrappers ni copias previas.
 migration=h.ROOT/'supabase/migrations/20261105000000_report_card_current_enrollments.sql'
 h.sql(migration.read_text())
 h.sql(f"""
insert into auth.users values('{h.C}','control@example.invalid'),('{h.A}','alumno@example.invalid');
insert into public.profiles(id,full_name,role) values('{h.C}','Control de prueba','control_escolar'),('{h.A}','Alumno de prueba','student');
insert into public.subjects(id,code,name) values('{h.S}','TEST-BAJA','Materia retirada'),('{h.S2}','TEST-ACT','Materia vigente');
insert into public.academic_periods(id,name,starts_on,ends_on)values('{h.T}','AGO-DIC 2026','2026-08-01','2026-12-31');
insert into public.enrollments(id,student_id,subject_id,period_id,active) values('{h.EA}','{h.A}','{h.S}','{h.T}',false),('{h.EB}','{h.A}','{h.S2}','{h.T}',true);
insert into public.enrollment_grades(enrollment_id,score,published)values('{h.EA}',50,true),('{h.EB}',80,true);
insert into public.kardex_students(student_id,student_number)values('{h.A}','TEST-001');
insert into public.student_formation_periods(student_id,period_id,stage_code,semester,updated_by)values('{h.A}','{h.T}','introductorio',1,'{h.C}');
update public.kardex_institution set rector_name='Rector ficticio',prefect_name='Prefecto ficticio' where id=true;
""")
 result=preview();h.check('boleta solo muestra inscripción vigente',len(result['rows'])==1 and result['rows'][0]['name']=='Materia vigente')
 h.check('escala 0-10 sin cambiar nota fuente',result['rows'][0]['score']==8 and result['rows'][0]['source_score']==80)
 history=json.loads(h.sql(h.actor(h.C,f"select public.portal_kardex_read('record','{h.A}')")).stdout)
 h.check('kardex conserva inscripción retirada y su nota',len(history['rows'])==2 and any(not r['enrollment_active'] and r['score']==50 for r in history['rows']))
 h.check('lista para emitir con requisitos completos',result['ready'])
 h.test('alumno no emite/consulta boleta oficial CE',h.actor(h.A,f"select public.portal_report_card_read('preview','{h.A}','{h.T}')"),error='42501')
 h.test('sin permiso anónimo',"select has_function_privilege('anon','public.portal_report_card_issue(uuid,uuid,jsonb,text,uuid)','execute')",'f')
 req=h.uid(999)
 body=f"select public.portal_report_card_issue('{h.A}','{h.T}','{{}}',{h.quote(result['token'])},'{req}')"
 issue=json.loads(h.sql(h.actor(h.C,body,commit=True)).stdout)
 h.check('boleta se emite',issue['saved'])
 before=h.sql(f"select snapshot from public.report_card_issues where id='{req}'").stdout
 h.sql(f"update public.kardex_students set student_number='TEST-002' where student_id='{h.A}';update public.enrollments set active=not active where student_id='{h.A}'")
 h.sql(migration.read_text())
 after=h.sql(f"select snapshot from public.report_card_issues where id='{req}'").stdout
 h.check('correcciones posteriores no reescriben boleta emitida',after==before)
 h.test('calificaciones fuente intactas',"select string_agg(score::text,',' order by score) from public.enrollment_grades",'50.00,80.00')
 print('PASS modo:', 'sin extensión anterior' if LEGACY else 'con extensión anterior')
finally:h.run('docker','rm','-f',h.NAME,check=False)
