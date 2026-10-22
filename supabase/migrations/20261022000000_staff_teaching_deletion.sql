-- Aplicar después de 20261021090000_learning_files.sql.
-- Instala capacidades; no asigna personas ni elimina ningún registro existente.
begin;

-- Una cuenta de Control Escolar conserva su rol y también puede impartir clases.
alter policy "Active professors read own teaching assignments"
    on public.teaching_assignments using (
        professor_id=(select auth.uid()) and exists (
            select 1 from public.profiles p where p.id=(select auth.uid())
                and p.active and p.role in ('professor','control_escolar')));

create or replace function public.portal_admin_read(p_resource text,p_search text default '',p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; needle text:=lower(btrim(coalesce(p_search,'')));
begin
    perform public._require_control_catalog_access();
    if p_offset is null or p_offset<0 or p_offset>100000 or p_limit is null or p_limit<1 or p_limit>100
       or char_length(needle)>160 then raise exception using errcode='22023',message='Consulta inválida'; end if;
    if p_resource in ('people','students','professors') then
        select coalesce(jsonb_agg(to_jsonb(rows)), '[]'::jsonb) into result from (
            select p.id,p.full_name,p.role,p.active,p.management_revision,u.email
            from public.profiles p join auth.users u on u.id=p.id
            where (p_resource='people' or p.active and (p_resource='students' and p.role='student' or p_resource='professors' and p.role in ('professor','control_escolar')))
              and (needle='' or strpos(lower(p.full_name||' '||coalesce(u.email,'')),needle)>0)
            order by p.full_name,p.id offset p_offset limit p_limit+1
        ) rows;
    elsif p_resource in ('classes','active_classes') then
        select coalesce(jsonb_agg(to_jsonb(rows)), '[]'::jsonb) into result from (
            select c.id,c.subject_id,c.period_id,c.active,s.code,s.name as subject_name,
                a.name as period_name,a.starts_on,a.ends_on,
                (select count(*) from public.enrollments e join public.profiles p on p.id=e.student_id
                 where e.subject_id=c.subject_id and e.period_id=c.period_id and e.active and p.active and p.role='student') as students,
                (select count(*) from public.teaching_assignments t join public.profiles p on p.id=t.professor_id
                 where t.subject_id=c.subject_id and t.period_id=c.period_id and t.active and p.active and p.role in ('professor','control_escolar')) as professors
            from public.course_offerings c join public.subjects s on s.id=c.subject_id join public.academic_periods a on a.id=c.period_id
            where (p_resource='classes' or c.active) and (needle='' or strpos(lower(s.code||' '||s.name||' '||a.name),needle)>0)
            order by a.starts_on desc,s.code,c.id offset p_offset limit p_limit+1
        ) rows;
    elsif p_resource in ('enrollments','assignments') then
        select coalesce(jsonb_agg(to_jsonb(rows)), '[]'::jsonb) into result from (
            select x.id,x.person_id,p.full_name,x.active,c.id as class_id,s.name as subject_name,a.name as period_name,
                case when g.published then g.score else null end as published_score
            from (
                select e.id,e.student_id as person_id,e.subject_id,e.period_id,e.active from public.enrollments e where p_resource='enrollments'
                union all select t.id,t.professor_id,t.subject_id,t.period_id,t.active from public.teaching_assignments t where p_resource='assignments'
            ) x join public.profiles p on p.id=x.person_id join public.subjects s on s.id=x.subject_id
            join public.academic_periods a on a.id=x.period_id join public.course_offerings c on c.subject_id=x.subject_id and c.period_id=x.period_id
            left join public.enrollment_grades g on g.enrollment_id=x.id and p_resource='enrollments'
            where needle='' or strpos(lower(p.full_name||' '||s.name||' '||a.name),needle)>0
            order by p.full_name,s.name,x.id offset p_offset limit p_limit+1
        ) rows;
    elsif p_resource='events' then
        select coalesce(jsonb_agg(to_jsonb(rows)), '[]'::jsonb) into result from (
            select e.id,e.action,p.full_name as actor_name,e.created_at,e.details from (select id,actor_id,action,details,created_at from public.management_events union all select id,actor_id,action,details,created_at from public.catalog_events) e join public.profiles p on p.id=e.actor_id
            order by e.created_at desc,e.id offset p_offset limit p_limit+1
        ) rows;
    else raise exception using errcode='22023',message='Sección inválida'; end if;
    return jsonb_build_object('items', (select coalesce(jsonb_agg(v),'[]'::jsonb) from jsonb_array_elements(result) with ordinality as j(v,n) where n<=p_limit),
                             'has_more',jsonb_array_length(result)>p_limit);
end;
$$;

create or replace function public.portal_admin_write(p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; target uuid; c public.course_offerings%rowtype; person public.profiles%rowtype;
    value text; target_role text; enabled boolean; entity uuid; changed integer; before_data jsonb;
begin
    -- Orden único para cambios de administración, incluso bajas cruzadas entre dos responsables.
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_data is null or jsonb_typeof(p_data)<>'object' then raise exception using errcode='22023',message='Datos inválidos'; end if;
    if p_action='class_create' then
        perform id from public.subjects where id=(p_data->>'subject_id')::uuid for share;
        if not found then raise exception using errcode='22023',message='Selecciona una materia'; end if;
        perform id from public.academic_periods where id=(p_data->>'period_id')::uuid for share;
        if not found then raise exception using errcode='22023',message='Selecciona un periodo'; end if;
        insert into public.course_offerings(subject_id,period_id) values ((p_data->>'subject_id')::uuid,(p_data->>'period_id')::uuid) returning id into entity;
    elsif p_action in ('enroll','assign') then
        select * into c from public.course_offerings where id=(p_data->>'class_id')::uuid and active for share;
        if not found then raise exception using errcode='22023',message='Selecciona una clase activa'; end if;
        target_role:=case when p_action='enroll' then 'student' else 'professor' end;
        select * into person from public.profiles where id=(p_data->>'person_id')::uuid and active and (role=target_role or p_action='assign' and role='control_escolar') for share;
        if not found then raise exception using errcode='22023',message='Selecciona una persona activa con el rol correcto'; end if;
        if p_action='enroll' then
            insert into public.enrollments as e(student_id,subject_id,period_id) values(person.id,c.subject_id,c.period_id)
            on conflict(student_id,subject_id,period_id) do update set active=true where not e.active returning id into entity;
        else
            insert into public.teaching_assignments as t(professor_id,subject_id,period_id) values(person.id,c.subject_id,c.period_id)
            on conflict(professor_id,subject_id,period_id) do update set active=true where not t.active returning id into entity;
        end if;
        if entity is null then raise exception using errcode='PT409',message='La persona ya está asignada a esta clase'; end if;
    elsif p_action in ('class_state','enrollment_state','assignment_state') then
        if jsonb_typeof(p_data->'active') is distinct from 'boolean' then raise exception using errcode='22023',message='Estado inválido'; end if;
        enabled:=(p_data->>'active')::boolean; entity:=(p_data->>'id')::uuid;
        if p_action='class_state' then update public.course_offerings set active=enabled where id=entity;
        elsif p_action='enrollment_state' then update public.enrollments set active=enabled where id=entity;
        else update public.teaching_assignments set active=enabled where id=entity; end if;
        get diagnostics changed=row_count;
        if changed<>1 then raise exception using errcode='22023',message='No se encontró el registro'; end if;
    elsif p_action='person_update' then
        entity:=(p_data->>'id')::uuid;
        select * into person from public.profiles where id=entity for update;
        if not found then raise exception using errcode='22023',message='Persona no encontrada'; end if;
        if jsonb_typeof(p_data->'revision') is distinct from 'number' or (p_data->>'revision')::integer<>person.management_revision then
            raise exception using errcode='PT409',message='La persona cambió; actualiza la lista'; end if;
        value:=btrim(p_data->>'full_name'); target_role:=p_data->>'role';
        if not public._catalog_text_has_content(value) or char_length(value)>160 or value ~ '[[:cntrl:]]'
           or target_role is null or target_role not in ('student','professor','control_escolar') or jsonb_typeof(p_data->'active') is distinct from 'boolean' then
            raise exception using errcode='22023',message='Nombre, rol o estado inválidos'; end if;
        enabled:=(p_data->>'active')::boolean;
        if entity=actor and (not enabled or target_role<>'control_escolar') then
            raise exception using errcode='22023',message='No puedes quitarte tu propio acceso de Control Escolar'; end if;
        if target_role<>person.role and (exists(select 1 from public.enrollments where student_id=entity) or exists(select 1 from public.teaching_assignments where professor_id=entity) and not (person.role in ('professor','control_escolar') and target_role in ('professor','control_escolar'))) then
            raise exception using errcode='22023',message='El rol de una persona con historial académico no se puede cambiar'; end if;
        before_data:=jsonb_build_object('full_name',person.full_name,'role',person.role,'active',person.active);
        update public.profiles set full_name=value,role=target_role,active=enabled,management_revision=management_revision+1 where id=entity;
    elsif p_action='subject_update' then
        entity:=(p_data->>'id')::uuid; value:=btrim(p_data->>'name');
        if not public._catalog_text_has_content(value) or char_length(value)>160 or value ~ '[[:cntrl:]]'
           or not public._catalog_text_has_content(p_data->>'code') or char_length(btrim(p_data->>'code'))>40 or (p_data->>'code') ~ '[[:cntrl:]]' then
            raise exception using errcode='22023',message='Materia inválida'; end if;
        update public.subjects set name=value,code=upper(btrim(p_data->>'code')) where id=entity;
        if not found then raise exception using errcode='22023',message='Materia no encontrada'; end if;
    elsif p_action='period_update' then
        entity:=(p_data->>'id')::uuid; value:=btrim(p_data->>'name');
        if not public._catalog_text_has_content(value) or char_length(value)>120 or value ~ '[[:cntrl:]]'
           or p_data->>'starts_on' is null or p_data->>'ends_on' is null
           or not isfinite((p_data->>'starts_on')::date) or not isfinite((p_data->>'ends_on')::date)
           or (p_data->>'starts_on')::date<date '0001-01-01' or (p_data->>'ends_on')::date>date '9999-12-31'
           or (p_data->>'ends_on')::date<(p_data->>'starts_on')::date then raise exception using errcode='22023',message='Periodo inválido'; end if;
        update public.academic_periods set name=value,starts_on=(p_data->>'starts_on')::date,ends_on=(p_data->>'ends_on')::date where id=entity;
        if not found then raise exception using errcode='22023',message='Periodo no encontrado'; end if;
    else raise exception using errcode='22023',message='Acción inválida'; end if;
    if entity is null then raise exception using errcode='22023',message='Registro inválido'; end if;
    insert into public.management_events(actor_id,action,entity_id,details) values(actor,p_action,entity,jsonb_build_object('after',p_data,'before',before_data));
    return jsonb_build_object('id',entity,'saved',true);
exception when unique_violation then raise exception using errcode='PT409',message='Ya existe un registro con esos datos';
when invalid_text_representation or numeric_value_out_of_range or datetime_field_overflow then raise exception using errcode='22023',message='Datos inválidos';
end;
$$;
revoke all on function public.portal_admin_read(text,text,integer,integer),public.portal_admin_write(text,jsonb) from public,anon,authenticated;
grant execute on function public.portal_admin_read(text,text,integer,integer),public.portal_admin_write(text,jsonb) to authenticated;

create or replace function public.get_teaching_roster(
    p_assignment_id uuid,
    p_offset integer default 0,
    p_limit integer default 20
)
returns table (enrollment_id uuid, student_name text)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    actor uuid := auth.uid();
    assigned_subject uuid;
    assigned_period uuid;
begin
    select t.subject_id, t.period_id into assigned_subject, assigned_period
    from public.teaching_assignments t
    join public.profiles p on p.id = t.professor_id
    where t.id = p_assignment_id and t.professor_id = actor
      and p.active = true and p.role in ('professor','control_escolar') and t.active
      and public._portal_class_active(t.subject_id,t.period_id);

    if not found then
        raise exception using errcode = '42501', message = 'No tienes acceso a esta lista';
    end if;
    if p_offset is null or p_offset < 0 or p_offset > 100000
       or p_limit is null or p_limit < 1 or p_limit > 100 then
        raise exception using errcode = '22023', message = 'Paginación inválida';
    end if;

    return query
        select e.id, p.full_name
        from public.enrollments e
        join public.profiles p on p.id = e.student_id
        where e.subject_id = assigned_subject and e.period_id = assigned_period
          and p.active = true and p.role = 'student' and e.active
        order by p.full_name asc, e.id asc
        offset p_offset limit p_limit;
end;
$$;


create or replace function public._lock_teaching_grade(p_assignment_id uuid, p_enrollment_id uuid)
returns void
language plpgsql volatile security definer set search_path = ''
as $$
begin
    perform e.id
    from public.enrollments e
    join public.teaching_assignments t
      on t.subject_id = e.subject_id and t.period_id = e.period_id
    join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
    join public.profiles teacher on teacher.id = t.professor_id
    join public.profiles student on student.id = e.student_id
    where e.id = p_enrollment_id and t.id = p_assignment_id
      and t.professor_id = auth.uid() and t.active and e.active and c.active
      and teacher.active = true and teacher.role in ('professor','control_escolar')
      and student.active = true and student.role = 'student'
    for update of e
    for share of t, teacher, student, c;
    if not found then
        raise exception using errcode = '42501', message = 'No tienes acceso a esta calificación';
    end if;
end;
$$;
revoke all privileges on function public._lock_teaching_grade(uuid, uuid)
    from public, anon, authenticated;

create or replace function public.get_teaching_grade(p_assignment_id uuid, p_enrollment_id uuid)
returns table (
    enrollment_id uuid, published_score numeric, draft_score numeric,
    revision integer, has_unpublished_changes boolean
)
language plpgsql stable security definer set search_path = ''
as $$
begin
    if not exists (
        select 1 from public.enrollments e
        join public.teaching_assignments t
          on t.subject_id = e.subject_id and t.period_id = e.period_id
        join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
    join public.profiles teacher on teacher.id = t.professor_id
        join public.profiles student on student.id = e.student_id
        where e.id = p_enrollment_id and t.id = p_assignment_id
          and t.professor_id = auth.uid() and t.active and e.active and c.active
          and teacher.active = true and teacher.role in ('professor','control_escolar')
          and student.active = true and student.role = 'student'
    ) then
        raise exception using errcode = '42501', message = 'No tienes acceso a esta calificación';
    end if;
    return query
        select e.id,
               case when g.published then g.score else null end,
               coalesce(d.score, case when g.published = false then g.score else null end),
               coalesce(d.revision, 0),
               coalesce(d.needs_publication, false)
        from public.enrollments e
        left join public.enrollment_grades g on g.enrollment_id = e.id
        left join public.enrollment_grade_drafts d on d.enrollment_id = e.id
        where e.id = p_enrollment_id;
end;
$$;


-- La eliminación SQL y la eliminación física en Storage no comparten transacción.
-- Esta bandeja privada conserva las rutas hasta que Storage confirma su borrado.
create table public.portal_file_cleanup (
    object_path text primary key,
    deleted_course_id uuid not null,
    requested_by uuid not null references public.profiles(id) on delete restrict,
    created_at timestamptz not null default now()
);
alter table public.portal_file_cleanup enable row level security;
revoke all on public.portal_file_cleanup from public,anon,authenticated;

create function public._portal_delete_snapshot(p_kind text,p_id uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare label text; courses uuid[]; enrollment_ids uuid[]; tasks uuid[]; topics uuid[];
    counts jsonb; result jsonb;
begin
    if p_kind='class' then
        select s.code||' · '||s.name||' · '||a.name into label
        from public.course_offerings c join public.subjects s on s.id=c.subject_id
        join public.academic_periods a on a.id=c.period_id where c.id=p_id;
    elsif p_kind='subject' then
        select s.code||' · '||s.name into label from public.subjects s where s.id=p_id;
    elsif p_kind='period' then
        select a.name into label from public.academic_periods a where a.id=p_id;
    else raise exception using errcode='22023',message='Tipo de registro inválido'; end if;
    if label is null then raise exception using errcode='22023',message='El registro ya no existe; actualiza la lista'; end if;
    select coalesce(array_agg(c.id order by c.id),'{}'::uuid[]) into courses
      from public.course_offerings c where (p_kind='class' and c.id=p_id)
        or (p_kind='subject' and c.subject_id=p_id) or (p_kind='period' and c.period_id=p_id);
    select coalesce(array_agg(e.id order by e.id),'{}'::uuid[]) into enrollment_ids
      from public.enrollments e where (p_kind='subject' and e.subject_id=p_id)
        or (p_kind='period' and e.period_id=p_id)
        or exists(select 1 from public.course_offerings c where c.id=any(courses)
            and c.subject_id=e.subject_id and c.period_id=e.period_id);
    select coalesce(array_agg(t.id order by t.id),'{}'::uuid[]) into tasks
      from public.learning_assignments t where t.course_id=any(courses);
    select coalesce(array_agg(t.id order by t.id),'{}'::uuid[]) into topics
      from public.learning_topics t where t.course_id=any(courses);
    counts:=jsonb_build_object(
        'classes',cardinality(courses),'enrollments',cardinality(enrollment_ids),
        'professors',(select count(*) from public.teaching_assignments t where
            (p_kind='subject' and t.subject_id=p_id) or (p_kind='period' and t.period_id=p_id)
            or exists(select 1 from public.course_offerings c where c.id=any(courses)
                and c.subject_id=t.subject_id and c.period_id=t.period_id)),
        'announcements',(select count(*) from public.learning_announcements n where n.course_id=any(courses)),
        'modules',(select count(*) from public.learning_modules m where m.course_id=any(courses)),
        'topics',cardinality(topics),'assignments',cardinality(tasks),
        'submissions',(select count(*) from public.learning_submissions s where s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids)),
        'grades',(select count(*) from public.learning_grades g where g.assignment_id=any(tasks) or g.enrollment_id=any(enrollment_ids))
          +(select count(*) from public.enrollment_grades g where g.enrollment_id=any(enrollment_ids))
          +(select count(*) from public.enrollment_grade_drafts g where g.enrollment_id=any(enrollment_ids)),
        'history',(select count(*) from public.enrollment_grade_events g where g.enrollment_id=any(enrollment_ids))
          +(select count(*) from public.learning_submission_history h join public.learning_submissions s on s.id=h.submission_id
            where s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids)),
        'events',(select count(*) from public.learning_events e where e.course_id=any(courses)),
        'progress',(select count(*) from public.learning_topic_progress t where t.topic_id=any(topics)),
        'files',(select count(*) from public.learning_submission_files f where f.assignment_id=any(tasks) or f.enrollment_id=any(enrollment_ids)),
        'stored_files',(select count(*) from storage.objects o where o.bucket_id='portal-coursework'
            and lower(split_part(o.name,'/',1))=any(courses::text[])));
    result:=jsonb_build_object('id',p_id,'kind',p_kind,'label',label,'counts',counts,
        'course_ids',to_jsonb(courses),'enrollment_ids',to_jsonb(enrollment_ids),'task_ids',to_jsonb(tasks),'topic_ids',to_jsonb(topics));
    return result||jsonb_build_object('token',md5(result::text));
end;
$$;
revoke all on function public._portal_delete_snapshot(text,uuid) from public,anon,authenticated;

create function public.portal_admin_delete_preview(p_kind text,p_id uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    return public._portal_delete_snapshot(p_kind,p_id)-array['course_ids','enrollment_ids','task_ids','topic_ids'];
end;
$$;

create function public.portal_admin_delete(p_kind text,p_id uuid,p_token text,p_confirmation text)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; snapshot jsonb; courses uuid[]; enrollment_ids uuid[]; tasks uuid[]; topics uuid[];
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_confirmation is distinct from 'ELIMINAR' then
        raise exception using errcode='22023',message='Escribe ELIMINAR para confirmar'; end if;
    snapshot:=public._portal_delete_snapshot(p_kind,p_id);
    if p_token is distinct from snapshot->>'token' then
        raise exception using errcode='PT409',message='Los registros cambiaron; cierra y revisa de nuevo la eliminación'; end if;
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into courses from jsonb_array_elements_text(snapshot->'course_ids') j(v);
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into enrollment_ids from jsonb_array_elements_text(snapshot->'enrollment_ids') j(v);
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into tasks from jsonb_array_elements_text(snapshot->'task_ids') j(v);
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into topics from jsonb_array_elements_text(snapshot->'topic_ids') j(v);
    -- Congelar relaciones frente a escritores de notas finales (usan estos bloqueos).
    perform e.id from public.enrollments e where e.id=any(enrollment_ids) order by e.id for update;
    perform c.id from public.course_offerings c where c.id=any(courses) order by c.id for update;
    snapshot:=public._portal_delete_snapshot(p_kind,p_id);
    if p_token is distinct from snapshot->>'token' then
        raise exception using errcode='PT409',message='Los registros cambiaron; cierra y revisa de nuevo la eliminación'; end if;
    insert into public.portal_file_cleanup(object_path,deleted_course_id,requested_by)
        select o.name,lower(split_part(o.name,'/',1))::uuid,actor from storage.objects o
        where o.bucket_id='portal-coursework' and lower(split_part(o.name,'/',1))=any(courses::text[])
        on conflict(object_path) do nothing;
    -- Hijos primero. No se usa CASCADE sobre personas, Auth, otros cursos ni Storage.
    delete from public.learning_submission_files f where f.assignment_id=any(tasks) or f.enrollment_id=any(enrollment_ids);
    delete from public.learning_grades g where g.assignment_id=any(tasks) or g.enrollment_id=any(enrollment_ids);
    delete from public.learning_submission_history h using public.learning_submissions s
        where h.submission_id=s.id and (s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids));
    delete from public.learning_submissions s where s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids);
    delete from public.learning_topic_progress p where p.topic_id=any(topics);
    delete from public.learning_topics t where t.id=any(topics);
    delete from public.learning_modules m where m.course_id=any(courses);
    delete from public.learning_assignments t where t.id=any(tasks);
    delete from public.learning_course_settings s where s.course_id=any(courses);
    delete from public.learning_announcements n where n.course_id=any(courses);
    delete from public.learning_events e where e.course_id=any(courses);
    -- Conservar solo la auditoría administrativa, sin mantener el curso eliminado.
    update public.learning_audit a set details=a.details||jsonb_build_object('deleted_course_id',a.course_id),course_id=null
        where a.course_id=any(courses);
    delete from public.enrollment_grade_events g where g.enrollment_id=any(enrollment_ids);
    delete from public.enrollment_grade_drafts g where g.enrollment_id=any(enrollment_ids);
    delete from public.enrollment_grades g where g.enrollment_id=any(enrollment_ids);
    delete from public.enrollments e where e.id=any(enrollment_ids);
    delete from public.teaching_assignments t where (p_kind='subject' and t.subject_id=p_id)
        or (p_kind='period' and t.period_id=p_id) or exists(select 1 from public.course_offerings c
            where c.id=any(courses) and c.subject_id=t.subject_id and c.period_id=t.period_id);
    delete from public.course_offerings c where c.id=any(courses);
    if p_kind='subject' then delete from public.subjects s where s.id=p_id;
    elsif p_kind='period' then delete from public.academic_periods a where a.id=p_id; end if;
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,p_kind||'_delete',p_id,jsonb_build_object('label',snapshot->>'label','counts',snapshot->'counts'));
    return jsonb_build_object('id',p_id,'saved',true,'pending_files',snapshot->'counts'->'stored_files');
