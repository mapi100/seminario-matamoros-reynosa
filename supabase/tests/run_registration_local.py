"""Regresión de prefecto y matrícula: solo PostgreSQL desechable y datos ficticios."""
import json
import run_kardex_local as k
h=k.h

def main():
 try:
  k.bootstrap()
  h.test('prefecto confirmado instalado',"select prefect_name from public.kardex_institution",'Pbro. Martín Nicolás Hinojosa')
  current=json.loads(h.sql(h.actor(h.C,"select public.portal_kardex_read('settings')")).stdout)['institution']
  current.update(prefect_name='Prefecto ficticio',revision=current['revision'])
  h.sql(h.actor(h.C,"select public.portal_kardex_write('institution_save',"+h.quote(json.dumps(current))+"::jsonb)",commit=True))
  h.test('prefecto se guarda y se vuelve a leer',"select prefect_name from public.kardex_institution",'Prefecto ficticio')
  def read(student=h.A):return json.loads(h.sql(h.actor(h.C,f"select public.portal_student_record_read('record','{student}')")).stdout)
  def q(who=h.C,student=h.A,num='MR-FICT-001',token=None):return h.actor(who,'select public.portal_student_number_save('+','.join([h.quote(student),h.quote(token or read(student)['token']),h.quote(num)])+')',commit=True)
  before=read();h.sql(q());h.test('matricula compartida con expediente',f"select student_number from public.kardex_students where student_id='{h.A}'",'MR-FICT-001')
  for who in [h.A,h.P,h.IC]:h.test('solo Control cambia matricula',q(who),error='42501')
  h.test('revision antigua rechazada',q(token=before['token']),error='PT409')
  h.sql(q(student=h.B,num='MR-FICT-002'))
  h.test('matricula duplicada no sobreescribe',q(num='MR-FICT-002'),error='PT409')
  h.test('matricula original conservada',f"select student_number from public.kardex_students where student_id='{h.A}'",'MR-FICT-001')
  h.sql(q(num='00000'));h.test('ceros se tratan como pendientes',f"select student_number is null from public.kardex_students where student_id='{h.A}'",'t')
  r=read();details=dict(r['details']);details.update(birth_place='Ciudad ficticia',medical_coverage='Sí',medical_provider='Proveedor ficticio',social_profiles='Perfil ficticio',home_zone='Zona ficticia',home_deanery='Decanato ficticio',registration_course='1o Filosofía',home_phone='No registrado')
  values={'full_name':r['student']['full_name'],'curp':r['identity']['curp'],'birth_date':r['identity']['birth_date'],'details':details}
  h.sql(h.actor(h.C,'select public.portal_student_record_save('+','.join([h.quote(h.A),h.quote(r['token']),h.quote(json.dumps(values))+'::jsonb'])+')',commit=True))
  h.check('nuevos campos personales preservados',read()['details']['medical_provider']=='Proveedor ficticio')
  h.test('anon no cambia matrícula',"select has_function_privilege('anon','public.portal_student_number_save(uuid,text,text)','execute')",'f')
  print('PASS comprobaciones de prefecto, matrícula, conflictos y nuevos campos')
 finally:h.run('docker','rm','-f',h.NAME,check=False)
if __name__=='__main__':main()
