-- Kardex institucional: aplicar una vez después de las migraciones anteriores.
-- No modifica notas, inscripciones ni registros existentes.
begin;
create table public.kardex_institution (
    id boolean primary key default true check(id),
    name text not null default 'Seminario Diocesano San José',
    campus text not null default 'Matamoros-Reynosa',
    address text, cct text, issue_place text,
    rector_name text, officer_name text,
    revision integer not null default 0
);
insert into public.kardex_institution(id) values(true);
create table public.kardex_programs (
    id uuid primary key default gen_random_uuid(),
    name text not null, plan_name text not null,
    education_level text, modality text,
    rvoe_number text, rvoe_date date, rvoe_authority text,
    pass_mark numeric(5,2) check(pass_mark between 0 and 100),
    display_scale text not null default '100' check(display_scale in ('100','10')),
    repeat_policy text not null default 'all' check(repeat_policy in ('all','latest','best')),
    weighted boolean not null default false,
    revision integer not null default 1,
    unique(name,plan_name)
);
create table public.kardex_students (
    student_id uuid primary key references public.profiles(id) on delete restrict,
    student_number text unique,
    curp text unique check(curp is null or curp ~ '^[A-Z][AEIOUX][A-Z]{2}[0-9]{6}[HM][A-Z]{5}[A-Z0-9][0-9]$'),
    birth_date date, entered_on date, completed_on date,
    revision integer not null default 1,
    check(completed_on is null or entered_on is null or completed_on>=entered_on)
);
create table public.kardex_plan_subjects (
    program_id uuid not null references public.kardex_programs(id) on delete restrict,
    subject_id uuid not null references public.subjects(id) on delete cascade,
    credits numeric(7,2) check(credits between 0 and 9999),
    hours numeric(7,2) check(hours between 0 and 9999),
    term text,
    revision integer not null default 1,
    primary key(program_id,subject_id)
);
create table public.kardex_enrollment_details (
    enrollment_id uuid primary key references public.enrollments(id) on delete cascade,
    program_id uuid references public.kardex_programs(id) on delete restrict,
    exam_type text check(exam_type in ('ORD','EXT','EQ','REV')),
    notes text,
    revision integer not null default 1
);
create sequence public.kardex_folio_seq;
create table public.kardex_issues (
    id uuid primary key,
    student_id uuid not null references public.profiles(id) on delete restrict,
    issued_by uuid not null references public.profiles(id) on delete restrict,
    folio text not null unique,
    kind text not null check(kind in ('partial','final')),
    request_hash text not null,
    snapshot jsonb not null,
    issued_at timestamptz not null default now()
);
create index kardex_issues_student_idx on public.kardex_issues(student_id,issued_at desc,id);
alter table public.kardex_institution enable row level security;
alter table public.kardex_programs enable row level security;
alter table public.kardex_students enable row level security;
alter table public.kardex_plan_subjects enable row level security;
alter table public.kardex_enrollment_details enable row level security;
alter table public.kardex_issues enable row level security;
revoke all on public.kardex_institution,public.kardex_programs,public.kardex_students,
    public.kardex_plan_subjects,public.kardex_enrollment_details,public.kardex_issues from public,anon,authenticated;
revoke all on sequence public.kardex_folio_seq from public,anon,authenticated;

create function public._kardex_text(p_value text,p_max integer,p_required boolean default false)
returns text language plpgsql immutable set search_path=''
as $$
declare value text:=btrim(p_value);
begin
    if not public._catalog_text_has_content(value) then
        if p_required then raise exception using errcode='22023',message='Completa los campos obligatorios'; end if;
        return null;
    end if;
    if char_length(value)>p_max or value ~ '[[:cntrl:]]' then raise exception using errcode='22023',message='Texto inválido o demasiado largo'; end if;
    return value;
end;
$$;
create function public._kardex_date(p_value text)
returns date language plpgsql immutable set search_path=''
as $$
declare result date;
begin
    if p_value is null or btrim(p_value)='' then return null; end if;
    if p_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then raise exception using errcode='22023',message='Fecha inválida'; end if;
    result:=p_value::date;
    if not isfinite(result) or result<date '0001-01-01' or result>date '9999-12-31' then raise exception using errcode='22023',message='Fecha inválida'; end if;
    return result;