end;
$$;

create function public._portal_cleanup_authorized(p_path text)
returns boolean language sql stable security definer set search_path=''
as $$
    select exists(select 1 from public.profiles p where p.id=auth.uid() and p.active and p.role='control_escolar')
      and exists(select 1 from public.portal_file_cleanup q where q.object_path=p_path)
$$;
revoke all on function public._portal_cleanup_authorized(text) from public,anon,authenticated;
grant execute on function public._portal_cleanup_authorized(text) to authenticated;
-- Storage requiere SELECT y DELETE para eliminar objetos mediante su API oficial.
create policy "Control reads queued coursework for cleanup" on storage.objects for select to authenticated
    using(bucket_id='portal-coursework' and public._portal_cleanup_authorized(name));
create policy "Control deletes queued coursework" on storage.objects for delete to authenticated
    using(bucket_id='portal-coursework' and public._portal_cleanup_authorized(name));

create function public.portal_admin_cleanup_files(p_ack boolean default false)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; total bigint;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    if p_ack then
        -- Nunca confiar solo en el resultado HTTP: comprobar ausencia en Storage.
        delete from public.portal_file_cleanup q where not exists(select 1 from storage.objects o
            where o.bucket_id='portal-coursework' and o.name=q.object_path);
    end if;
    select count(*) into total from public.portal_file_cleanup;
    select coalesce(jsonb_agg(r.object_path),'[]'::jsonb) into result from (
        select q.object_path from public.portal_file_cleanup q order by q.created_at,q.object_path limit 100
    ) r;
    return jsonb_build_object('paths',result,'remaining',total);
end;
$$;
revoke all on function public.portal_admin_delete_preview(text,uuid),
    public.portal_admin_delete(text,uuid,text,text),public.portal_admin_cleanup_files(boolean) from public,anon,authenticated;
grant execute on function public.portal_admin_delete_preview(text,uuid),
    public.portal_admin_delete(text,uuid,text,text),public.portal_admin_cleanup_files(boolean) to authenticated;
commit;
