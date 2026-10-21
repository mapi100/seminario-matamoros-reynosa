-- Aplicar una vez, después de 20261021050000_control_catalogs.sql.
-- Administración desde el portal: consultas acotadas, RPC con autorización y auditoría.
begin;
create table public.course_offerings (
    id uuid primary key default gen_random_uuid(),
    subject_id uuid not null references public.subjects(id) on delete restrict,
    period_id uuid not null references public.academic_periods(id) on delete restrict,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    unique(subject_id, period_id)
);
-- Conservar las clases e inscripciones existentes; no cargar materias ficticias.
insert into public.course_offerings(subject_id,period_id)
select subject_id,period_id from public.enrollments
union select subject_id,period_id from public.teaching_assignments;
alter table public.enrollments add column active boolean not null default true;
alter table public.teaching_assignments add column active boolean not null default true;
create index enrollments_active_class_idx on public.enrollments(subject_id,period_id) where active;
create index teaching_active_class_idx on public.teaching_assignments(subject_id,period_id) where active;
alter table public.profiles add column management_revision integer not null default 0;
create table public.management_events (
    id uuid primary key default gen_random_uuid(),
    actor_id uuid not null references public.profiles(id) on delete restrict,
    action text not null,
    entity_id uuid not null,
    details jsonb not null,
    created_at timestamptz not null default now()
);
create index management_events_created_idx on public.management_events(created_at desc,id);
alter table public.course_offerings enable row level security;
alter table public.management_events enable row level security;
revoke all on public.course_offerings, public.management_events from public,anon,authenticated;

-- Booleano sin datos personales, para políticas sin ciclos de RLS.
create function public._portal_class_active(p_subject uuid,p_period uuid)
returns boolean language sql stable security definer set search_path=''
as $$ select exists(select 1 from public.course_offerings c where c.subject_id=p_subject and c.period_id=p_period and c.active) $$;
revoke all on function public._portal_class_active(uuid,uuid) from public,anon,authenticated;
grant execute on function public._portal_class_active(uuid,uuid) to authenticated;
create policy "Enrollment must remain active" on public.enrollments as restrictive
for select to authenticated using (active and public._portal_class_active(subject_id,period_id));
create policy "Teaching assignment must remain active" on public.teaching_assignments as restrictive
for select to authenticated using (active and public._portal_class_active(subject_id,period_id));

create function public.portal_admin_read(p_resource text,p_search text default '',p_offset integer default 0,p_limit integer default 30)
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
            where (p_resource='people' or p.role=case when p_resource='students' then 'student' else 'professor' end and p.active)
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
                 where t.subject_id=c.subject_id and t.period_id=c.period_id and t.active and p.active and p.role='professor') as professors
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

create function public.portal_admin_write(p_action text,p_data jsonb)
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
        select * into person from public.profiles where id=(p_data->>'person_id')::uuid and active and role=target_role for share;
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
        if target_role<>person.role and (exists(select 1 from public.enrollments where student_id=entity) or exists(select 1 from public.teaching_assignments where professor_id=entity)) then
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
      and p.active = true and p.role = 'professor' and t.active
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
      and teacher.active = true and teacher.role = 'professor'
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
          and teacher.active = true and teacher.role = 'professor'
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


commit;