end;
$$;
revoke all on function public._kardex_text(text,integer,boolean),public._kardex_date(text) from public,anon,authenticated;

create function public._kardex_record(p_student uuid,p_program uuid default null)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare student jsonb; institution jsonb; program jsonb; rows jsonb; curriculum jsonb;
    result jsonb; stats jsonb; reasons jsonb:='[]'::jsonb;
    policy text:='all'; weighted boolean:=false; threshold numeric; missing_weights bigint;
begin
    select jsonb_build_object('id',p.id,'full_name',p.full_name,'active',p.active,
        'student_number',s.student_number,'curp',s.curp,'birth_date',s.birth_date,
        'entered_on',s.entered_on,'completed_on',s.completed_on,'revision',coalesce(s.revision,0)) into student
    from public.profiles p left join public.kardex_students s on s.student_id=p.id
    where p.id=p_student and (p.role='student' or s.student_id is not null or exists(select 1 from public.enrollments e where e.student_id=p.id) or exists(select 1 from public.kardex_issues i where i.student_id=p.id));
    if student is null then raise exception using errcode='22023',message='Alumno no encontrado'; end if;
    select to_jsonb(i)-'id' into institution from public.kardex_institution i;
    if p_program is not null then
        select to_jsonb(p) into program from public.kardex_programs p where p.id=p_program;
        if program is null then raise exception using errcode='22023',message='Programa no encontrado'; end if;
        policy:=program->>'repeat_policy';weighted:=(program->>'weighted')::boolean;threshold:=(program->>'pass_mark')::numeric;
    end if;
    -- No se filtran clases, personas o inscripciones por actividad: el historial
    -- incluye periodos archivados y calificaciones publicadas antes de una baja.
    with source as (
        select e.id as enrollment_id,e.subject_id,e.period_id,e.active as enrollment_active,
            s.code,s.name,a.name as period_name,a.starts_on,a.ends_on,
            case when g.published then g.score end as score,
            d.program_id,p.name as program_name,d.exam_type,d.notes,coalesce(d.revision,0) as revision,
            c.credits,c.hours,c.term,
            case when g.published and p.pass_mark is not null then g.score>=p.pass_mark end as passed
        from public.enrollments e join public.subjects s on s.id=e.subject_id
        join public.academic_periods a on a.id=e.period_id
        left join public.enrollment_grades g on g.enrollment_id=e.id
        left join public.kardex_enrollment_details d on d.enrollment_id=e.id
        left join public.kardex_programs p on p.id=d.program_id
        left join public.kardex_plan_subjects c on c.program_id=d.program_id and c.subject_id=e.subject_id
        where e.student_id=p_student and (p_program is null or d.program_id=p_program)
    ), graded as (
        select x.enrollment_id,
            row_number() over(partition by x.program_id,x.subject_id order by x.ends_on desc,x.starts_on desc,x.period_id desc,x.enrollment_id desc) as latest,
            row_number() over(partition by x.program_id,x.subject_id order by x.score desc,x.ends_on desc,x.starts_on desc,x.period_id desc,x.enrollment_id desc) as best
        from source x where x.score is not null
    )
    select coalesce(jsonb_agg(to_jsonb(r) order by r.starts_on,r.ends_on,r.period_id,r.code,r.enrollment_id),'[]'::jsonb) into rows from (
        select x.*,x.score is not null and (policy='all' or policy='latest' and y.latest=1 or policy='best' and y.best=1) as counted
        from source x left join graded y on y.enrollment_id=x.enrollment_id
    ) r;
    select count(*) into missing_weights from jsonb_array_elements(rows) j
        where (j->>'counted')::boolean and coalesce((j->>'credits')::numeric,0)<=0;
    select jsonb_build_object(
        'enrollments',jsonb_array_length(rows),
        'graded',(select count(*) from jsonb_array_elements(rows) j where j->>'score' is not null),
        'pending',(select count(*) from jsonb_array_elements(rows) j where j->>'score' is null and (j->>'enrollment_active')::boolean),
        'withdrawn',(select count(*) from jsonb_array_elements(rows) j where j->>'score' is null and not (j->>'enrollment_active')::boolean),
        'counted',(select count(*) from jsonb_array_elements(rows) j where (j->>'counted')::boolean),
        'missing_weights',case when weighted then missing_weights else 0 end,
        'average',case when weighted and missing_weights>0 then null else (
            select round(sum((j->>'score')::numeric * case when weighted then (j->>'credits')::numeric else 1 end)
                /nullif(sum(case when weighted then (j->>'credits')::numeric else 1 end),0),2)
            from jsonb_array_elements(rows) j where (j->>'counted')::boolean) end,
        'credits_earned',(select coalesce(sum(x.credits),0) from (
            select (j->>'program_id')::uuid,(j->>'subject_id')::uuid,max((j->>'credits')::numeric) as credits
            from jsonb_array_elements(rows) j where (j->>'passed')::boolean
            group by j->>'program_id',j->>'subject_id') x)
    ) into stats;
    curriculum:='[]'::jsonb;
    if p_program is not null then
        select coalesce(jsonb_agg(to_jsonb(r) order by r.term nulls last,r.code),'[]'::jsonb) into curriculum from (
            select s.id as subject_id,s.code,s.name,c.credits,c.hours,c.term,c.revision,
                exists(select 1 from jsonb_array_elements(rows) j where j->>'subject_id'=s.id::text and (j->>'passed')::boolean) as passed
            from public.kardex_plan_subjects c join public.subjects s on s.id=c.subject_id where c.program_id=p_program
        ) r;
    end if;
    if exists(select 1 from jsonb_array_elements(rows) j where j->>'score' is not null
        and (j->>'passed' is null or ((j->>'passed')::boolean and j->>'credits' is null))) then
        stats:=stats||jsonb_build_object('credits_earned',null);
    end if;
    stats:=stats||jsonb_build_object('plan_subjects',jsonb_array_length(curriculum),
        'plan_pending',(select count(*) from jsonb_array_elements(curriculum) j where not (j->>'passed')::boolean),
        'plan_credits',(select coalesce(sum((j->>'credits')::numeric),0) from jsonb_array_elements(curriculum) j),
        'unclassified',(select count(*) from public.enrollments e left join public.kardex_enrollment_details d on d.enrollment_id=e.id where e.student_id=p_student and d.program_id is null));
    if student->>'student_number' is null then reasons:=reasons||'"Registra la matrícula del alumno"'::jsonb; end if;
    if p_program is null then reasons:=reasons||'"Selecciona un programa para generar un kardex final"'::jsonb; end if;
    if jsonb_array_length(curriculum)=0 then reasons:=reasons||'"Registra las materias del plan de estudios"'::jsonb; end if;
    if threshold is null then reasons:=reasons||'"Configura la calificación mínima aprobatoria del programa"'::jsonb; end if;
    if (stats->>'graded')::integer=0 then reasons:=reasons||'"Todavía no hay calificaciones finales publicadas"'::jsonb; end if;
    if (stats->>'pending')::integer>0 then reasons:=reasons||'"Hay inscripciones con calificación final pendiente"'::jsonb; end if;
    if (stats->>'unclassified')::integer>0 then reasons:=reasons||'"Clasifica las inscripciones que todavía no tienen programa"'::jsonb; end if;
    if exists(select 1 from jsonb_array_elements(curriculum) j where j->>'credits' is null) then
        reasons:=reasons||'"Completa los créditos de las materias del plan (usa cero si no otorgan créditos)"'::jsonb;
    end if;
    if (stats->>'plan_pending')::integer>0 then reasons:=reasons||'"Quedan materias del plan sin aprobar"'::jsonb; end if;
    if weighted and missing_weights>0 then reasons:=reasons||'"Faltan créditos positivos para calcular el promedio ponderado"'::jsonb; end if;
    if exists(select 1 from jsonb_array_elements(rows) j where j->>'score' is not null and j->>'exam_type' is null) then
        reasons:=reasons||'"Registra el tipo de evaluación de las calificaciones publicadas"'::jsonb; end if;
    result:=jsonb_build_object('student',student,'institution',institution,'program',program,'rows',rows,'curriculum',curriculum,
        'stats',stats,'final_reasons',reasons,'final_ready',jsonb_array_length(reasons)=0,
        'method',jsonb_build_object('repeat_policy',policy,'weighted',weighted,'display_scale',coalesce(program->>'display_scale','100')));
    return result||jsonb_build_object('token',md5(result::text));
