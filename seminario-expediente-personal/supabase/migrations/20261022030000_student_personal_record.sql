-- Aplicar una vez después de 20261022020000_kardex.sql.
-- El expediente utiliza el mismo usuario, nombre, CURP y nacimiento del portal.
begin;
create table public.student_personal_records (
    student_id uuid primary key references public.profiles(id) on delete cascade,
    details jsonb not null default '{}'::jsonb check(jsonb_typeof(details)='object'),
    revision integer not null default 1,
    updated_at timestamptz not null default now(),
    updated_by uuid not null references public.profiles(id) on delete restrict,
    reviewed_at timestamptz,
    reviewed_by uuid references public.profiles(id) on delete restrict,
    reviewed_fingerprint text
);
alter table public.student_personal_records enable row level security;
revoke all on public.student_personal_records from public,anon,authenticated;

create function public._student_record_target(p_student uuid)
returns uuid language plpgsql volatile security definer set search_path=''
as $$
declare actor public.profiles%rowtype; target uuid;
begin
    select * into actor from public.profiles where id=auth.uid() and active for share;
    if actor.id is null or actor.role not in ('student','control_escolar') then
        raise exception using errcode='42501',message='No tienes acceso al expediente';
    end if;
    target:=coalesce(p_student,actor.id);
    if actor.role='student' and target<>actor.id then
        raise exception using errcode='42501',message='Solo puedes acceder a tu propio expediente';
    end if;
    perform p.id from public.profiles p where p.id=target and (p.role='student'
        or exists(select 1 from public.student_personal_records r where r.student_id=p.id)
        or exists(select 1 from public.kardex_students k where k.student_id=p.id)
        or exists(select 1 from public.enrollments e where e.student_id=p.id)) for share of p;
    if not found then raise exception using errcode='22023',message='Alumno no encontrado'; end if;
    return target;
end;
$$;
create function public._student_record_age(p_birth date,p_today date)
returns integer language sql immutable set search_path=''
as $$ select case when p_birth<=p_today then extract(year from age(p_today,p_birth))::integer end $$;

