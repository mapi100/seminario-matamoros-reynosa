"""Grupos formativos e inscripciones atómicas en PostgreSQL desechable, sin producción."""
import concurrent.futures
import json
import time
import run_learning_local as h

CE=h.uid(800);CE2=h.uid(801);PROF=h.uid(802);OFF=h.uid(803)
ST=[h.uid(i) for i in range(810,848)];PER=h.uid(850);OLD=h.uid(851);CL=[h.uid(i) for i in range(860,864)]
checks=0

def ok(name,value=True):
 global checks
 assert value,name
 checks+=1;print('PASS '+name,flush=True)
def read(who=CE,period=PER):return json.loads(h.sql(h.actor(who,f"select public.portal_formation_group_read('{period}')")).stdout)
def query(action='assign',students=None,classes=None,token=None,stage='introductorio',sem=1,react=False,period=PER):
 students=ST[:10] if students is None else students
 def arr(values):return "array["+','.join(h.quote(v) for v in values)+"]::uuid[]"
 return 'select public.portal_formation_group_write('+','.join([h.quote(action),h.quote(period),h.quote(stage),str(sem),arr(students),h.quote(token if token is not None else read()['token']),arr(classes or []),str(react).lower()])+')'
def write(**args):return json.loads(h.sql(h.actor(CE,query(**args),commit=True)).stdout)
def enrollment(student,course):return json.loads(h.sql(f"select coalesce((select to_jsonb(e) from public.enrollments e join public.course_offerings c using(subject_id,period_id) where c.id='{course}' and e.student_id='{student}'),'null'::jsonb)").stdout)