end;
$$;
revoke all on function public._kardex_record(uuid,uuid) from public,anon,authenticated;

create function public.portal_kardex_read(p_resource text,p_student uuid default null,p_program uuid default null,
    p_search text default '',p_offset integer default 0,p_limit integer default 30,p_issue uuid default null)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; total bigint; needle text:=lower(btrim(coalesce(p_search,'')));
begin
    perform public._require_control_catalog_access();
    if p_offset is null or p_offset<0 or p_offset>100000 or p_limit is null or p_limit<1 or p_limit>100 or char_length(needle)>160 then
        raise exception using errcode='22023',message='Consulta inválida'; end if;
    if p_resource='students' then
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from (
            select p.id,p.full_name,p.active,s.student_number,s.curp,
                (select count(*) from public.enrollments e where e.student_id=p.id) as enrollments
            from public.profiles p left join public.kardex_students s on s.student_id=p.id
            where (p.role='student' or s.student_id is not null or exists(select 1 from public.enrollments e where e.student_id=p.id) or exists(select 1 from public.kardex_issues i where i.student_id=p.id))
                and (needle='' or strpos(lower(p.full_name||' '||coalesce(s.student_number,'')||' '||coalesce(s.curp,'')),needle)>0)
            order by p.full_name,p.id offset p_offset limit p_limit+1
        ) r;
    elsif p_resource='record' then return public._kardex_record(p_student,p_program);
    elsif p_resource='settings' then
        return jsonb_build_object('institution',(select to_jsonb(i)-'id' from public.kardex_institution i));
    elsif p_resource='programs' then
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from (
            select p.* from public.kardex_programs p where needle='' or strpos(lower(p.name||' '||p.plan_name),needle)>0
            order by p.name,p.plan_name,p.id offset p_offset limit p_limit+1
        ) r;
    elsif p_resource='curriculum' then
        if not exists(select 1 from public.kardex_programs where id=p_program) then raise exception using errcode='22023',message='Programa no encontrado'; end if;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from (
            select s.id as subject_id,s.code,s.name,c.credits,c.hours,c.term,coalesce(c.revision,0) as revision,c.program_id is not null as included
            from public.subjects s left join public.kardex_plan_subjects c on c.program_id=p_program and c.subject_id=s.id
            where needle='' or strpos(lower(s.code||' '||s.name),needle)>0 order by s.code,s.id offset p_offset limit p_limit+1
        ) r;
    elsif p_resource='issues' then
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from (
            select i.id,i.folio,i.kind,i.issued_at,i.snapshot->'student'->>'full_name' as student_name,
                i.snapshot->'program'->>'name' as program_name
            from public.kardex_issues i where i.student_id=p_student order by i.issued_at desc,i.id offset p_offset limit p_limit+1
        ) r;
    elsif p_resource='issue' then
        select jsonb_build_object('id',i.id,'folio',i.folio,'kind',i.kind,'issued_at',i.issued_at,'snapshot',i.snapshot) into result
            from public.kardex_issues i where i.id=p_issue;
        if result is null then raise exception using errcode='22023',message='Documento no encontrado'; end if;
        return result;
    else raise exception using errcode='22023',message='Sección de kardex inválida'; end if;
    return jsonb_build_object('items',(select coalesce(jsonb_agg(v),'[]'::jsonb) from jsonb_array_elements(result) with ordinality j(v,n) where n<=p_limit),
        'has_more',jsonb_array_length(result)>p_limit);
