"""Archivos personales en PostgreSQL/RLS desechable. No prueba el transporte de Storage real."""
import concurrent.futures,json,time
import run_learning_local as h
A=h.uid(1100);B=h.uid(1101);C=h.uid(1102);P=h.uid(1103);IC=h.uid(1104);OFF=h.uid(1105);N=h.uid(1106)
checks=0

def ok(name,value=True):
 global checks
 assert value,name
 checks+=1;print('PASS '+name,flush=True)
def q(action='list',who=A,student=A,data=None,commit=True):return h.actor(who,'select public.portal_student_files('+','.join([h.quote(action),h.quote(student),h.quote(json.dumps(data or {}))+'::jsonb'])+')',commit=commit)
def call(action='list',who=A,student=A,data=None):return json.loads(h.sql(q(action,who,student,data)).stdout)
def reserve(who=A,student=A,kind='bautismo',name='Boleta.pdf',size=20):return call('reserve',who,student,{'kind':kind,'name':name,'size':size})['item']
def blob(f,who=A,mime='application/pdf',size=None,path=None,owner=None):return h.actor(who,"insert into storage.objects(bucket_id,name,owner_id,metadata)values('portal-personal',"+h.quote(path or f['object_path'])+','+h.quote(owner or who)+','+h.quote(json.dumps({'size':size if size is not None else f['size'],'mimetype':mime}))+"::jsonb)",commit=True)
def complete(f,who=A,student=A):return call('complete',who,student,{'id':f['id']})
def remove(f,who=A,student=A):return call('remove',who,student,{'id':f['id']})
def release(f,who=A,student=A):return call('release',who,student,{'id':f['id']})

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
  for uid,role,active in [(A,'student',True),(B,'student',True),(C,'control_escolar',True),(P,'professor',True),(IC,'control_escolar',False),(OFF,'student',False)]:
   h.sql(f"insert into auth.users values('{uid}','{uid}@example.invalid');insert into public.profiles(id,full_name,role,active)values('{uid}','Persona ficticia {uid[-3:]}','{role}',{str(active).lower()})")
  bucket=json.loads(h.sql("select to_jsonb(b)from storage.buckets b where id='portal-personal'").stdout)
  ok('Bucket privado, solo PDF y límite 5 MiB',not bucket['public'] and bucket['file_size_limit']==5242880 and bucket['allowed_mime_types']==['application/pdf'])
  ok('Los buckets de clases siguen presentes',h.sql("select count(*)from storage.buckets where id in('portal-coursework','portal-content')").stdout.strip()=='2')
  ok('Tabla privada sin acceso directo',h.sql("select has_table_privilege('authenticated','public.student_record_files','select,insert,update,delete')").stdout.strip()=='f')
  ok('Tabla con RLS activo',h.sql("select relrowsecurity from pg_class where oid='public.student_record_files'::regclass").stdout.strip()=='t')
  ok('Anon no ejecuta RPC',h.sql("select has_function_privilege('anon','public.portal_student_files(text,uuid,jsonb)','execute')").stdout.strip()=='f')
  for who in [P,IC,OFF,N]:
   ok('Solo alumno propio o Control activo consulta','42501'in h.sql(q(who=who),ok=False).stderr)
  ok('Otro alumno no consulta el expediente','42501'in h.sql(q(who=B),ok=False).stderr)
  ok('No hay archivos inventados',call()['items']==[] and call()['max_files']==10)
  for data in [{'kind':'bad','name':'x.pdf','size':20},{'kind':'bautismo','name':'x.docx','size':20},{'kind':'bautismo','name':'../x.pdf','size':20},{'kind':'bautismo','name':'x.pdf','size':0},{'kind':'bautismo','name':'x.pdf','size':5242881},{'kind':'bautismo','name':'x.pdf','size':20.5},{'kind':'bautismo','name':'x.pdf','size':20,'student_id':B}]:
   ok('Reserva inválida rechazada','22023'in h.sql(q('reserve',data=data),ok=False).stderr)
  # Simula una política antigua excesivamente permisiva: las guardas del nuevo bucket deben prevalecer.
  h.sql('grant usage on schema storage to anon;grant select,insert,update,delete on storage.objects to anon;create policy fixture_broad on storage.objects for all to public using(true)with check(true)')
  f=reserve(name='Boleta de bautismo á.pdf');ok('Reserva cuenta y crea ruta sin nombres personales',f['state']=='pending' and f['object_path']==A+'/'+f['id']+'.pdf' and len(call()['items'])==1)
  ok('No se confirma un objeto que falta','22023'in h.sql(q('complete',data={'id':f['id']}),ok=False).stderr)
  for who in [B,P,IC,OFF]:ok('Storage no permite leer por ruta ajena',h.sql(h.actor(who,"select public._student_file_authorized("+h.quote(f['object_path'])+",'read')")).stdout.strip()=='f')
  for who in [B,P,C]:ok('Solo quien reservó sube a esa ruta','42501'in h.sql(blob(f,who),ok=False).stderr)
  ok('Ruta sin reserva no admite objetos','42501'in h.sql(blob(f,path=A+'/'+h.uid(1199)+'.pdf'),ok=False).stderr)
  h.sql(blob(f,mime='text/plain'));ok('MIME incorrecto no confirma','22023'in h.sql(q('complete',data={'id':f['id']}),ok=False).stderr)
  h.sql("update storage.objects set metadata=jsonb_build_object('mimetype','application/pdf','size',21)where name="+h.quote(f['object_path']))
  ok('Tamaño debe coincidir con la reserva','22023'in h.sql(q('complete',data={'id':f['id']}),ok=False).stderr)
  h.sql("update storage.objects set metadata=jsonb_build_object('mimetype','application/pdf','size',20)where name="+h.quote(f['object_path']))
  ok('Alumno confirma su PDF',complete(f)['item']['state']=='ready')
  ok('Anon no ve metadata aunque exista política genérica amplia',h.sql(h.actor(None,"select count(*)from storage.objects where bucket_id='portal-personal'",role='anon')).stdout.strip()=='0')
  ok('Anon tampoco inserta con política genérica amplia','42501'in h.sql(h.actor(None,"insert into storage.objects(bucket_id,name,owner_id)values('portal-personal','falso.pdf','anon')",role='anon',commit=True),ok=False).stderr)
  ok('Confirmar dos veces es idempotente',complete(f)['item']['state']=='ready' and h.sql("select count(*)from public.management_events where action='student_file_uploaded'").stdout.strip()=='1')
  for who,count in [(A,1),(C,1),(B,0),(P,0),(IC,0),(OFF,0)]:
   ok('Descarga/metadata privada por RLS '+who[-3:],h.sql(h.actor(who,"select count(*)from storage.objects where bucket_id='portal-personal'")).stdout.strip()==str(count))
  h.sql('grant update on storage.objects to authenticated')
  unchanged=h.sql("select metadata from storage.objects where name="+h.quote(f['object_path'])).stdout
  result=h.sql(h.actor(A,"update storage.objects set metadata='{}' where bucket_id='portal-personal' returning name",commit=True))
  ok('RLS impide sobrescribir incluso con permiso UPDATE general',not result.stdout.strip()and h.sql("select metadata from storage.objects where name="+h.quote(f['object_path'])).stdout==unchanged)
  ok('Archivo confirmado no admite otra inserción','42501'in h.sql(blob(f),ok=False).stderr)
  ok('Rutas malformadas no dan acceso',h.sql(h.actor(C,"select public._student_file_authorized('../otro.pdf','read')")).stdout.strip()=='f')
  ce=reserve(C,A,kind='seguro_medico',name='Seguro.pdf');h.sql(blob(ce,C));complete(ce,C)
  ok('Control sube en expediente y alumno descarga aunque no sea owner del objeto',len(call()['items'])==2 and h.sql(h.actor(A,"select count(*)from storage.objects where bucket_id='portal-personal'")).stdout.strip()=='2')
  ok('Control no puede confirmar una reserva del alumno','42501'in h.sql(q('complete',C,A,{'id':f['id']}),ok=False).stderr)
  ok('No hay DELETE directo antes de confirmar retirada',h.sql(h.actor(A,"delete from storage.objects where name="+h.quote(f['object_path'])+" returning name",commit=True)).stdout.strip()=='')
  remove(f,C);ok('Retirada marca estado antes de tocar Storage',next(x for x in call()['items']if x['id']==f['id'])['state']=='deleting')
  ok('No libera registro mientras existe objeto','PT409'in h.sql(q('release',C,A,{'id':f['id']}),ok=False).stderr)
  ok('Objeto en retirada no puede subirse otra vez',h.sql(h.actor(A,"select public._student_file_authorized("+h.quote(f['object_path'])+",'insert')")).stdout.strip()=='f')
  h.sql(h.actor(C,"delete from storage.objects where name="+h.quote(f['object_path']),commit=True));release(f,C)
  ok('Control retira el archivo y libera lugar',len(call()['items'])==1)
  ok('Retirada repetida no crea error ni nueva auditoría',release(f,C)['removed'] and h.sql("select count(*)from public.management_events where action='student_file_removed'").stdout.strip()=='1')
  remove(ce);h.sql(h.actor(A,"delete from storage.objects where name="+h.quote(ce['object_path']),commit=True));release(ce)
  ok('Alumno puede quitar documento que cargó Control',call()['items']==[])
  pending=reserve();remove(pending);release(pending);ok('Carga incompleta se limpia aunque no tenga bytes',call()['items']==[])
  for _ in range(9):reserve(B,B)
  stmt=q('reserve',C,B,{'kind':'preparatoria','name':'Certificado.pdf','size':20})
  with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
   results=list(pool.map(lambda _:h.run('docker','exec','-i',h.NAME,'psql','-U','postgres','-X','-q','-t','-A','-v','ON_ERROR_STOP=1',input=stmt,check=False),range(2)))
  ok('Dos cargas simultáneas no superan diez reservas',sum(r.returncode==0 for r in results)==1 and len(call(who=C,student=B)['items'])==10)
  ok('Reservas incompletas también limitan a diez','22023'in h.sql(q('reserve',B,B,{'kind':'bautismo','name':'x.pdf','size':20}),ok=False).stderr)
  for kind in ['comunion','confirmacion','otros_sacramentos','preparatoria','titulo_universitario','otros_estudios','otro']:
   r=reserve(kind=kind);ok('Categoría admitida '+kind,r['kind']==kind)
  ok('Auditoría no guarda nombre personal del archivo',h.sql("select count(*)from public.management_events where details::text like '%Boleta de bautismo%'").stdout.strip()=='0')
  ok('No afecta los datos básicos del expediente',h.sql('select count(*)from public.student_personal_records').stdout.strip()=='0')
  h.sql(f"update public.profiles set active=false where id='{A}'")
  ok('Revocar cuenta bloquea el acceso inmediatamente','42501'in h.sql(q(),ok=False).stderr)
  ok('Control conserva acceso a expediente de alumno inactivo',len(call(who=C)['items'])==7)
  print('PASS '+str(checks)+' comprobaciones SQL de archivos personales; sin producción.')
 finally:h.run('docker','rm','-f',h.NAME,check=False)
if __name__=='__main__':main()
