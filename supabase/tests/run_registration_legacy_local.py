"""Compatibilidad: instalación sin extensión de boletas; datos ficticios y sin red."""
import json,time
import run_learning_local as h

def main():
 try:
  h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
  for _ in range(100):
   logs=h.run('docker','logs',h.NAME,check=False)
   if 'PostgreSQL init process complete'in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
   time.sleep(.2)
  h.sql(h.AUTH);h.sql(h.STORAGE)
  repair=h.ROOT/'supabase/migrations/20261104000000_registration_records.sql'
  for p in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):
   if p.name=='20261027000000_semester_report_cards.sql' or p==repair:continue
   h.sql(p.read_text())
  h.test('base de ensayo sin extensión boletas',"select to_regprocedure('public._kardex_write_before_report_cards(text,jsonb)') is null",'t')
  for who,role in [(h.C,'control_escolar'),(h.A,'student')]:
   h.sql(f"insert into auth.users values('{who}','{who}@example.invalid');insert into public.profiles(id,full_name,role)values('{who}','Persona ficticia','{role}')")
  h.sql(repair.read_text());h.sql(repair.read_text())
  h.test('reinstalar no provoca recursión ni pierde prefecto',"select prefect_name from public.kardex_institution",'Pbro. Martín Nicolás Hinojosa')
  institution=json.loads(h.sql(h.actor(h.C,"select public.portal_kardex_read('settings')")).stdout)['institution'];institution['prefect_name']='Prefecto ficticio'
  h.sql(h.actor(h.C,"select public.portal_kardex_write('institution_save',"+h.quote(json.dumps(institution))+"::jsonb)",commit=True))
  h.test('guardado funciona sin boletas',"select prefect_name from public.kardex_institution",'Prefecto ficticio')
  record=json.loads(h.sql(h.actor(h.C,f"select public.portal_student_record_read('record','{h.A}')")).stdout)
  h.sql(h.actor(h.C,f"select public.portal_student_number_save('{h.A}','{record['token']}','FICT-001')",commit=True))
  h.test('matrícula funciona sin boletas',f"select student_number from public.kardex_students where student_id='{h.A}'",'FICT-001')
  h.test('función original no queda expuesta',"select has_function_privilege('authenticated','public._kardex_write_before_registration(text,jsonb)','execute')",'f')
 finally:h.run('docker','rm','-f',h.NAME,check=False)
if __name__=='__main__':main()