end;
$$;

create function public.portal_kardex_write(p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; entity uuid; expected integer; current_revision integer; item jsonb; changed bigint;
    credits_value numeric; hours_value numeric; target_student uuid; program uuid; exam text; current_row public.kardex_students%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_data is null or jsonb_typeof(p_data)<>'object' then raise exception using errcode='22023',message='Datos inválidos'; end if;
    if p_action='institution_save' then
        if jsonb_typeof(p_data->'revision') is distinct from 'number' then raise exception using errcode='22023',message='Revisión inválida'; end if;
        update public.kardex_institution set name=public._kardex_text(p_data->>'name',200,true),
            campus=coalesce(public._kardex_text(p_data->>'campus',160),''),address=public._kardex_text(p_data->>'address',350),
            cct=upper(public._kardex_text(p_data->>'cct',40)),issue_place=public._kardex_text(p_data->>'issue_place',160),
            rector_name=public._kardex_text(p_data->>'rector_name',160),officer_name=public._kardex_text(p_data->>'officer_name',160),revision=revision+1
        where revision=(p_data->>'revision')::integer;
        if not found then raise exception using errcode='PT409',message='Los datos de la institución cambiaron; actualiza antes de guardar'; end if;
    elsif p_action='program_save' then
        entity:=coalesce((p_data->>'id')::uuid,gen_random_uuid());
        select revision into current_revision from public.kardex_programs where id=entity for update;
        if coalesce(current_revision,0)<>coalesce((p_data->>'revision')::integer,-1) then raise exception using errcode='PT409',message='El programa cambió; actualiza antes de guardar'; end if;
        if p_data->>'display_scale' is null or p_data->>'display_scale' not in ('100','10') or p_data->>'repeat_policy' is null or p_data->>'repeat_policy' not in ('all','latest','best')
            or jsonb_typeof(p_data->'weighted') is distinct from 'boolean' then raise exception using errcode='22023',message='Configura la escala y el cálculo del promedio'; end if;
        if p_data->>'pass_mark' is not null and (jsonb_typeof(p_data->'pass_mark')<>'number' or (p_data->>'pass_mark')::numeric not between 0 and 100) then
            raise exception using errcode='22023',message='Calificación mínima inválida; usa la escala de 0 a 100'; end if;
        insert into public.kardex_programs(id,name,plan_name,education_level,modality,rvoe_number,rvoe_date,rvoe_authority,pass_mark,display_scale,repeat_policy,weighted)
            values(entity,public._kardex_text(p_data->>'name',200,true),public._kardex_text(p_data->>'plan_name',160,true),public._kardex_text(p_data->>'education_level',120),
                public._kardex_text(p_data->>'modality',80),public._kardex_text(p_data->>'rvoe_number',120),public._kardex_date(p_data->>'rvoe_date'),
                public._kardex_text(p_data->>'rvoe_authority',200),(p_data->>'pass_mark')::numeric,p_data->>'display_scale',p_data->>'repeat_policy',(p_data->>'weighted')::boolean)
        on conflict(id) do update set name=excluded.name,plan_name=excluded.plan_name,education_level=excluded.education_level,modality=excluded.modality,
            rvoe_number=excluded.rvoe_number,rvoe_date=excluded.rvoe_date,rvoe_authority=excluded.rvoe_authority,pass_mark=excluded.pass_mark,
            display_scale=excluded.display_scale,repeat_policy=excluded.repeat_policy,weighted=excluded.weighted,revision=public.kardex_programs.revision+1;
    elsif p_action='student_save' then
        entity:=(p_data->>'student_id')::uuid;
        perform id from public.profiles where id=entity and (role='student' or exists(select 1 from public.kardex_students where student_id=entity) or exists(select 1 from public.enrollments where student_id=entity)) for share;
        if not found then raise exception using errcode='22023',message='Alumno no encontrado'; end if;
        select * into current_row from public.kardex_students where student_id=entity for update;
        if coalesce(current_row.revision,0)<>coalesce((p_data->>'revision')::integer,-1) then raise exception using errcode='PT409',message='El expediente cambió; actualiza antes de guardar'; end if;
        insert into public.kardex_students(student_id,student_number,curp,birth_date,entered_on,completed_on)
            values(entity,upper(public._kardex_text(p_data->>'student_number',40)),upper(public._kardex_text(p_data->>'curp',18)),
                public._kardex_date(p_data->>'birth_date'),public._kardex_date(p_data->>'entered_on'),public._kardex_date(p_data->>'completed_on'))
        on conflict(student_id) do update set student_number=excluded.student_number,curp=excluded.curp,birth_date=excluded.birth_date,
            entered_on=excluded.entered_on,completed_on=excluded.completed_on,revision=public.kardex_students.revision+1;
    elsif p_action='curriculum_save' then
        entity:=(p_data->>'program_id')::uuid;
        perform id from public.kardex_programs where id=entity for share;
        if not found then raise exception using errcode='22023',message='Programa no encontrado'; end if;
        if jsonb_typeof(p_data->'items') is distinct from 'array' or jsonb_array_length(p_data->'items') not between 1 and 100 then raise exception using errcode='22023',message='Lista de materias inválida'; end if;
        for item in select value from jsonb_array_elements(p_data->'items') loop
            perform id from public.subjects where id=(item->>'subject_id')::uuid for share;
            if not found then raise exception using errcode='22023',message='Materia no encontrada'; end if;
            select revision into current_revision from public.kardex_plan_subjects where program_id=entity and subject_id=(item->>'subject_id')::uuid for update;
            if coalesce(current_revision,0)<>coalesce((item->>'revision')::integer,-1) then raise exception using errcode='PT409',message='El plan cambió; actualiza antes de guardar'; end if;
            if jsonb_typeof(item->'included') is distinct from 'boolean' then raise exception using errcode='22023',message='Estado de materia inválido'; end if;
            if (item->>'included')::boolean then
                credits_value:=(item->>'credits')::numeric;hours_value:=(item->>'hours')::numeric;
                if credits_value<0 or credits_value>9999 or hours_value<0 or hours_value>9999 then raise exception using errcode='22023',message='Créditos u horas inválidos'; end if;
                insert into public.kardex_plan_subjects(program_id,subject_id,credits,hours,term)
                    values(entity,(item->>'subject_id')::uuid,credits_value,hours_value,public._kardex_text(item->>'term',60))
                on conflict(program_id,subject_id) do update set credits=excluded.credits,hours=excluded.hours,term=excluded.term,revision=public.kardex_plan_subjects.revision+1;
            else delete from public.kardex_plan_subjects where program_id=entity and subject_id=(item->>'subject_id')::uuid; end if;
        end loop;
    elsif p_action='academic_save' then
        entity:=(p_data->>'student_id')::uuid;
        if jsonb_typeof(p_data->'items') is distinct from 'array' or jsonb_array_length(p_data->'items') not between 1 and 500 then raise exception using errcode='22023',message='Lista de inscripciones inválida'; end if;
        for item in select value from jsonb_array_elements(p_data->'items') loop
            perform e.id from public.enrollments e where e.id=(item->>'enrollment_id')::uuid and e.student_id=entity for share;
            if not found then raise exception using errcode='22023',message='Una inscripción no corresponde al alumno'; end if;
            select revision into current_revision from public.kardex_enrollment_details where enrollment_id=(item->>'enrollment_id')::uuid for update;
            if coalesce(current_revision,0)<>coalesce((item->>'revision')::integer,-1) then raise exception using errcode='PT409',message='Los datos académicos cambiaron; actualiza antes de guardar'; end if;
            program:=(item->>'program_id')::uuid;exam:=public._kardex_text(item->>'exam_type',3);
            if program is not null and not exists(select 1 from public.kardex_programs where id=program) then raise exception using errcode='22023',message='Programa no encontrado'; end if;
            if exam is not null and exam not in ('ORD','EXT','EQ','REV') then raise exception using errcode='22023',message='Tipo de evaluación inválido'; end if;
            insert into public.kardex_enrollment_details(enrollment_id,program_id,exam_type,notes)
                values((item->>'enrollment_id')::uuid,program,exam,public._kardex_text(item->>'notes',200))
            on conflict(enrollment_id) do update set program_id=excluded.program_id,exam_type=excluded.exam_type,notes=excluded.notes,revision=public.kardex_enrollment_details.revision+1;
        end loop;
    else raise exception using errcode='22023',message='Acción de kardex inválida'; end if;
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,'kardex_'||p_action,coalesce(entity,actor),'{}'::jsonb);
    return jsonb_build_object('saved',true,'id',coalesce(entity,actor));
