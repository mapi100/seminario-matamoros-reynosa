-- Aplicar una vez, después de 20261022030000_student_personal_record.sql.
begin;

create table public.formation_stages (
    code text primary key,
    name text not null,
    ecclesial_name text not null,
    semesters smallint not null check(semesters>0),
    position smallint not null unique
);
insert into public.formation_stages values
    ('introductorio','Curso Introductorio','Etapa propedéutica',2,1),
    ('filosofia','Filosofía','Etapa discipular',6,2),
    ('teologia','Teología','Etapa configuradora',8,3);

create table public.student_formation_periods (
    student_id uuid not null references public.profiles(id) on delete cascade,
    period_id uuid not null references public.academic_periods(id) on delete cascade,
    stage_code text not null references public.formation_stages(code),
    semester smallint not null,
    revision integer not null default 1,
    updated_by uuid not null references public.profiles(id) on delete restrict,
    updated_at timestamptz not null default now(),
    primary key(student_id,period_id)
);
alter table public.kardex_programs add column formation_stage text references public.formation_stages(code);
alter table public.formation_stages enable row level security;
alter table public.student_formation_periods enable row level security;
revoke all on public.formation_stages,public.student_formation_periods from public,anon,authenticated;

create function public._formation_check_semester()
returns trigger language plpgsql set search_path=''
as $$
begin
    if new.semester is null or not exists(select 1 from public.formation_stages s
        where s.code=new.stage_code and new.semester between 1 and s.semesters) then
        raise exception using errcode='22023',message='El semestre no corresponde a la etapa seleccionada';
    end if;
    return new;
end;
$$;
create trigger formation_semester_bounds before insert or update on public.student_formation_periods
    for each row execute function public._formation_check_semester();

create function public._formation_history(p_student uuid)
returns jsonb language sql stable security definer set search_path=''
as $$
    select coalesce(jsonb_agg(jsonb_build_object('student_id',f.student_id,'period_id',f.period_id,
        'period_name',p.name,'starts_on',p.starts_on,'ends_on',p.ends_on,
        'stage_code',s.code,'stage_name',s.name,'ecclesial_name',s.ecclesial_name,
        'semesters',s.semesters,'semester',f.semester,'revision',f.revision)
        order by p.starts_on desc,p.ends_on desc,p.id),'[]'::jsonb)
    from public.student_formation_periods f join public.academic_periods p on p.id=f.period_id
        join public.formation_stages s on s.code=f.stage_code where f.student_id=p_student
$$;

create function public.portal_formation_read(p_resource text default 'settings',p_student uuid default null,
    p_period uuid default null,p_stage text default '',p_search text default '',p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor public.profiles%rowtype; rows jsonb; target uuid; needle text:=lower(btrim(coalesce(p_search,'')));
begin
    select * into actor from public.profiles where id=auth.uid() and active for share;
    if actor.id is null or actor.role not in ('student','control_escolar') then
        raise exception using errcode='42501',message='Acceso a formación no autorizado'; end if;
    if p_resource='own' then
        if actor.role<>'student' or (p_student is not null and p_student<>actor.id) then
            raise exception using errcode='42501',message='Solo puedes consultar tu trayectoria'; end if;
        return jsonb_build_object('history',public._formation_history(actor.id));
    end if;
    perform public._require_control_catalog_access();
    if p_resource='settings' then
        return jsonb_build_object('stages',(select jsonb_agg(to_jsonb(s) order by s.position) from public.formation_stages s),
            'periods',(select coalesce(jsonb_agg(to_jsonb(p) order by p.starts_on desc,p.id),'[]'::jsonb) from public.academic_periods p));
    end if;
    if p_resource='history' then
        target:=public._student_record_target(p_student);
        return jsonb_build_object('history',public._formation_history(target));
    end if;
    if p_resource<>'students' or p_offset is null or p_offset<0 or p_offset>100000 or p_limit is null
        or p_limit not between 1 and 100 or char_length(needle)>160
        or (coalesce(p_stage,'')<>'' and not exists(select 1 from public.formation_stages where code=p_stage)) then
        raise exception using errcode='22023',message='Consulta de formación inválida'; end if;
    if p_period is not null and not exists(select 1 from public.academic_periods where id=p_period) then
        raise exception using errcode='22023',message='Periodo no encontrado'; end if;
    select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into rows from (
        select p.id,p.full_name,p.active,k.student_number,
            f.stage_code,f.semester,coalesce(f.revision,0) as revision
        from public.profiles p left join public.kardex_students k on k.student_id=p.id
            left join public.student_formation_periods f on f.student_id=p.id and f.period_id=p_period
        where (p.role='student' or exists(select 1 from public.student_formation_periods x where x.student_id=p.id))
            and (needle='' or strpos(lower(p.full_name||' '||coalesce(k.student_number,'')),needle)>0)
            and (coalesce(p_stage,'')='' or f.stage_code=p_stage)
        order by p.full_name,p.id offset p_offset limit p_limit+1
    ) r;
    return jsonb_build_object('items',(select coalesce(jsonb_agg(v),'[]'::jsonb)
        from jsonb_array_elements(rows) with ordinality j(v,n) where n<=p_limit),
        'has_more',jsonb_array_length(rows)>p_limit);
end;
$$;

create function public.portal_formation_save(p_student uuid,p_period uuid,p_stage text,p_semester integer,p_revision integer)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; current_revision integer;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_student is null or p_period is null or p_revision is null or p_revision<0
        or p_semester is null or not exists(select 1 from public.formation_stages
            where code=p_stage and p_semester between 1 and semesters) then
        raise exception using errcode='22023',message='Selecciona una etapa, un semestre y un periodo válidos'; end if;
    perform id from public.profiles where id=p_student and (role='student'
        or exists(select 1 from public.student_formation_periods where student_id=p_student)) for share;
    if not found then raise exception using errcode='22023',message='Alumno no encontrado'; end if;
    perform id from public.academic_periods where id=p_period for share;
    if not found then raise exception using errcode='22023',message='Periodo no encontrado'; end if;
    select revision into current_revision from public.student_formation_periods
        where student_id=p_student and period_id=p_period for update;
    if coalesce(current_revision,0)<>p_revision then
        raise exception using errcode='PT409',message='La etapa cambió; actualiza la lista antes de guardar'; end if;
    if exists(select 1 from public.student_formation_periods where student_id=p_student and period_id=p_period
        and stage_code=p_stage and semester=p_semester) then return jsonb_build_object('saved',true); end if;
    insert into public.student_formation_periods(student_id,period_id,stage_code,semester,updated_by)
        values(p_student,p_period,p_stage,p_semester,actor)
    on conflict(student_id,period_id) do update set stage_code=excluded.stage_code,semester=excluded.semester,
        updated_by=actor,updated_at=now(),revision=public.student_formation_periods.revision+1;
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,'formation_saved',p_student,jsonb_build_object('period_id',p_period,'stage',p_stage,'semester',p_semester));
    return jsonb_build_object('saved',true);
