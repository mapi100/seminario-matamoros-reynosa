"""Inscripción múltiple en PostgreSQL desechable, sin red ni datos de producción."""
import concurrent.futures
import json
import time
import run_learning_local as h

CE=h.uid(350); CE2=h.uid(351); PROF=h.uid(352); INACTIVE=h.uid(353)
STUDENTS=[h.uid(i) for i in range(310,348)]; PER=h.uid(360); CLASS=h.uid(361); CLASS2=h.uid(362); OFF=h.uid(363)
checks=0

def ok(label,condition=True):
 global checks
 assert condition,label
 checks+=1;print('PASS '+label,flush=True)

def query(students,course=CLASS):
 values='null' if students is None else 'array['+','.join(h.quote(v) for v in students)+']::uuid[]'
 return 'select public.portal_enroll_students('+h.quote(course)+','+values+')'

def write(students,who=CE,course=CLASS):return json.loads(h.sql(h.actor(who,query(students,course),commit=True)).stdout)
def candidates(who=CE):return json.loads(h.sql(h.actor(who,'select public.portal_enrollment_candidates('+h.quote(CLASS)+')')).stdout)
def count(student,course=CLASS):return int(h.sql(f"select count(*) from public.enrollments e join public.course_offerings c using(subject_id,period_id) where c.id='{course}' and e.student_id='{student}'").stdout)