exception when unique_violation then raise exception using errcode='PT409',message='La matrícula, CURP o programa ya existe';
    when check_violation or invalid_text_representation or numeric_value_out_of_range or datetime_field_overflow or invalid_datetime_format then
        raise exception using errcode='22023',message='Revisa la matrícula, CURP, fechas, créditos y demás datos del formulario';
end;
$$;

create function public.portal_kardex_issue(p_student uuid,p_program uuid,p_kind text,p_token text,p_request_id uuid,p_notes text default '')
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; record jsonb; fingerprint text; existing public.kardex_issues%rowtype; folio_value text; n text; notes_value text;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_request_id is null or p_kind is null or p_kind not in ('partial','final') then raise exception using errcode='22023',message='Tipo de documento inválido'; end if;
    notes_value:=public._kardex_text(p_notes,1000);
    fingerprint:=md5(jsonb_build_object('student',p_student,'program',p_program,'kind',p_kind,'token',p_token,'notes',notes_value)::text);
    select * into existing from public.kardex_issues where id=p_request_id;
    if found then
        if existing.issued_by<>actor or existing.request_hash<>fingerprint then raise exception using errcode='PT409',message='Esta solicitud ya fue utilizada para otro documento'; end if;
        return jsonb_build_object('saved',true,'id',existing.id,'folio',existing.folio);
    end if;
    perform e.id from public.enrollments e where e.student_id=p_student order by e.id for share;
    record:=public._kardex_record(p_student,p_program);
    if p_token is distinct from record->>'token' then raise exception using errcode='PT409',message='Las calificaciones o el expediente cambiaron; actualiza la vista previa antes de emitir'; end if;
    if record->'student'->>'student_number' is null then raise exception using errcode='22023',message='Registra la matrícula antes de emitir el kardex'; end if;
    if (record->'stats'->>'graded')::integer=0 then raise exception using errcode='22023',message='Publica al menos una calificación final antes de emitir'; end if;
    if p_kind='final' and not (record->>'final_ready')::boolean then raise exception using errcode='22023',message='Completa los requisitos que aparecen en la vista previa del kardex final'; end if;
    n:=nextval('public.kardex_folio_seq')::text;
    folio_value:='KDX-'||to_char(current_date,'YYYY')||'-'||lpad(n,greatest(6,length(n)),'0');
    insert into public.kardex_issues(id,student_id,issued_by,folio,kind,request_hash,snapshot)
        values(p_request_id,p_student,actor,folio_value,p_kind,fingerprint,record||jsonb_build_object('notes',notes_value));
    insert into public.management_events(actor_id,action,entity_id,details) values(actor,'kardex_issue',p_request_id,jsonb_build_object('folio',folio_value,'kind',p_kind));
    return jsonb_build_object('saved',true,'id',p_request_id,'folio',folio_value);
end;
$$;
revoke all on function public.portal_kardex_read(text,uuid,uuid,text,integer,integer,uuid),public.portal_kardex_write(text,jsonb),
    public.portal_kardex_issue(uuid,uuid,text,text,uuid,text) from public,anon,authenticated;
grant execute on function public.portal_kardex_read(text,uuid,uuid,text,integer,integer,uuid),public.portal_kardex_write(text,jsonb),
    public.portal_kardex_issue(uuid,uuid,text,text,uuid,text) to authenticated;
commit;
