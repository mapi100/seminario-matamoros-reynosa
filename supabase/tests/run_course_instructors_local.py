"""Docentes visibles por clase: PostgreSQL desechable, sin red ni datos reales."""
import json
import run_kardex_local as k
h=k.h


def board(period=h.T,who=h.C):
    return json.loads(h.sql(h.actor(who,"select public.portal_course_board_read("+h.quote(period)+")")).stdout)


def names(who=h.A,course=h.K):
    return h.read(who,'course',course)['instructors']


def digest(table):
    return h.sql("select md5(coalesce(jsonb_agg(to_jsonb(t)order by to_jsonb(t)::text),'[]')::text)from "+table+' t').stdout.strip()


def main():
    k.bootstrap()
    h.sql(f"update public.course_offerings set active=true where id='{h.K}';update public.enrollments set active=true where id='{h.EA}';update public.profiles set full_name='Pbro. Docente Alfa' where id='{h.P}';update public.profiles set active=true where id='{h.B}'")
    h.check('curso sin asignación devuelve lista vacía',names()==[])
    h.check('el acceso de CE a todo no lo convierte en titular',h.read(h.C,'course',h.L)['instructors']==[])
    female=h.uid(800);second_control=h.uid(801);future_class=h.uid(802);future_assignment=h.uid(803)
    h.sql(f"""
insert into auth.users(id,email)values('{female}','maestra@example.invalid'),('{second_control}','control2@example.invalid');
insert into public.profiles(id,full_name,role)values
 ('{female}','Maestra de ejemplo','professor'),('{second_control}','Segundo Control','control_escolar');
insert into public.teaching_assignments(professor_id,subject_id,period_id)values
 ('{h.P}','{h.S}','{h.T}'),('{female}','{h.S}','{h.T}');
insert into public.course_offerings(id,subject_id,period_id)values('{future_class}','{h.S}','{k.T2}');
insert into public.teaching_assignments(id,professor_id,subject_id,period_id)values
 ('{future_assignment}','{h.C}','{h.S}','{k.T2}');
""")
    expected=[{'name':'Maestra de ejemplo'},{'name':'Pbro. Docente Alfa'}]
    for actor in [h.A,h.P,h.C]:
        h.check('alumno y personal ven los mismos docentes '+actor[-2:],names(actor)==expected)
    row=next(x for x in board()['classes']if x['id']==h.K)
    h.check('tarjeta y aula muestran los mismos nombres',row['instructors']==expected)
    h.check('solo expone el nombre, sin correo, UUID ni datos privados',all(set(x)=={'name'}for x in row['instructors']))
    future=next(x for x in board(k.T2)['classes']if x['id']==future_class)
    h.check('no mezcla titulares de la misma materia en otro periodo',future['instructors']==[{'name':'Control Escolar'}])
    h.check('otro curso conserva su lista vacía',next(x for x in board()['classes']if x['id']==h.L)['instructors']==[])
    h.test('un alumno ajeno no consulta los docentes del curso',h.actor(h.B,h.rquery('course',future_class)),error='42501')
    h.test('un profesor ajeno no consulta otro curso',h.actor(h.P,h.rquery('course',h.L)),error='42501')
    for actor in [h.A,h.P]:
        h.test('no amplía el directorio administrativo '+actor[-2:],h.actor(actor,"select public.portal_course_board_read()"),error='42501')
    h.sql(f"insert into public.teaching_assignments(professor_id,subject_id,period_id)values('{h.C}','{h.S}','{h.T}')")
    h.check('CE aparece como docente solo si está asignado',{'name':'Control Escolar'}in names())
    h.check('CE sin asignación no se añade a la lista',{'name':'Segundo Control'}not in names())
    h.sql(f"update public.teaching_assignments set active=false where professor_id='{h.P}' and period_id='{h.T}'")
    h.check('baja de asignación retira al titular',{'name':'Pbro. Docente Alfa'}not in names())
    h.sql(f"update public.profiles set active=false where id='{female}'")
    h.check('perfil docente inactivo no aparece',{'name':'Maestra de ejemplo'}not in names())
    h.sql(f"update public.profiles set active=true,role='student' where id='{female}'")
    h.check('un perfil convertido a alumno no figura como docente',{'name':'Maestra de ejemplo'}not in names())
    h.sql(f"update public.profiles set role='professor',full_name='Maestra actualizada' where id='{female}'")
    h.check('actualiza el nombre sin una copia desfasada',{'name':'Maestra actualizada'}in names())
    h.sql(f"update public.profiles set active=false where id='{h.C}'")
    h.test('CE inactivo no consulta la clase',h.actor(h.C,h.rquery('course',h.K)),error='42501')
    h.test('CE inactivo no consulta el directorio',h.actor(h.C,'select public.portal_course_board_read()'),error='42501')
    h.sql(f"update public.profiles set active=true where id='{h.C}';update public.enrollments set active=false where id='{h.EA}'")
    h.test('alumno dado de baja no consulta el docente',h.actor(h.A,h.rquery('course',h.K)),error='42501')
    for signature in ['_course_instructor_names(uuid)','_learning_read_before_instructors(text,uuid,integer,integer)']:
        for role in ['anon','authenticated']:
            h.test('helper privado '+role+' '+signature,"select has_function_privilege("+h.quote(role)+','+h.quote('public.'+signature)+",'execute')",'f')
    h.test('anónimo no consulta el curso',h.actor(None,h.rquery('course',h.K),role='anon'),error='42501')
    # Mantener el filtro previo de tareas personales y las asignaciones activas de cada CE.
    h.sql(f"insert into public.learning_assignments(course_id,title,published)values('{h.K}','Actividad propia',true),('{h.L}','Actividad ajena',true)")
    personal=h.read(h.C,'dashboard')
    h.check('conserva el filtro de tareas personales de CE',[x['title']for x in personal['work']]==['Actividad propia'])
    h.check('conserva las categorías en la respuesta del aula',all('grading_category'in x and 'requires_submission'in x for x in h.read(h.C,'course',h.K)['assignments']))
    before={t:digest(t)for t in ['auth.users','public.profiles','public.teaching_assignments','public.enrollments','public.enrollment_grades','public.report_card_issues']}
    h.sql((h.ROOT/'supabase/migrations/20261117010000_course_instructors.sql').read_text())
    h.check('reinstalación sin alterar cuentas, asignaciones, notas ni boletas',before=={t:digest(t)for t in before})
    h.check('reinstalación conserva el filtro personal',[x['title']for x in h.read(h.C,'dashboard')['work']]==['Actividad propia'])
    h.check('reinstalación no duplica docentes',len(names(h.C))==2)
    print(f'PASS {h.checks} comprobaciones SQL de docentes; sin producción',flush=True)


if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