create function public._student_personal_record(p_student uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare person public.profiles%rowtype; academic public.kardex_students%rowtype;
    personal public.student_personal_records%rowtype; data jsonb; details jsonb; fingerprint text;
    missing jsonb:='[]'::jsonb; item record; today date:=(now() at time zone 'America/Matamoros')::date;
begin
    select * into person from public.profiles where id=p_student;
    if person.id is null then raise exception using errcode='22023',message='Alumno no encontrado'; end if;
    select * into academic from public.kardex_students where student_id=p_student;
    select * into personal from public.student_personal_records where student_id=p_student;
    details:=coalesce(personal.details,'{}'::jsonb);
    fingerprint:=md5(jsonb_build_object('full_name',person.full_name,'curp',academic.curp,'birth_date',academic.birth_date,'details',details)::text);
    for item in select * from (values
        ('Fecha de nacimiento',academic.birth_date::text),('CURP',academic.curp),
        ('Teléfono personal',details->>'phone'),('Calle',details->>'street'),
        ('Municipio / ciudad',details->>'city'),('Estado',details->>'state'),('País',details->>'country'),
        ('Contacto de emergencia',details->>'emergency_name'),('Teléfono de emergencia',details->>'emergency_phone')
    ) as fields(label,value) loop
        if not public._catalog_text_has_content(item.value) then missing:=missing||to_jsonb(item.label); end if;
    end loop;
    data:=jsonb_build_object(
        'student',jsonb_build_object('id',person.id,'full_name',person.full_name,'role',person.role,'active',person.active,
            'login_email',(select email from auth.users where id=p_student)),
        'identity',jsonb_build_object('curp',academic.curp,'birth_date',academic.birth_date,
            'age',public._student_record_age(academic.birth_date,today),'age_as_of',today),
        'details',details,
        'school',jsonb_build_object('student_number',academic.student_number,'entered_on',academic.entered_on,'completed_on',academic.completed_on,
            'enrollments',(select count(*) from public.enrollments where student_id=p_student),
            'programs',(select coalesce(jsonb_agg(to_jsonb(x) order by x.name,x.plan_name),'[]'::jsonb) from (
                select distinct p.id,p.name,p.plan_name from public.enrollments e
                join public.kardex_enrollment_details d on d.enrollment_id=e.id join public.kardex_programs p on p.id=d.program_id where e.student_id=p_student) x)),
        'revision',coalesce(personal.revision,0),'updated_at',personal.updated_at,
        'completion',jsonb_build_object('completed',9-jsonb_array_length(missing),'total',9,'missing',missing),
        'review',jsonb_build_object('reviewed',coalesce(personal.reviewed_fingerprint=fingerprint,false),'reviewed_at',personal.reviewed_at,
            'reviewer',case when personal.reviewed_fingerprint=fingerprint then (select full_name from public.profiles where id=personal.reviewed_by) end));
    return data||jsonb_build_object('token',md5(jsonb_build_object('student_id',person.id,'full_name',person.full_name,'management_revision',person.management_revision,
        'curp',academic.curp,'birth_date',academic.birth_date,'kardex_revision',coalesce(academic.revision,0),
        'details',details,'revision',coalesce(personal.revision,0))::text));
end;
$$;
revoke all on function public._student_record_target(uuid),public._student_record_age(date,date),public._student_personal_record(uuid) from public,anon,authenticated;

create function public.portal_student_record_read(p_resource text default 'record',p_student uuid default null,
    p_search text default '',p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare target uuid; result jsonb; needle text:=lower(btrim(coalesce(p_search,''))); control boolean;
begin
    if p_resource='students' then
        perform public._require_control_catalog_access();
        if p_offset is null or p_offset<0 or p_offset>100000 or p_limit is null or p_limit<1 or p_limit>100 or char_length(needle)>160 then
            raise exception using errcode='22023',message='Consulta inválida'; end if;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from (
            select p.id,p.full_name,p.active,k.student_number,r.updated_at
            from public.profiles p left join public.kardex_students k on k.student_id=p.id left join public.student_personal_records r on r.student_id=p.id
            where (p.role='student' or r.student_id is not null or k.student_id is not null or exists(select 1 from public.enrollments e where e.student_id=p.id))
                and (needle='' or strpos(lower(p.full_name||' '||coalesce(k.student_number,'')||' '||coalesce(k.curp,'')),needle)>0)
            order by p.full_name,p.id offset p_offset limit p_limit+1
        ) r;
        return jsonb_build_object('items',(select coalesce(jsonb_agg(v),'[]'::jsonb) from jsonb_array_elements(result) with ordinality j(v,n) where n<=p_limit),
            'has_more',jsonb_array_length(result)>p_limit);
    elsif p_resource<>'record' or p_resource is null then raise exception using errcode='22023',message='Consulta inválida'; end if;
    target:=public._student_record_target(p_student);
    select role='control_escolar' into control from public.profiles where id=auth.uid();
    return public._student_personal_record(target)||jsonb_build_object('can_review',control);
end;
$$;

create function public.portal_student_record_save(p_student uuid,p_token text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare target uuid; actor uuid:=auth.uid(); previous jsonb; name_value text; curp_value text; birth_value date;
    details jsonb:='{}'::jsonb; limits jsonb; item record; value text; maximum integer;
    today date:=(now() at time zone 'America/Matamoros')::date; control boolean;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    target:=public._student_record_target(p_student);
    perform id from public.profiles where id=target for update;
    previous:=public._student_personal_record(target);
    if p_token is distinct from previous->>'token' then raise exception using errcode='PT409',message='El expediente cambió. Actualiza los datos antes de guardar'; end if;
    if jsonb_typeof(p_data) is distinct from 'object' or (p_data-'full_name'-'curp'-'birth_date'-'details')<>'{}'::jsonb
        or jsonb_typeof(p_data->'full_name') is distinct from 'string'
        or jsonb_typeof(p_data->'details') is distinct from 'object'
        or (p_data->>'curp' is not null and jsonb_typeof(p_data->'curp')<>'string')
        or (p_data->>'birth_date' is not null and jsonb_typeof(p_data->'birth_date')<>'string') then
        raise exception using errcode='22023',message='El formulario solo admite datos personales'; end if;
    name_value:=public._kardex_text(p_data->>'full_name',160,true);
    curp_value:=upper(public._kardex_text(p_data->>'curp',18));birth_value:=public._kardex_date(p_data->>'birth_date');
    if birth_value>today or birth_value<today-interval '120 years' then raise exception using errcode='22023',message='Revisa la fecha de nacimiento'; end if;
    if curp_value is not null and curp_value !~ '^[A-Z][AEIOUX][A-Z]{2}[0-9]{6}[HM][A-Z]{5}[A-Z0-9][0-9]$' then
        raise exception using errcode='22023',message='La CURP debe tener 18 caracteres y un formato válido'; end if;
    if curp_value is not null and birth_value is not null and substring(curp_value from 5 for 6)<>to_char(birth_value,'YYMMDD') then
        raise exception using errcode='22023',message='La fecha de nacimiento no coincide con la fecha incluida en la CURP'; end if;
    limits:='{"birth_country":100,"birth_state":100,"birth_city":100,"nationality":100,"registered_sex":30,
        "phone":40,"alternate_phone":40,"contact_email":320,"street":180,"exterior_number":20,"interior_number":20,
        "neighborhood":100,"postal_code":16,"city":100,"state":100,"country":100,
        "emergency_name":160,"emergency_relationship":80,"emergency_phone":40,
        "father_name":160,"father_phone":40,"mother_name":160,"mother_phone":40,
        "home_diocese":160,"home_parish":160,"previous_school":200,"previous_level":80,
        "previous_qualification":160,"previous_graduation_year":4}'::jsonb;
    for item in select entry.key,entry.value from jsonb_each(p_data->'details') entry loop
        if not limits?item.key or jsonb_typeof(item.value) not in ('string','null') then raise exception using errcode='22023',message='Campo personal inválido'; end if;
        maximum:=(limits->>item.key)::integer;value:=public._kardex_text(item.value#>>'{}',maximum);
        if value is not null then
            if item.key in ('phone','alternate_phone','emergency_phone','father_phone','mother_phone')
                and (value !~ '^[0-9+().#xX /-]+$' or length(regexp_replace(value,'[^0-9]','','g')) not between 7 and 20) then
                raise exception using errcode='22023',message='Revisa los teléfonos: usa de 7 a 20 dígitos, con lada cuando corresponda'; end if;
            if item.key='contact_email' and value !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then raise exception using errcode='22023',message='Revisa el correo de contacto'; end if;
            if item.key='registered_sex' and value not in ('H','M','NE') then raise exception using errcode='22023',message='Revisa el sexo registrado'; end if;
            if item.key='previous_graduation_year' and (value !~ '^[0-9]{4}$' or value::integer not between 1900 and extract(year from today)::integer) then
                raise exception using errcode='22023',message='Revisa el año de egreso de la escuela anterior'; end if;
            details:=details||jsonb_build_object(item.key,value);
        end if;
    end loop;
    select role='control_escolar' into control from public.profiles where id=actor;
    if name_value is distinct from previous->'student'->>'full_name' or curp_value is distinct from previous->'identity'->>'curp'
        or birth_value::text is distinct from previous->'identity'->>'birth_date' or details is distinct from previous->'details' then
        if name_value is distinct from previous->'student'->>'full_name' then
            update public.profiles set full_name=name_value,management_revision=management_revision+1 where id=target;
        end if;
        if curp_value is distinct from previous->'identity'->>'curp' or birth_value::text is distinct from previous->'identity'->>'birth_date' then
            insert into public.kardex_students(student_id,curp,birth_date) values(target,curp_value,birth_value)
            on conflict(student_id) do update set curp=excluded.curp,birth_date=excluded.birth_date,revision=public.kardex_students.revision+1;
        end if;
        insert into public.student_personal_records(student_id,details,updated_by) values(target,details,actor)
        on conflict(student_id) do update set details=excluded.details,updated_by=excluded.updated_by,updated_at=clock_timestamp(),revision=public.student_personal_records.revision+1;
        insert into public.management_events(actor_id,action,entity_id,details)
            values(actor,'student_record_saved',target,jsonb_build_object('source',case when control then 'control_escolar' else 'student' end));
    end if;
    return public._student_personal_record(target)||jsonb_build_object('saved',true,'can_review',control);
exception when unique_violation then raise exception using errcode='PT409',message='La CURP ya está registrada. Revisa el expediente con Control Escolar';
    when check_violation or invalid_text_representation or numeric_value_out_of_range or datetime_field_overflow or invalid_datetime_format then
        raise exception using errcode='22023',message='Revisa la CURP, fechas y datos del formulario';
end;
$$;

create function public.portal_student_record_review(p_student uuid,p_token text)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; target uuid; data jsonb; fingerprint text; previous text;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();target:=public._student_record_target(p_student);
    data:=public._student_personal_record(target);
    if p_token is distinct from data->>'token' then raise exception using errcode='PT409',message='El expediente cambió. Actualiza antes de marcarlo como revisado'; end if;
    fingerprint:=md5(jsonb_build_object('full_name',data->'student'->>'full_name','curp',data->'identity'->>'curp',
        'birth_date',data->'identity'->>'birth_date','details',data->'details')::text);
    select reviewed_fingerprint into previous from public.student_personal_records where student_id=target;
    if previous is distinct from fingerprint then
        insert into public.student_personal_records(student_id,updated_by,reviewed_by,reviewed_at,reviewed_fingerprint)
            values(target,actor,actor,clock_timestamp(),fingerprint)
        on conflict(student_id) do update set reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at,reviewed_fingerprint=excluded.reviewed_fingerprint;
        insert into public.management_events(actor_id,action,entity_id,details) values(actor,'student_record_reviewed',target,'{}'::jsonb);
    end if;
    return public._student_personal_record(target)||jsonb_build_object('saved',true,'can_review',true);
end;
$$;
revoke all on function public.portal_student_record_read(text,uuid,text,integer,integer),public.portal_student_record_save(uuid,text,jsonb),
    public.portal_student_record_review(uuid,text) from public,anon,authenticated;
grant execute on function public.portal_student_record_read(text,uuid,text,integer,integer),public.portal_student_record_save(uuid,text,jsonb),
    public.portal_student_record_review(uuid,text) to authenticated;
commit;
