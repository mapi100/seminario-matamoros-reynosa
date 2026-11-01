"""Corrección de grupos: PostgreSQL desechable, sin red ni datos de producción."""
import concurrent.futures
import json
import time
import run_learning_local as h
CE=h.uid(900);CE2=h.uid(901);PROF=h.uid(902);OFF=h.uid(903)
ST=[h.uid(n) for n in range(910,921)];P26=h.uid(930);P27=h.uid(931)
CL=[h.uid(n) for n in range(940,944)]
checks=0

def ok(label,condition=True):
 global checks
 assert condition,label
 checks+=1;print('PASS '+label,flush=True)
def read(period=P27):return json.loads(h.sql(h.actor(CE,f"select public.portal_formation_group_read('{period}')")).stdout)
def query(kind='students',ids=None,period=P27,token=None,stage='introductorio',semester=1,confirmation='CONFIRMAR'):
 values=ST[:10] if ids is None else ids
 arr='null' if values=='null' else 'array['+','.join(h.quote(v) for v in values)+']::uuid[]'
 return 'select public.portal_formation_group_remove('+','.join([h.quote(kind),h.quote(period),h.quote(stage),str(semester),arr,h.quote(token or read(period)['token']),h.quote(confirmation)])+')'
def remove(**args):return json.loads(h.sql(h.actor(CE,query(**args),commit=True)).stdout)
def assign(ids=ST[:10],period=P27):
 arr='array['+','.join(h.quote(s) for s in ids)+']::uuid[]'
 return h.sql(h.actor(CE,"select public.portal_formation_group_write('assign','"+period+"','introductorio',1,"+arr+",'"+read(period)['token']+"')",commit=True))