def main():
 try:
  h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
  for _ in range(100):
   if 'PostgreSQL init process complete' in (h.run('docker','logs',h.NAME,check=False).stdout+h.run('docker','logs',h.NAME,check=False).stderr) and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
   time.sleep(.2)
  else:raise AssertionError('PG no disponible')
  h.sql(h.AUTH);h.sql(h.STORAGE)
  for path in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):h.sql(path.read_text())
  for uid,role,active in [(s,'student',True) for s in STUDENTS]+[(CE,'control_escolar',True),(CE2,'control_escolar',True),(PROF,'professor',True),(INACTIVE,'student',False)]:
   h.sql(f"insert into auth.users values('{uid}','{uid}@example.invalid');insert into public.profiles(id,full_name,role,active)values('{uid}','Persona ficticia {uid[-3:]}','{role}',{str(active).lower()})")
  h.sql(f"insert into public.academic_periods(id,name,starts_on,ends_on)values('{PER}','Periodo ficticio','2026-08-01','2026-12-31');insert into public.subjects(code,name)values('FICT-1','Materia ficticia'),('FICT-2','Segunda materia'),('FICT-3','Materia inactiva')")
  for i,uid,active in [(1,CLASS,True),(2,CLASS2,True),(3,OFF,False)]:h.sql(f"insert into public.course_offerings(id,subject_id,period_id,active)select '{uid}',id,'{PER}',{str(active).lower()} from public.subjects where code='FICT-{i}'")
  for student,active,score in [(STUDENTS[0],True,88),(STUDENTS[1],False,79)]:
   h.sql(f"insert into public.enrollments(student_id,subject_id,period_id,active)select '{student}',subject_id,period_id,{str(active).lower()} from public.course_offerings where id='{CLASS}';insert into public.enrollment_grades(enrollment_id,score,published)select id,{score},true from public.enrollments where student_id='{student}'")
  before=h.sql('select jsonb_agg(to_jsonb(g) order by enrollment_id) from public.enrollment_grades g').stdout
  data=candidates();ok('38 alumnos activos, sin profesores ni controles',len(data['items'])==38 and {r['id'] for r in data['items']}==set(STUDENTS))
  ok('Estados disponibles, ya inscritos y bajas',sorted(r['status'] for r in data['items']).count('enrolled')==1 and sum(r['status']=='inactive' for r in data['items'])==1)
  for who in [PROF,INACTIVE,STUDENTS[0],None]:
   role='anon' if who is None else 'authenticated'
   for statement in ['select public.portal_enrollment_candidates('+h.quote(CLASS)+')',query([STUDENTS[2]])]:
    denied=h.sql(h.actor(who,statement,role=role),ok=False);ok('Solo CE activo: '+str(who), '42501' in denied.stderr)
  for function in ['portal_enrollment_candidates(uuid)','portal_enroll_students(uuid,uuid[])']:
   ok('Anon sin execute '+function,h.sql("select has_function_privilege('anon','public."+function+"','execute')").stdout.strip()=='f')
  first=write([STUDENTS[0],STUDENTS[1],STUDENTS[2],STUDENTS[2]])
  ok('Lote distingue nuevo, reactivado y existente sin duplicar',first=={'saved':True,'class_id':CLASS,'selected':3,'enrolled':1,'reactivated':1,'already_enrolled':1})
  ok('Calificaciones y sus identificadores conservados',h.sql('select jsonb_agg(to_jsonb(g) order by enrollment_id) from public.enrollment_grades g').stdout==before)
  ok('Repetición del lote es idempotente',write(STUDENTS[:3])['already_enrolled']==3)
  ok('Auditoría solo por las dos inscripciones efectivas',h.sql("select count(*) from public.management_events where action='enroll'").stdout.strip()=='2')
  for invalid in [None,[],[None],[PROF],[INACTIVE],[h.uid(999)],[STUDENTS[3],PROF],[STUDENTS[3]]*501]:
   denied=h.sql(h.actor(CE,query(invalid),commit=True),ok=False);ok('Entrada inválida rechazada antes de escribir','22023' in denied.stderr)
  ok('Alumno válido de un lote inválido no quedó inscrito',count(STUDENTS[3])==0)
  for course in [OFF,h.uid(999),None]:
   result=h.sql(h.actor(CE,query([STUDENTS[3]],course),commit=True),ok=False);ok('Clase ausente/inactiva rechazada','22023' in result.stderr)
  # Falla después de la primera inserción: PostgreSQL debe revertir también auditoría y alta previas.
  events=h.sql('select count(*) from public.management_events').stdout
  h.sql("create function public.fixture_fail_batch() returns trigger language plpgsql as $$begin if new.student_id='"+STUDENTS[5]+"'::uuid then raise exception 'Fallo ficticio';end if;return new;end$$;create trigger fixture_fail before insert on public.enrollments for each row execute function public.fixture_fail_batch()")
  h.sql(h.actor(CE,query(STUDENTS[4:6]),commit=True),ok=False)
  ok('Fallo intermedio revierte todo el lote',count(STUDENTS[4])==0 and count(STUDENTS[5])==0 and h.sql('select count(*) from public.management_events').stdout==events)
  h.sql('drop trigger fixture_fail on public.enrollments;drop function public.fixture_fail_batch()')
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
   results=list(executor.map(lambda who:write(STUDENTS[6:8],who),[CE,CE2]))
  ok('Dos controles simultáneos no duplican ni fallan',sum(r['enrolled'] for r in results)==2 and sum(r['already_enrolled'] for r in results)==2 and all(count(s)==1 for s in STUDENTS[6:8]))
  result=write(STUDENTS);ok('Inscripción completa de 38 en una llamada',result['selected']==38 and all(count(s)==1 for s in STUDENTS))
  ok('Ya inscritos deshabilitables al volver a consultar',all(r['status']=='enrolled' for r in candidates()['items']))
  ok('Otra clase mantiene sus inscripciones independientes',write(STUDENTS[:2],course=CLASS2)['enrolled']==2 and all(count(s,CLASS2)==1 for s in STUDENTS[:2]))
  h.sql(f"update public.profiles set role='professor' where id='{CE}'")
  h.sql(h.actor(CE,query([STUDENTS[0]])),ok=False);ok('Rol revocado se valida en la base, no en metadata')
  print('PASS '+str(checks)+' comprobaciones SQL de inscripción múltiple; sin producción.')
 finally:h.run('docker','rm','-f',h.NAME,check=False)

if __name__=='__main__':main()
