-- Inscripción múltiple: solo Control Escolar activo. No altera datos al instalarse.
begin;

create function public.portal_enrollment_candidates(p_class uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare c public.course_offerings%rowtype; result jsonb;
begin
    perform public._require_control_catalog_access();
    select * into c from public.course_offerings where id=p_class and active;
    if not found then raise exception using errcode='22023',message='Selecciona una clase activa'; end if;
    select coalesce(jsonb_agg(to_jsonb(x) order by x.full_name,x.id),'[]'::jsonb) into result from (
        select p.id,p.full_name,u.email,
            case when e.active then 'enrolled' when e.id is not null then 'inactive' else 'available' end as status
        from public.profiles p join auth.users u on u.id=p.id
        left join public.enrollments e on e.student_id=p.id and e.subject_id=c.subject_id and e.period_id=c.period_id
        where p.role='student' and p.active
    ) x;
    return jsonb_build_object('class_id',c.id,'items',result);
end;
$$;

create function public.portal_enroll_students(p_class uuid,p_students uuid[])
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare c public.course_offerings%rowtype; students uuid[]; student uuid; matched integer;
    previous public.enrollments%rowtype; saved jsonb; added integer:=0; restored integer:=0; skipped integer:=0;
begin
    -- Mismo orden de bloqueo que la administración existente: todo el lote es una transacción.
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    if p_students is null or coalesce(array_ndims(p_students),0)<>1 or cardinality(p_students)<1
        or cardinality(p_students)>500 or array_position(p_students,null) is not null then
        raise exception using errcode='22023',message='Selecciona entre 1 y 500 alumnos'; end if;
    select array_agg(distinct x order by x) into students from unnest(p_students) x;
    select * into c from public.course_offerings where id=p_class and active for share;
    if not found then raise exception using errcode='22023',message='La clase ya no está activa. Actualiza la lista.'; end if;
    perform p.id from public.profiles p where p.id=any(students) and p.active and p.role='student' order by p.id for share;
    get diagnostics matched=row_count;
    if matched<>cardinality(students) then
        raise exception using errcode='22023',message='Un alumno ya no está disponible. Actualiza la lista antes de inscribir.'; end if;
    foreach student in array students loop
        select * into previous from public.enrollments e
            where e.student_id=student and e.subject_id=c.subject_id and e.period_id=c.period_id for update;
        if previous.active then skipped:=skipped+1;
        else
            -- Reutiliza validación, auditoría y reactivación conservando el identificador y sus notas.
            saved:=public.portal_admin_write('enroll',jsonb_build_object('class_id',c.id,'person_id',student));
            if saved->>'saved' is distinct from 'true' then raise exception 'No se confirmó una inscripción'; end if;
            if previous.id is null then added:=added+1; else restored:=restored+1; end if;
        end if;
    end loop;
    return jsonb_build_object('saved',true,'class_id',c.id,'selected',cardinality(students),
        'enrolled',added,'reactivated',restored,'already_enrolled',skipped);
end;
$$;

revoke all on function public.portal_enrollment_candidates(uuid),public.portal_enroll_students(uuid,uuid[]) from public,anon,authenticated;
grant execute on function public.portal_enrollment_candidates(uuid),public.portal_enroll_students(uuid,uuid[]) to authenticated;
notify pgrst,'reload schema';
commit;