def contents(table,where='true'):return h.sql(f"select coalesce(jsonb_agg(to_jsonb(x) order by to_jsonb(x)::text),'[]') from public.{table} x where {where}").stdout

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
  for period,name,start,end in [(P26,'AGO-DIC 2026','2026-08-01','2026-12-31'),(P27,'ENE-MAY 2027','2027-01-01','2027-05-31')]:
   h.sql(f"insert into public.academic_periods(id,name,starts_on,ends_on)values('{period}','{name}','{start}','{end}')")
  for n in range(2):
   h.sql(f"insert into public.subjects(code,name)values('FICT-{n}','Materia {n}')")
   for per,c in [(P26,CL[n]),(P27,CL[n+2])]:
    h.sql(f"insert into public.course_offerings(id,subject_id,period_id)select '{c}',id,'{per}' from public.subjects where code='FICT-{n}';insert into public.course_formation_groups(course_id,group_code)values('{c}','CI-1')")
  assign(period=P26);assign()
  for per in [P26,P27]:
   h.sql(h.actor(CE,f"select public.portal_formation_save('{ST[10]}','{per}','filosofia',3,0)",commit=True))
   h.sql(f"insert into public.enrollments(student_id,subject_id,period_id)select '{ST[0]}',subject_id,period_id from public.course_offerings where period_id='{per}';insert into public.teaching_assignments(professor_id,subject_id,period_id)select '{PROF}',subject_id,period_id from public.course_offerings where period_id='{per}'")
  h.sql('insert into public.enrollment_grades(enrollment_id,score,published)select id,87,true from public.enrollments')
  h.sql(f"insert into public.learning_assignments(course_id,title)values('{CL[2]}','Tarea ficticia');insert into public.learning_course_settings(course_id,syllabus)values('{CL[2]}','Temario de prueba')")
  protected=['profiles','enrollments','enrollment_grades','teaching_assignments','course_offerings','learning_assignments','learning_course_settings']
  before={t:contents(t) for t in protected};history=contents('student_formation_periods',f"period_id='{P26}'");oldclasses=contents('course_formation_groups',f"course_id in ('{CL[0]}','{CL[1]}')")
  ok('Hay diez seminaristas CI-1 en cada periodo',all(sum(r['stage_code']=='introductorio' for r in read(p)['students'])==10 for p in [P26,P27]))
  for who,role in [(None,'anon'),(PROF,'authenticated'),(OFF,'authenticated'),(ST[0],'authenticated')]:
   ok('Solo Control Escolar activo puede quitar','42501' in h.sql(h.actor(who,query(),role=role,commit=True),ok=False).stderr)
  ok('Anon no tiene execute',h.sql("select has_function_privilege('anon','public.portal_formation_group_remove(text,uuid,text,integer,uuid[],text,text)','execute')").stdout.strip()=='f')
  for text in ['',None,'SI','CONFIRMAR TODO']:
   ok('Confirmación obligatoria','22023' in h.sql(h.actor(CE,query(confirmation=text),commit=True),ok=False).stderr)
  for args in [dict(ids=[]),dict(ids='null'),dict(ids=[None]),dict(ids=[ST[0],ST[10]]),dict(ids=[ST[0],PROF]),dict(ids=[ST[0],h.uid(999)]),dict(kind='delete'),dict(semester=3),dict(ids=ST[:1]*501)]:
   ok('Validar todo antes de quitar','22023' in h.sql(h.actor(CE,query(**args),commit=True),ok=False).stderr)
  result=remove();ok('Quitar los diez de ENE-MAY devuelve diez',result=={'saved':True,'kind':'students','removed':10,'period_id':P27,'group_code':'CI-1'})
  ok('Quedan sin etapa en ENE-MAY',all(r['stage_code'] is None for r in read()['students'] if r['id'] in ST[:10]))
  ok('AGO-DIC conserva formación íntegra',contents('student_formation_periods',f"period_id='{P26}'")==history)
  ok('Cuentas, clases, profesores, tareas y notas intactos',all(contents(t)==before[t] for t in protected))
  ok('Otro curso del mismo periodo se conserva',next(r for r in read()['students'] if r['id']==ST[10])['stage_code']=='filosofia')
  ok('Auditoría registra curso, periodo y valores anteriores',h.sql("select count(*) from public.management_events where action='formation_removed' and details->>'before_stage'='introductorio' and details->>'before_semester'='1'").stdout.strip()=='10')
  assign();ok('Se puede corregir y volver a agregar',sum(r['stage_code']=='introductorio' for r in read()['students'])==10)
  result=remove(ids=[ST[0],ST[0]]);ok('UUID duplicado se quita solo una vez',result['removed']==1)
  assign(ids=[ST[0]])
  events=contents('management_events');formation=contents('student_formation_periods')
  h.sql(f"create function public.fixture_remove_fail()returns trigger language plpgsql as $$begin if old.student_id='{ST[1]}'::uuid then raise exception 'Fallo ficticio';end if;return old;end$$;create trigger fixture_fail before delete on public.student_formation_periods for each row execute function public.fixture_remove_fail()")
  h.sql(h.actor(CE,query(ids=ST[:2]),commit=True),ok=False)
  ok('Fallo intermedio revierte retiradas y auditoría',contents('student_formation_periods')==formation and contents('management_events')==events)
  h.sql('drop trigger fixture_fail on public.student_formation_periods;drop function public.fixture_remove_fail()')
  for args in [dict(ids=[CL[0]]),dict(ids=[CL[2],CL[0]]),dict(ids=[CL[2],h.uid(999)]),dict(ids=[CL[2]]*101)]:
   ok('Materia de otro periodo o lote inválido se rechaza','22023' in h.sql(h.actor(CE,query(kind='classes',**args),commit=True),ok=False).stderr)
  groupbefore=contents('course_formation_groups');events=contents('management_events')
  h.sql(f"create function public.fixture_remove_fail()returns trigger language plpgsql as $$begin if new.course_id='{CL[3]}'::uuid then raise exception 'Fallo ficticio';end if;return new;end$$;create trigger fixture_fail before update on public.course_formation_groups for each row execute function public.fixture_remove_fail()")
  h.sql(h.actor(CE,query(kind='classes',ids=CL[2:]),commit=True),ok=False)
  ok('Fallo intermedio de materias revierte lote y auditoría',contents('course_formation_groups')==groupbefore and contents('management_events')==events)
  h.sql('drop trigger fixture_fail on public.course_formation_groups;drop function public.fixture_remove_fail()')
  result=remove(kind='classes',ids=CL[2:]);ok('Quitar materias solo las deja sin clasificación',result['removed']==2 and len(read()['classes'])==0 and h.sql(f"select count(*) from public.course_formation_groups where course_id in ('{CL[2]}','{CL[3]}') and group_code is null and revision=2").stdout.strip()=='2')
  ok('Materias de AGO-DIC intactas',contents('course_formation_groups',f"course_id in ('{CL[0]}','{CL[1]}')")==oldclasses)
  ok('Quitar materias conserva todas las relaciones académicas',all(contents(t)==before[t] for t in protected))
  h.sql(h.actor(CE,f"select public.portal_course_group_save('{CL[2]}','CI-1',2)",commit=True));ok('Materia se puede volver a clasificar',len(read()['classes'])==1)
  token=read()['token'];stmt=query(ids=ST[:2],token=token)
  with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
   results=list(pool.map(lambda who:h.run('docker','exec','-i',h.NAME,'psql','-U','postgres','-X','-q','-t','-A','-v','ON_ERROR_STOP=1',input=h.actor(who,stmt,commit=True),check=False),[CE,CE2]))
  ok('Dos controles simultáneos: segundo debe actualizar',sum(r.returncode==0 for r in results)==1 and any('cambiaron' in r.stderr for r in results))
  ok('Repetir una confirmación antigua no retira más','PT409' in h.sql(h.actor(CE,stmt,commit=True),ok=False).stderr)
  h.sql(f"update public.profiles set active=false where id='{CE2}'")
  ok('Control desactivado se rechaza en servidor','42501' in h.sql(h.actor(CE2,query(ids=ST[2:3]),commit=True),ok=False).stderr)
  print('PASS '+str(checks)+' comprobaciones SQL para quitar asignaciones; sin producción.')
 finally:h.run('docker','rm','-f',h.NAME,check=False)
if __name__=='__main__':main()
