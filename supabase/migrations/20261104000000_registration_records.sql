-- Corrección del prefecto, matrícula desde expediente y campos de inscripción.
begin;
-- Conservar el guardado que realmente está instalado, con o sin la extensión de boletas.
do $$begin
 if to_regprocedure('public._kardex_write_before_registration(text,jsonb)') is null then
  if to_regprocedure('public.portal_kardex_write(text,jsonb)') is null then
   raise exception 'Falta instalar el módulo de kardex; no se aplicó la actualización';
  end if;
  alter function public.portal_kardex_write(text,jsonb) rename to _kardex_write_before_registration;
 end if;
end;$$;
alter table public.kardex_institution add column if not exists prefect_name text;
create or replace function public.portal_kardex_write(p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb; prefect text;
begin
 perform pg_catalog.pg_advisory_xact_lock(72643219);
 perform public._require_control_catalog_access();
 if p_action='institution_save' and p_data?'prefect_name' then prefect:=public._kardex_text(p_data->>'prefect_name',160);end if;
 result:=public._kardex_write_before_registration(p_action,p_data);
 if p_action='institution_save' and p_data?'prefect_name' then
  update public.kardex_institution set prefect_name=prefect where id=true;
  if not found then raise exception 'No se encontró la configuración del plantel';end if;
 end if;
 return result;
end;$$;
update public.kardex_institution set prefect_name='Pbro. Martín Nicolás Hinojosa',revision=revision+1
where id=true and prefect_name is distinct from 'Pbro. Martín Nicolás Hinojosa';
create or replace function public.portal_student_record_save(p_student uuid,p_token text,p_data jsonb)
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
    limits:='{"birth_place":160,"home_phone":80,"social_profiles":500,"medical_coverage":80,"medical_provider":160,"home_zone":160,"home_deanery":200,"registration_course":80,"registration_timestamp":80,"birth_country":100,"birth_state":100,"birth_city":100,"nationality":100,"registered_sex":30,
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

create or replace function public.portal_student_number_save(p_student uuid,p_token text,p_number text)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare target uuid; before jsonb; n text;
begin
 perform pg_catalog.pg_advisory_xact_lock(72643219);
 perform public._require_control_catalog_access();target:=public._student_record_target(p_student);
 before:=public._student_personal_record(target);
 if p_token is null or p_token is distinct from before->>'token' then raise exception using errcode='PT409',message='El expediente cambió. Actualiza antes de editar la matrícula';end if;
 n:=upper(public._kardex_text(p_number,40));if n ~ '^0+$' then n:=null;end if;
 if n is not null and n ~ '[[:cntrl:]]' then raise exception using errcode='22023',message='Matrícula inválida';end if;
 if n is distinct from before->'school'->>'student_number' then
  insert into public.kardex_students(student_id,student_number)values(target,n)
  on conflict(student_id)do update set student_number=excluded.student_number,revision=public.kardex_students.revision+1;
  insert into public.management_events(actor_id,action,entity_id,details)values(auth.uid(),'student_number_saved',target,'{}');
 end if;
 return public._student_personal_record(target)||jsonb_build_object('saved',true,'can_review',true);
exception when unique_violation then raise exception using errcode='PT409',message='Esa matrícula ya pertenece a otro seminarista';
end;$$;
revoke all on function public.portal_student_number_save(uuid,text,text) from public,anon,authenticated;
grant execute on function public.portal_student_number_save(uuid,text,text) to authenticated;
revoke all on function public._kardex_write_before_registration(text,jsonb),public.portal_kardex_write(text,jsonb),public.portal_student_record_save(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.portal_kardex_write(text,jsonb),public.portal_student_record_save(uuid,text,jsonb) to authenticated;
notify pgrst,'reload schema';
commit;
