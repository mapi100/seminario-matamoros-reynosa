import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent));import run_learning_local as h
import argparse
parser=argparse.ArgumentParser(description='Prueba local del SQL de carga privado, sin producción.')
parser.add_argument('--import-sql',type=Path,required=True)
payload=parser.parse_args().import_sql.read_text();checks=0
A=h.uid(100);P=h.uid(101);C=h.uid(102);I=h.uid(103)
def ok(name,condition):
 global checks
 assert condition,name;checks+=1

def rows(who):return json.loads(h.sql(h.actor(who,'select public.portal_course_groups_read()')).stdout)['items']
try:
 h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
 for _ in range(100):
  logs=h.run('docker','logs',h.NAME,check=False)
  if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
  time.sleep(.2)
 else:raise AssertionError('PG no disponible')
 h.sql(h.AUTH);h.sql(h.STORAGE)
 for f in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):h.sql(f.read_text())
 for uid,name,role,active in [(A,'Alumno ficticio','student',True),(P,'Profesor ficticio','professor',True),(C,'Control ficticio','control_escolar',True),(I,'Inactivo ficticio','student',False)]:
  h.sql(f"insert into auth.users values('{uid}','{uid}@example.invalid');insert into public.profiles(id,full_name,role,active)values('{uid}',{h.quote(name)},{h.quote(role)},{str(active).lower()});")
 h.sql(f"""insert into public.subjects(id,code,name)values('{h.S}','BIBL-1001','Introducción a la Biblia');
 insert into public.academic_periods(id,name,starts_on,ends_on)values('{h.T}','Ago-Dic 2026','2026-08-20','2026-12-18');
 insert into public.course_offerings(id,subject_id,period_id)values('{h.K}','{h.S}','{h.T}');
 insert into public.enrollments(id,student_id,subject_id,period_id)values('{h.EA}','{A}','{h.S}','{h.T}');
 insert into public.enrollment_grades(enrollment_id,score,published)values('{h.EA}',80,true);
 insert into public.teaching_assignments(professor_id,subject_id,period_id)values('{P}','{h.S}','{h.T}');""")
 h.sql(payload)
 def count(t):return int(h.sql('select count(*) from public.'+t).stdout)
 ok('134 clases y 134 clasificaciones',count('course_offerings')==134 and count('course_formation_groups')==134)
 ok('Reutiliza materia y clase existentes',h.sql(f"select group_code from public.course_formation_groups where course_id='{h.K}'").stdout.strip()=='CI-1')
 ok('Conserva nota y alumno',count('enrollments')==1 and h.sql('select score from public.enrollment_grades').stdout.strip()=='80.00')
 ok('No asigna docentes adicionales',count('teaching_assignments')==1)
 ok('Conserva fechas del periodo actual',h.sql(f"select starts_on||'/'||ends_on from public.academic_periods where id='{h.T}'").stdout.strip()=='2026-08-20/2026-12-18')
 ok('Enero 1 a mayo 31',h.sql("select starts_on||'/'||ends_on from public.academic_periods where name='Ene-May 2027'").stdout.strip()=='2027-01-01/2027-05-31')
 h.sql(payload);ok('Carga repetible',count('course_offerings')==134 and count('course_formation_groups')==134 and count('academic_periods')==2)
 ok('CE consulta todas',len(rows(C))==134)
 ok('Alumno solo sus clases',len(rows(A))==1)
 ok('Profesor solo asignadas',len(rows(P))==1)
 ok('Alumno sin nombres docentes previstos',rows(A)[0]['planned_professor'] is None)
 ok('CE consulta docente previsto',bool(rows(C)[0]['planned_professor']))
 h.sql(h.actor(I,'select public.portal_course_groups_read()'),ok=False);ok('Inactivo denegado',True)
 for role in ['anon','authenticated']:
  ok('Sin SELECT directo '+role,h.sql(f"select has_table_privilege('{role}','public.course_formation_groups','select')").stdout.strip()=='f')
 ok('Anon sin RPC',h.sql("select has_function_privilege('anon','public.portal_course_groups_read()','execute')").stdout.strip()=='f')
 for actor in [A,P,I]:
  h.sql(h.actor(actor,f"select public.portal_course_group_save('{h.K}','CI-2',1)"),ok=False);ok('No admin no edita',True)
 for group in ['CI-3','1F-6','3T-8','CI-1;drop']:
  h.sql(h.actor(C,f"select public.portal_course_group_save('{h.K}',{h.quote(group)},1)"),ok=False);ok('Curso inválido '+group,True)

 data=json.loads(h.sql(h.actor(C,"select public.portal_course_classes_read(false,'CI-1',0,30)")).stdout)
 ok('Busca CI-1 en el servidor',len(data['items'])==8 and not data['has_more'])
 data=json.loads(h.sql(h.actor(C,"select public.portal_course_classes_read(false,'',0,30)")).stdout)
 ok('Paginación de clases',len(data['items'])==30 and data['has_more'])
 for who in [A,P,I]:
  h.sql(h.actor(who,"select public.portal_course_classes_read()"),ok=False);ok('Listado administrativo no público',True)
 h.sql(h.actor(C,f"select public.portal_course_group_save('{h.K}','CI-2',1)",commit=True))
 ok('Guarda clasificación válida',h.sql(f"select group_code||'/'||revision from public.course_formation_groups where course_id='{h.K}'").stdout.strip()=='CI-2/2')
 h.sql(h.actor(C,f"select public.portal_course_group_save('{h.K}','CI-1',1)"),ok=False);ok('Revisión antigua bloqueada',True)
 h.sql(payload,ok=False);ok('Importar no pisa clasificación manual',h.sql(f"select group_code from public.course_formation_groups where course_id='{h.K}'").stdout.strip()=='CI-2')
 h.sql(f"insert into public.subjects(code,name)values('DUP','  INTRODUCCIÓN A LA BIBLIA  ')")
 h.sql(payload,ok=False);ok('Nombres duplicados abortan',True)
 h.sql("delete from public.subjects where code='DUP'")
 ok('RLS habilitado',h.sql("select relrowsecurity from pg_class where oid='public.course_formation_groups'::regclass").stdout.strip()=='t')
 ok('Sin promociones o datos personales inventados',count('student_formation_periods')==0 and count('student_personal_records')==0)
 print(str(checks)+' comprobaciones SQL/carga aprobadas; sin producción.')
finally:h.run('docker','rm','-f',h.NAME,check=False)