end;
$$;

-- Mantener las reglas existentes de emisión; añadir la etapa al documento que
-- se congela al emitir. Las copias ya emitidas permanecen intactas.
alter function public._kardex_record(uuid,uuid) rename to _kardex_record_before_formation;
create function public._kardex_record(p_student uuid,p_program uuid default null)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; history jsonb;
begin
    result:=public._kardex_record_before_formation(p_student,p_program)-'token';
    history:=public._formation_history(p_student);
    result:=result||jsonb_build_object('formation_history',history);
    return result||jsonb_build_object('token',md5(result::text));
end;
$$;
-- Los datos escolares son de solo lectura en el expediente personal.
alter function public._student_personal_record(uuid) rename to _student_personal_record_before_formation;
create function public._student_personal_record(p_student uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb;
begin
    result:=public._student_personal_record_before_formation(p_student);
    return jsonb_set(result,'{school,formation_history}',public._formation_history(p_student));
end;
$$;

-- Permitir vincular cada plan de estudios con una de las tres etapas.
alter function public.portal_kardex_write(text,jsonb) rename to _kardex_write_before_formation;
create function public.portal_kardex_write(p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; stage text; max_semesters integer; item jsonb;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    if p_action='program_save' and p_data ? 'formation_stage' then
        stage:=nullif(p_data->>'formation_stage','');
        if stage is not null and not exists(select 1 from public.formation_stages where code=stage) then
            raise exception using errcode='22023',message='Etapa del programa inválida'; end if;
        if stage is not null and exists(select 1 from public.kardex_plan_subjects c
            join public.formation_stages s on s.code=stage where c.program_id=(p_data->>'id')::uuid
            and case when c.term ~ '^[0-9]+$' then c.term::numeric not between 1 and s.semesters else false end) then
            raise exception using errcode='22023',message='El plan contiene semestres fuera de la duración de esta etapa'; end if;
    elsif p_action='curriculum_save' then
        select s.semesters into max_semesters from public.kardex_programs p
            join public.formation_stages s on s.code=p.formation_stage where p.id=(p_data->>'program_id')::uuid;
        if max_semesters is not null then
            for item in select value from jsonb_array_elements(p_data->'items') loop
                if item->>'included'='true' and (item->>'term' is null or item->>'term' !~ '^[1-8]$'
                    or (item->>'term')::integer>max_semesters) then
                    raise exception using errcode='22023',message='Selecciona el semestre de cada materia dentro de la etapa'; end if;
            end loop;
        end if;
    end if;
    result:=public._kardex_write_before_formation(p_action,p_data);
    if p_action='program_save' and p_data ? 'formation_stage' then
        update public.kardex_programs set formation_stage=stage where id=(result->>'id')::uuid;
    end if;
    return result;
exception when invalid_text_representation or numeric_value_out_of_range then
    raise exception using errcode='22023',message='Revisa el semestre y los datos de formación';
end;
$$;

revoke all on function public._formation_check_semester(),public._formation_history(uuid),
    public._kardex_record_before_formation(uuid,uuid),public._kardex_record(uuid,uuid),
    public._student_personal_record_before_formation(uuid),public._student_personal_record(uuid),
    public._kardex_write_before_formation(text,jsonb),public.portal_formation_read(text,uuid,uuid,text,text,integer,integer),
    public.portal_formation_save(uuid,uuid,text,integer,integer),public.portal_kardex_write(text,jsonb) from public,anon,authenticated;
grant execute on function public.portal_formation_read(text,uuid,uuid,text,text,integer,integer),
    public.portal_formation_save(uuid,uuid,text,integer,integer),public.portal_kardex_write(text,jsonb) to authenticated;
commit;
