-- Clasificación de clases por curso formativo (CI-1, 1F-1, etc.). Aplicar una vez.
-- No cambia materias, notas, inscripciones ni asignaciones existentes.
begin;
create table public.course_formation_groups (
    course_id uuid primary key references public.course_offerings(id) on delete cascade,
    group_code text not null check(group_code ~ '^(CI-[12]|[1-3]F-[1-6]|[1-4]T-[1-8])$'),
    weekly_periods smallint check(weekly_periods between 1 and 50),
    planned_professor text check(char_length(planned_professor)<=200),
    source text,
    revision integer not null default 1 check(revision>0),
    updated_by uuid references public.profiles(id) on delete restrict,
    updated_at timestamptz not null default now(),
    check(group_code like 'CI-%' or left(group_code,1)::integer=(right(group_code,1)::integer+1)/2)
);
alter table public.course_formation_groups enable row level security;
revoke all on public.course_formation_groups from public,anon,authenticated;

create function public.portal_course_groups_read()
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare person public.profiles%rowtype; result jsonb;
begin
    select * into person from public.profiles where id=auth.uid() and active;
    if person.id is null then raise exception using errcode='42501',message='Acceso no autorizado'; end if;
    select coalesce(jsonb_agg(to_jsonb(x) order by x.code,x.period_name),'[]') into result from (
        select c.id as course_id,s.code,p.name as period_name,g.group_code,g.revision,
            case when person.role='control_escolar' then g.weekly_periods end as weekly_periods,
            case when person.role='control_escolar' then g.planned_professor end as planned_professor
        from public.course_formation_groups g join public.course_offerings c on c.id=g.course_id
        join public.subjects s on s.id=c.subject_id join public.academic_periods p on p.id=c.period_id
        where person.role='control_escolar' or public._learning_can_course(c.id)
    ) x;
    return jsonb_build_object('items',result);
end;
$$;

create function public.portal_course_group_save(p_course uuid,p_group text,p_revision integer)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; old public.course_formation_groups%rowtype; saved public.course_formation_groups%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_group is null or p_group !~ '^(CI-[12]|[1-3]F-[1-6]|[1-4]T-[1-8])$'
        or (p_group not like 'CI-%' and left(p_group,1)::integer<>(right(p_group,1)::integer+1)/2)
        or p_revision is null or p_revision<0 then
        raise exception using errcode='22023',message='Selecciona un curso formativo válido'; end if;
    perform id from public.course_offerings where id=p_course for share;
    if not found then raise exception using errcode='22023',message='Clase no encontrada'; end if;
    select * into old from public.course_formation_groups where course_id=p_course for update;
    if coalesce(old.revision,0)<>p_revision then raise exception using errcode='PT409',message='El curso cambió. Actualiza la lista antes de guardar.'; end if;
    insert into public.course_formation_groups(course_id,group_code,updated_by)
        values(p_course,p_group,actor)
    on conflict(course_id) do update set group_code=excluded.group_code,
        revision=public.course_formation_groups.revision+1,updated_by=actor,updated_at=now()
    returning * into saved;
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,'class_group_saved',p_course,jsonb_build_object('before',old.group_code,'after',p_group));
    return jsonb_build_object('saved',true,'group_code',saved.group_code,'revision',saved.revision);
end;
$$;
-- Listado de Control Escolar: búsqueda y orden por curso, no por código interno.
create function public.portal_course_classes_read(p_active_only boolean default false,p_search text default '',p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare result jsonb; needle text:=lower(btrim(coalesce(p_search,'')));
begin
    perform public._require_control_catalog_access();
    if p_active_only is null or p_offset is null or p_offset<0 or p_offset>100000
       or p_limit is null or p_limit not between 1 and 100 or char_length(needle)>160 then
        raise exception using errcode='22023',message='Consulta inválida'; end if;
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
        select c.id,c.subject_id,c.period_id,c.active,s.code,s.name as subject_name,p.name as period_name,p.starts_on,p.ends_on,
            g.group_code,coalesce(g.revision,0) as group_revision,
            (select count(*) from public.enrollments e join public.profiles a on a.id=e.student_id
             where e.subject_id=c.subject_id and e.period_id=c.period_id and e.active and a.active and a.role='student') as students,
            (select count(*) from public.teaching_assignments t join public.profiles a on a.id=t.professor_id
             where t.subject_id=c.subject_id and t.period_id=c.period_id and t.active and a.active and a.role in ('professor','control_escolar')) as professors
        from public.course_offerings c join public.subjects s on s.id=c.subject_id
        join public.academic_periods p on p.id=c.period_id left join public.course_formation_groups g on g.course_id=c.id
        where (not p_active_only or c.active) and (needle='' or strpos(lower(coalesce(g.group_code,'')||' '||s.name||' '||p.name),needle)>0)
        order by p.starts_on desc,case when g.group_code like 'CI-%' then 0 when g.group_code like '%F-%' then 1 when g.group_code like '%T-%' then 2 else 3 end,
            right(g.group_code,1),s.name,c.id offset p_offset limit p_limit+1
    ) x;
    return jsonb_build_object('items',case when jsonb_array_length(result)>p_limit then result-p_limit else result end,'has_more',jsonb_array_length(result)>p_limit);
end;
$$;
revoke all on function public.portal_course_classes_read(boolean,text,integer,integer) from public,anon,authenticated;
grant execute on function public.portal_course_classes_read(boolean,text,integer,integer) to authenticated;
revoke all on function public.portal_course_groups_read(),public.portal_course_group_save(uuid,text,integer) from public,anon,authenticated;
grant execute on function public.portal_course_groups_read(),public.portal_course_group_save(uuid,text,integer) to authenticated;
commit;