def main():
 try:
  h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
  for _ in range(100):
   logs=h.run('docker','logs',h.NAME,check=False)
   if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
   time.sleep(.2)
  else:raise AssertionError('PG no disponible')
  h.sql(h.AUTH);h.sql(h.STORAGE)
  for path in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):h.sql(path.read_text())
  for uid,role,active in [(s,'student',True) for s in ST]+[(CE,'control_escolar',True),(CE2,'control_escolar',True),(PROF,'professor',True),(OFF,'student',False)]:
   h.sql(f"insert into auth.users values('{uid}','{uid}@example.invalid');insert into public.profiles(id,full_name,role,active)values('{uid}','Persona ficticia {uid[-3:]}','{role}',{str(active).lower()})")
  for per,name in [(PER,'Actual'),(OLD,'Anterior')]:h.sql(f"insert into public.academic_periods(id,name,starts_on,ends_on)values('{per}','{name}','2026-01-01','2026-05-31')")
  for n,c in enumerate(CL):
   h.sql(f"insert into public.subjects(code,name)values('FICT-{n}','Materia {n}');insert into public.course_offerings(id,subject_id,period_id,active)select '{c}',id,'{PER}',{str(n!=3).lower()} from public.subjects where code='FICT-{n}';insert into public.course_formation_groups(course_id,group_code)values('{c}','{'CI-2' if n==2 else 'CI-1'}')")
  h.sql(h.actor(CE,f"select public.portal_formation_save('{ST[0]}','{OLD}','filosofia',3,0)",commit=True))
  before=h.sql(f"select to_jsonb(f) from public.student_formation_periods f where period_id='{OLD}'").stdout
  h.sql(f"update public.course_formation_groups set group_code=null where course_id='{CL[3]}'")
  data=read();ok('Todos los 38 alumnos activos sin profesores ni inactivos',len(data['students'])==38 and len(data['classes'])==3)
  for who in [PROF,OFF,ST[0],CE2]:
   if who==CE2:h.sql(f"update public.profiles set active=false where id='{CE2}'")
   for stmt in [f"select public.portal_formation_group_read('{PER}')",query(token=data['token'])]:ok('Solo Control Escolar activo','42501' in h.sql(h.actor(who,stmt),ok=False).stderr)
  h.sql(f"update public.profiles set active=true where id='{CE2}'")
  for sig in ['_formation_group_snapshot(uuid)','portal_formation_group_read(uuid)','portal_formation_group_write(text,uuid,text,integer,uuid[],text,uuid[],boolean)']:
   ok('Sin execute anónimo: '+sig,h.sql("select has_function_privilege('anon','public."+sig+"','execute')").stdout.strip()=='f')
  ok('Helper privado',h.sql("select has_function_privilege('authenticated','public._formation_group_snapshot(uuid)','execute')").stdout.strip()=='f')
  first=write();ok('Diez asignaciones en un lote',first=={'saved':True,'assigned':10,'unchanged':0})
  ok('Historia de otros periodos intacta',before==h.sql(f"select to_jsonb(f) from public.student_formation_periods f where period_id='{OLD}'").stdout)
  ok('Asignar curso no inscribe materias',h.sql('select count(*) from public.enrollments').stdout.strip()=='0')
  ok('Repetir asignación es idempotente',write()['unchanged']==10)
  oldtoken=read()['token'];write(students=[ST[10]])
  ok('Revisión antigua se rechaza','PT409' in h.sql(h.actor(CE,query(token=oldtoken),commit=True),ok=False).stderr)
  for args in [dict(students=[]),dict(students=[ST[11],PROF]),dict(students=[OFF]),dict(sem=3),dict(stage='invalido'),dict(action='delete'),dict(students=[ST[0]]*501),dict(classes=[CL[0]])]:
   ok('Lote inválido no escribe','22023' in h.sql(h.actor(CE,query(**args),commit=True),ok=False).stderr)
  ok('Alumno válido de lote mixto no cambia',next(x for x in read()['students'] if x['id']==ST[11])['revision']==0)
  write(students=[ST[1]],stage='filosofia',sem=3)
  moved=write(students=[ST[1]]);ok('Cambio explícito de curso dentro del periodo',moved['assigned']==1 and next(x for x in read()['students'] if x['id']==ST[1])['semester']==1)
  for student,active,score in [(ST[0],True,88),(ST[1],False,79)]:
   h.sql(f"insert into public.enrollments(student_id,subject_id,period_id,active)select '{student}',subject_id,period_id,{str(active).lower()} from public.course_offerings where id='{CL[0]}';insert into public.enrollment_grades(enrollment_id,score,published)select id,{score},true from public.enrollments where student_id='{student}'")
  oldenroll=enrollment(ST[1],CL[0]);grades=h.sql('select jsonb_agg(to_jsonb(g) order by enrollment_id) from public.enrollment_grades g').stdout
  result=write(action='enroll',classes=CL[:2]);ok('10 × 2 distingue nuevas, existentes y bajas',result=={'saved':True,'enrolled':18,'reactivated':0,'already_enrolled':1,'kept_inactive':1})
  ok('Baja conservada por defecto',enrollment(ST[1],CL[0])==oldenroll)
  result=write(action='enroll',classes=CL[:2],react=True);ok('Reactivación solo si se solicita',result['reactivated']==1 and result['already_enrolled']==19 and enrollment(ST[1],CL[0])['id']==oldenroll['id'])
  ok('Todas las notas y sus identificadores permanecen intactos',grades==h.sql('select jsonb_agg(to_jsonb(g) order by enrollment_id) from public.enrollment_grades g').stdout)
  for args in [dict(classes=[]),dict(classes=[CL[2]]),dict(classes=[CL[3]]),dict(classes=[h.uid(999)]),dict(classes=CL[:2],students=[ST[12]])]:
   ok('Inscripción exige curso, alumnos y materias compatibles','22023' in h.sql(h.actor(CE,query(action='enroll',**args),commit=True),ok=False).stderr)
  # Excepciones: solo un alumno y una materia, no altera al resto.
  result=write(action='enroll',students=[ST[10]],classes=[CL[0]]);ok('Seleccionar excepciones solo afecta los pares elegidos',result['enrolled']==1 and enrollment(ST[10],CL[1]) is None)
  # Falla intermedia revierte formación y auditoría previas.
  events=h.sql('select count(*) from public.management_events').stdout
  h.sql(f"create function public.fixture_fail_group() returns trigger language plpgsql as $$begin if new.student_id='{ST[14]}'::uuid then raise exception 'Fallo ficticio';end if;return new;end$$;create trigger fixture_fail before insert on public.student_formation_periods for each row execute function public.fixture_fail_group()")
  h.sql(h.actor(CE,query(students=ST[13:15]),commit=True),ok=False)
  ok('Fallo de asignación revierte alumnos y auditoría',all(r['revision']==0 for r in read()['students'] if r['id'] in ST[13:15]) and h.sql('select count(*) from public.management_events').stdout==events)
  h.sql('drop trigger fixture_fail on public.student_formation_periods;drop function public.fixture_fail_group()')
  write(students=ST[13:15]);events=h.sql('select count(*) from public.management_events').stdout
  h.sql(f"create function public.fixture_fail_group() returns trigger language plpgsql as $$begin if new.student_id='{ST[14]}'::uuid then raise exception 'Fallo ficticio';end if;return new;end$$;create trigger fixture_fail before insert on public.enrollments for each row execute function public.fixture_fail_group()")
  h.sql(h.actor(CE,query(action='enroll',students=ST[13:15],classes=CL[:2]),commit=True),ok=False)
  ok('Fallo de inscripción revierte el lote completo y auditoría',enrollment(ST[13],CL[0]) is None and h.sql('select count(*) from public.management_events').stdout==events)
  h.sql('drop trigger fixture_fail on public.enrollments;drop function public.fixture_fail_group()')
  token=read()['token'];stmt=query(action='enroll',students=ST[13:15],classes=CL[:2],token=token)
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(lambda who:h.run('docker','exec','-i',h.NAME,'psql','-U','postgres','-X','-q','-t','-A','-v','ON_ERROR_STOP=1',input=h.actor(who,stmt,commit=True),check=False),[CE,CE2]))
  ok('Dos controles simultáneos: una confirmación, otra revisión obsoleta',sum(r.returncode==0 for r in results)==1 and any('cambiaron' in r.stderr for r in results))
  ok('No hay inscripciones duplicadas',h.sql('select count(*) from (select student_id,subject_id,period_id from public.enrollments group by 1,2,3 having count(*)>1)x').stdout.strip()=='0')
  ok('Consultar no modifica datos',read()['token']==read()['token'])
  # Una clase activa sin curso no rompe el tablero ni aparece como materia del grupo.
  h.sql(f"update public.course_offerings set active=true where id='{CL[3]}'")
  ok('Clases sin clasificación se omiten sin bloquear grupos',len(read()['classes'])==3)
  stale=read()['token'];h.sql(h.actor(CE,f"select public.portal_course_group_save('{CL[0]}','CI-2',1)",commit=True))
  ok('Mover una materia invalida una revisión previa','PT409' in h.sql(h.actor(CE,query(action='enroll',classes=[CL[0]],token=stale),commit=True),ok=False).stderr)
  print('PASS '+str(checks)+' comprobaciones SQL de grupos formativos; sin producción.')
 finally:h.run('docker','rm','-f',h.NAME,check=False)
if __name__=='__main__':main()
