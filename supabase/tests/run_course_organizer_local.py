"""Organizador: PostgreSQL aislado, fixtures ficticios y ninguna conexión externa."""
import json,time
from pathlib import Path
import run_learning_local as h
A=h.uid(210);P=h.uid(211);C=h.uid(212);I=h.uid(213);PER=h.uid(214);PER2=h.uid(215);checks=0

def ok(label,condition=True):
 global checks
 assert condition,label;checks+=1

def read(who=C,period=PER):return json.loads(h.sql(h.actor(who,'select public.portal_course_board_read('+h.quote(period)+')')).stdout)
def move(who,subject,course,group,revision,period=PER):return h.actor(who,'select public.portal_course_board_write('+','.join([h.quote(subject),h.quote(period),h.quote(course),h.quote(group),str(revision) if revision is not None else 'null'])+')',commit=True)

def main():
 try:
  h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
  for _ in range(100):
   logs=h.run('docker','logs',h.NAME,check=False)
   if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
   time.sleep(.2)
  else:raise AssertionError('PG no disponible')
  h.sql(h.AUTH);h.sql(h.STORAGE)
  for p in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):h.sql(p.read_text())
  for uid,name,role,active in [(A,'Alumno ficticio','student',True),(P,'Profesor ficticio','professor',True),(C,'Control ficticio','control_escolar',True),(I,'Control inactivo','control_escolar',False)]:
   h.sql(f"insert into auth.users values('{uid}','{uid}@example.invalid');insert into public.profiles(id,full_name,role,active) values('{uid}',{h.quote(name)},{h.quote(role)},{str(active).lower()})")
  h.sql(f"insert into public.academic_periods(id,name,starts_on,ends_on) values('{PER}','Prueba actual','2026-08-01','2026-12-31'),('{PER2}','Prueba posterior','2027-01-01','2027-05-31')")
  h.sql("insert into public.subjects(code,name) select 'FICT-'||i,'Materia ficticia '||i from generate_series(1,145)i")
  h.sql(f"insert into public.course_offerings(subject_id,period_id) select id,'{PER}' from public.subjects order by code limit 134")
  h.sql("insert into public.course_formation_groups(course_id,group_code)select id,case when n%3=0 then 'CI-1' when n%3=1 then '1F-1' else '1T-1' end from(select id,row_number()over(order by id)n from public.course_offerings)x")
  data=read();ok('134 clases sin corte de 50',len(data['classes'])==134);ok('Catálogo completo 145 materias',len(data['subjects'])==145)
  c=data['classes'][0];subject=c['subject_id'];course=c['id'];enrollment=h.uid(220)
  h.sql(f"insert into public.enrollments(id,student_id,subject_id,period_id)values('{enrollment}','{A}','{subject}','{PER}');insert into public.enrollment_grades(enrollment_id,score,published)values('{enrollment}',85,true)")
  for who in [A,P,I]:
   h.sql(h.actor(who,f"select public.portal_course_board_read('{PER}')"),ok=False);ok('Lectura solo CE activo')
   h.sql(move(who,subject,course,'CI-2',1),ok=False);ok('Mover solo CE activo')
  for role in ['anon','authenticated']:
   ok('Sin escritura directa '+role,h.sql(f"select has_table_privilege('{role}','public.course_formation_groups','update')").stdout.strip()=='f')
  ok('Anon sin RPC',h.sql("select has_function_privilege('anon','public.portal_course_board_read(uuid)','execute')").stdout.strip()=='f')
  result=json.loads(h.sql(move(C,subject,course,'CI-2',1)).stdout);ok('Mover con revisión',result['revision']==2 and result['saved'])
  ok('Nota e inscripción conservadas',h.sql(f"select score from public.enrollment_grades where enrollment_id='{enrollment}'").stdout.strip()=='85.00')
  h.sql(move(C,subject,course,'CI-1',1),ok=False);ok('Conflicto de revisión bloqueado')
  for group in ['CI-3','1F-6','3T-8','CI-2;drop']:
   h.sql(move(C,subject,course,group,2),ok=False);ok('Destino inválido rechazado')
  for bad_subject,bad_course,bad_period in [(h.uid(999),course,PER),(subject,h.uid(999),PER),(subject,course,PER2)]:
   h.sql(move(C,bad_subject,bad_course,'CI-1',2,bad_period),ok=False);ok('No mezcla IDs o periodos')
  h.sql(move(C,subject,course,None,2));c=next(x for x in read()['classes'] if x['id']==course);ok('Sin clasificar conserva fila',c['group_code'] is None and c['revision']==3)
  label=json.loads(h.sql(h.actor(C,'select public.portal_course_groups_read()')).stdout);ok('Contrato de etiquetas admite null',next(x for x in label['items'] if x['course_id']==course)['revision']==3)
  h.sql(move(C,subject,course,'2F-3',3));ok('Reasignar conserva nota',h.sql('select score from public.enrollment_grades').stdout.strip()=='85.00')
  fresh=next(s for s in data['subjects'] if s['id'] not in {x['subject_id'] for x in data['classes']})
  result=json.loads(h.sql(move(C,fresh['id'],None,'1T-2',0)).stdout);ok('Abrir desde catálogo',result['created'] and result['saved'])
  h.sql(move(C,fresh['id'],None,'1T-1',0),ok=False);ok('Alta concurrente no duplica')
  ok('Solo una clase nueva',len(read()['classes'])==135)
  h.sql(move(C,subject,None,'CI-1',0,PER2));ok('Nueva clase conserva periodo previo',len(read(period=PER2)['classes'])==1 and len(read()['classes'])==135)
  h.sql(move(C,subject,None,None,0,PER2),ok=False);ok('Alta sin curso rechazada')
  h.sql(f"update public.course_offerings set active=false where id='{course}'")
  ok('Inactiva visible en tablero',next(x for x in read()['classes'] if x['id']==course)['active'] is False)
  ok('Auditoría registrada',int(h.sql("select count(*) from public.management_events where action='class_group_saved'").stdout)>0)
  print('PASS '+str(checks)+' comprobaciones SQL del organizador; PostgreSQL local sin producción.')
 finally:h.run('docker','rm','-f',h.NAME,check=False)
if __name__=='__main__':main()
