"""Inicio personal de Control Escolar en PostgreSQL aislado, sin datos reales."""
import json
import run_kardex_local as k
h=k.h


def dashboard(who=h.C,offset=0,limit=100):
    return h.read(who,'dashboard',offset=offset,limit=limit)


def digest(table):
    return h.sql("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text),'[]')::text) from "+table+' t').stdout.strip()


def main():
    k.bootstrap()
    h.sql(f"update public.course_offerings set active=true where id='{h.K}';update public.enrollments set active=true where id='{h.EA}';")
    own,other,global_note,draft_note,own_task,other_task,own_event,other_event,global_event=[h.uid(700+n)for n in range(9)]
    h.sql(f"""
insert into public.learning_announcements(id,course_id,author_id,title,body,published,published_at) values
 ('{own}','{h.K}','{h.C}','Aviso propio','Propio',true,now()),
 ('{other}','{h.L}','{h.C}','Aviso de otra materia','Ajeno',true,now()),
 ('{global_note}',null,'{h.C}','Aviso institucional','Comunidad',true,now()),
 ('{draft_note}',null,'{h.C}','Borrador institucional','Privado',false,null);
insert into public.learning_assignments(id,course_id,title,due_at,published) values
 ('{own_task}','{h.K}','Tarea propia',now()+interval '5 days',true),
 ('{other_task}','{h.L}','Tarea ajena',now()+interval '1 day',true);
insert into public.learning_events(id,course_id,title,starts_at,created_by) values
 ('{own_event}','{h.K}','Evento propio',now()+interval '5 days','{h.C}'),
 ('{other_event}','{h.L}','Evento ajeno',now()+interval '1 day','{h.C}'),
 ('{global_event}',null,'Evento institucional',now()+interval '2 days','{h.C}');
""")
    empty=dashboard()
    h.check('CE sin docencia conserva todos los cursos administrativos',len(empty['courses'])==2)
    h.check('CE sin docencia no recibe tareas de otros',empty['work']==[])
    h.check('CE sin docencia conserva solo avisos y eventos institucionales',
            {x['id']for x in empty['announcements']}=={global_note} and {x['id']for x in empty['events']}=={global_event})
    h.check('puede administrar borradores institucionales',
            {x['id']for x in empty['institutional_announcements']}=={global_note,draft_note})
    h.sql(f"insert into public.teaching_assignments(professor_id,subject_id,period_id)values('{h.C}','{h.S}','{h.T}'),('{h.P}','{h.S}','{h.T}')")
    personal=dashboard()
    h.check('trabajo pendiente solo de titularidades activas', [x['id']for x in personal['work']]==[own_task])
    h.check('avisos propios más institucionales publicados',
            {x['id']for x in personal['announcements']}=={own,global_note})
    h.check('calendario propio más institucional',
            {x['id']for x in personal['events']}=={own_event,global_event})
    h.check('abrir y administrar un curso ajeno sigue permitido',h.read(h.C,'course',h.L)['can_manage'] is True)
    h.check('la evaluación mantiene los campos de ponderación',
            all('grading_category'in x and 'requires_submission'in x for x in h.read(h.C,'course',h.K)['assignments']))
    paged=dashboard(offset=1,limit=1)
    h.check('paginar el directorio no recorta las tareas personales',len(paged['courses'])==1 and [x['id']for x in paged['work']]==[own_task])
    h.check('el alumno conserva sus tareas pendientes', {x['id']for x in dashboard(h.A)['work']}=={own_task,other_task})
    h.sql(f"insert into public.learning_submissions(assignment_id,enrollment_id,body)values('{own_task}','{h.EA}','Entrega de prueba')")
    h.check('una entrega retira solo esa tarea pendiente del alumno', [x['id']for x in dashboard(h.A)['work']]==[other_task])

    # Más actividades ajenas que el límite del inicio: las propias deben seguir allí.
    h.sql(f"""
insert into public.learning_assignments(course_id,title,due_at,published)
 select '{h.L}','Tarea ajena '||n,now()-interval '10 days',true from generate_series(1,70)n;
insert into public.learning_announcements(course_id,author_id,title,body,pinned,published,published_at)
 select '{h.L}','{h.C}','Aviso ajeno '||n,'Ajeno',true,true,now() from generate_series(1,70)n;
insert into public.learning_events(course_id,title,starts_at,created_by)
 select '{h.L}','Evento ajeno '||n,now(),'{h.C}' from generate_series(1,120)n;
""")
    crowded=dashboard()
    h.check('filtra tareas antes del límite de 50', [x['id']for x in crowded['work']]==[own_task])
    h.check('filtra avisos antes del límite de 50', {x['id']for x in crowded['announcements']}=={own,global_note})
    h.check('filtra eventos antes del límite de 100', {x['id']for x in crowded['events']}=={own_event,global_event})
    h.check('los profesores conservan su inicio habitual', [x['id']for x in dashboard(h.P)['work']]==[own_task])
    h.check('los alumnos conservan sus tareas de ambas materias inscritas',len(dashboard(h.A)['work'])==50)

    h.sql(f"update public.teaching_assignments set active=false where professor_id='{h.C}'")
    h.check('una baja docente retira las tareas inmediatamente',dashboard()['work']==[])
    h.sql(f"update public.teaching_assignments set active=true where professor_id='{h.C}';update public.course_offerings set active=false where id='{h.K}'")
    h.check('una clase inactiva no aporta tareas, avisos ni eventos',
            dashboard()['work']==[] and {x['id']for x in dashboard()['events']}=={global_event})
    h.sql(f"update public.course_offerings set active=true where id='{h.K}'")

    # Las asignaciones se resuelven por usuario autenticado, no por autor de la tarea.
    second=h.uid(720)
    h.sql(f"insert into auth.users values('{second}','control2@example.invalid');insert into public.profiles(id,full_name,role)values('{second}','Segundo control ficticio','control_escolar')")
    h.check('otro CE no hereda las tareas del primero',dashboard(second)['work']==[])
    for actor in [h.IC,h.N]:
        h.test('inactivo o sin perfil no consulta el inicio',h.actor(actor,h.rquery('dashboard')),error='42501')
    h.test('anónimo sin acceso',h.actor(None,h.rquery('dashboard'),role='anon'),error='42501')
    for role in ['anon','authenticated']:
        h.test('helper privado '+role,"select has_function_privilege("+h.quote(role)+",'public._learning_control_personal_dashboard(integer,integer)','execute')",'f')
    for offset,limit in [(-1,10),(100001,10),(0,0),(0,101)]:
        h.test('paginación inválida '+str((offset,limit)),h.actor(h.C,h.rquery('dashboard',offset=offset,limit=limit)),error='22023')

    tables=['public.profiles','public.teaching_assignments','public.enrollments','public.enrollment_grades','public.learning_assignments','public.report_card_issues']
    before={t:digest(t)for t in tables}
    h.sql((h.ROOT/'supabase/migrations/20261117000000_control_personal_dashboard.sql').read_text())
    h.check('instalar de nuevo no modifica cuentas, tareas, notas ni boletas',before=={t:digest(t)for t in tables})
    h.check('la reinstalación conserva el filtro', [x['id']for x in dashboard()['work']]==[own_task])
    print(f'PASS {h.checks} comprobaciones del inicio personal; PostgreSQL aislado',flush=True)


if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
