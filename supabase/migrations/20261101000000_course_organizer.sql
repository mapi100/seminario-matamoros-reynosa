-- Organizador por periodo y selector de clases. Aplicar una vez después de course_formation_groups.
begin;
alter table public.course_formation_groups alter column group_code drop not null;

create function public.portal_course_board_read(p_period uuid default null)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare chosen uuid; periods jsonb; subjects jsonb; classes jsonb;
begin
    perform public._require_control_catalog_access();
    select coalesce(jsonb_agg(to_jsonb(p) order by p.starts_on desc,p.id),'[]') into periods
        from (select id,name,starts_on,ends_on from public.academic_periods) p;
    if p_period is null then
        select id into chosen from public.academic_periods
        order by case when (now() at time zone 'America/Matamoros')::date between starts_on and ends_on then 0 else 1 end,starts_on desc,id limit 1;
    else
        select id into chosen from public.academic_periods where id=p_period;
        if not found then raise exception using errcode='22023',message='El periodo ya no está disponible'; end if;
    end if;
    select coalesce(jsonb_agg(to_jsonb(s) order by s.name,s.id),'[]') into subjects
        from (select id,code,name from public.subjects) s;
    select coalesce(jsonb_agg(to_jsonb(x) order by x.name,x.id),'[]') into classes from (
        select c.id,c.subject_id,c.period_id,c.active,s.name,s.code,p.name as period_name,
            g.group_code,coalesce(g.revision,0) as revision
        from public.course_offerings c join public.subjects s on s.id=c.subject_id
        join public.academic_periods p on p.id=c.period_id left join public.course_formation_groups g on g.course_id=c.id
        where c.period_id=chosen
    ) x;
    return jsonb_build_object('periods',periods,'period_id',chosen,'subjects',subjects,'classes',classes);
end;
$$;

create function public.portal_course_board_write(p_subject uuid,p_period uuid,p_course uuid,p_group text,p_revision integer)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; c public.course_offerings%rowtype; old public.course_formation_groups%rowtype;
    saved public.course_formation_groups%rowtype; created boolean:=false;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_revision is null or p_revision<0 or (p_group is not null and
        (p_group !~ '^(CI-[12]|[1-3]F-[1-6]|[1-4]T-[1-8])$' or
         case when p_group like 'CI-%' then false else left(p_group,1)::integer<>(right(p_group,1)::integer+1)/2 end)) then
        raise exception using errcode='22023',message='Selecciona un curso válido'; end if;
    perform id from public.subjects where id=p_subject for share;
    if not found then raise exception using errcode='22023',message='Materia no encontrada'; end if;
    perform id from public.academic_periods where id=p_period for share;
    if not found then raise exception using errcode='22023',message='Periodo no encontrado'; end if;
    if p_course is null then
        if p_revision<>0 or p_group is null then raise exception using errcode='22023',message='Elige el curso donde abrir la materia'; end if;
        perform id from public.course_offerings where subject_id=p_subject and period_id=p_period;
        if found then raise exception using errcode='PT409',message='La materia ya tiene clase en este periodo. Actualiza el tablero.'; end if;
        insert into public.course_offerings(subject_id,period_id) values(p_subject,p_period) returning * into c;
        created:=true;
    else
        select * into c from public.course_offerings where id=p_course and subject_id=p_subject and period_id=p_period for update;
        if not found then raise exception using errcode='PT409',message='La clase cambió. Actualiza el tablero.'; end if;
    end if;
    select * into old from public.course_formation_groups where course_id=c.id for update;
    if coalesce(old.revision,0)<>p_revision then raise exception using errcode='PT409',message='Otra persona cambió esta clase. Actualiza antes de moverla.'; end if;
    if old.course_id is not null and old.group_code is not distinct from p_group then
        return jsonb_build_object('saved',true,'id',c.id,'revision',old.revision,'created',false);
    end if;
    if old.course_id is null and p_group is null then
        return jsonb_build_object('saved',true,'id',c.id,'revision',0,'created',false);
    end if;
    insert into public.course_formation_groups(course_id,group_code,updated_by)
        values(c.id,p_group,actor)
    on conflict(course_id) do update set group_code=excluded.group_code,revision=public.course_formation_groups.revision+1,
        updated_by=actor,updated_at=now() returning * into saved;
    if created then
        insert into public.management_events(actor_id,action,entity_id,details)
            values(actor,'class_create',c.id,jsonb_build_object('source','organizer','subject_id',p_subject,'period_id',p_period));
    end if;
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,'class_group_saved',c.id,jsonb_build_object('before',old.group_code,'after',p_group,'source','organizer'));
    return jsonb_build_object('saved',true,'id',c.id,'revision',saved.revision,'created',created);
end;
$$;
revoke all on function public.portal_course_board_read(uuid),public.portal_course_board_write(uuid,uuid,uuid,text,integer) from public,anon,authenticated;
grant execute on function public.portal_course_board_read(uuid),public.portal_course_board_write(uuid,uuid,uuid,text,integer) to authenticated;
notify pgrst,'reload schema';
commit;
