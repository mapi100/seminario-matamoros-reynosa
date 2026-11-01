-- Grupos en Etapas y semestres. Instalar después de 20261101010000_batch_enrollment.sql.
-- Solo añade funciones; la instalación no modifica alumnos, clases ni calificaciones.
begin;

create function public._formation_group_snapshot(p_period uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb;
begin
    if p_period is null or not exists(select 1 from public.academic_periods where id=p_period) then
        raise exception using errcode='22023',message='Selecciona un periodo válido'; end if;
    result:=jsonb_build_object('period_id',p_period,
        'students',(select coalesce(jsonb_agg(to_jsonb(x) order by x.id),'[]'::jsonb) from (
            select p.id,p.full_name,k.student_number,f.stage_code,f.semester,coalesce(f.revision,0) revision
            from public.profiles p left join public.kardex_students k on k.student_id=p.id
            left join public.student_formation_periods f on f.student_id=p.id and f.period_id=p_period
            where p.role='student' and p.active
        ) x),
        'classes',(select coalesce(jsonb_agg(to_jsonb(x) order by x.id),'[]'::jsonb) from (
            select c.id,s.name,g.group_code,g.revision
            from public.course_offerings c join public.subjects s on s.id=c.subject_id
            join public.course_formation_groups g on g.course_id=c.id where c.period_id=p_period and c.active and g.group_code is not null
        ) x),
        'enrollments',(select coalesce(jsonb_agg(to_jsonb(x) order by x.class_id,x.student_id),'[]'::jsonb) from (
            select c.id class_id,e.student_id,e.active
            from public.enrollments e join public.profiles p on p.id=e.student_id and p.active and p.role='student'
            join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id and c.active
            join public.course_formation_groups g on g.course_id=c.id where e.period_id=p_period and g.group_code is not null
        ) x));
    return result||jsonb_build_object('token',md5(result::text));
end;
$$;

create function public.portal_formation_group_read(p_period uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
begin
    perform public._require_control_catalog_access();
    return public._formation_group_snapshot(p_period);
end;
$$;

create function public.portal_formation_group_write(p_action text,p_period uuid,p_stage text,p_semester integer,
    p_students uuid[],p_token text,p_classes uuid[] default '{}'::uuid[],p_reactivate boolean default false)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare students uuid[]; classes uuid[]; person uuid; course uuid; target_group text; matched integer;
    rev integer; previous public.enrollments%rowtype; c public.course_offerings%rowtype;
    assigned integer:=0; added integer:=0; restored integer:=0; skipped integer:=0; kept_inactive integer:=0;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    if p_action is null or p_action not in ('assign','enroll') or p_semester is null or not exists(
        select 1 from public.formation_stages where code=p_stage and p_semester between 1 and semesters)
        or p_students is null or coalesce(array_ndims(p_students),0)<>1 or cardinality(p_students) not between 1 and 500
        or array_position(p_students,null) is not null or p_reactivate is null then
        raise exception using errcode='22023',message='Selecciona un curso y entre 1 y 500 seminaristas'; end if;
    select array_agg(distinct x order by x) into students from unnest(p_students) x;
    perform id from public.academic_periods where id=p_period for share;
    if not found then raise exception using errcode='22023',message='Periodo no encontrado'; end if;
    -- También cubre ediciones directas de filas existentes durante la revisión del lote.
    perform id from public.profiles where active and role='student' order by id for share;
    perform id from public.course_offerings where period_id=p_period order by id for share;
    perform g.course_id from public.course_formation_groups g join public.course_offerings x on x.id=g.course_id
        where x.period_id=p_period order by g.course_id for share of g;
    perform student_id from public.student_formation_periods where period_id=p_period order by student_id for update;
    perform id from public.enrollments where period_id=p_period order by id for update;
    if p_token is null or p_token is distinct from (public._formation_group_snapshot(p_period)->>'token') then
        raise exception using errcode='PT409',message='El grupo o sus materias cambiaron. Cierra y actualiza antes de continuar.'; end if;
    select count(*) into matched from public.profiles where id=any(students) and active and role='student';
    if matched<>cardinality(students) then
        raise exception using errcode='22023',message='Un seminarista ya no está disponible. Actualiza la lista.'; end if;
    if p_action='assign' then
        if p_classes is distinct from '{}'::uuid[] or p_reactivate then
            raise exception using errcode='22023',message='La asignación del curso no debe incluir inscripciones'; end if;
        foreach person in array students loop
            if not exists(select 1 from public.student_formation_periods where student_id=person and period_id=p_period
                and stage_code=p_stage and semester=p_semester) then
                select coalesce((select revision from public.student_formation_periods
                    where student_id=person and period_id=p_period),0) into rev;
                perform public.portal_formation_save(person,p_period,p_stage,p_semester,rev);
                assigned:=assigned+1;
            end if;
        end loop;
        return jsonb_build_object('saved',true,'assigned',assigned,'unchanged',cardinality(students)-assigned);
    end if;
    if p_classes is null or coalesce(array_ndims(p_classes),0)<>1 or cardinality(p_classes) not between 1 and 100
        or array_position(p_classes,null) is not null then
        raise exception using errcode='22023',message='Selecciona entre 1 y 100 materias del curso'; end if;
    select array_agg(distinct x order by x) into classes from unnest(p_classes) x;
    if cardinality(students)*cardinality(classes)>5000 then
        raise exception using errcode='22023',message='El lote admite hasta 5000 inscripciones. Selecciona menos materias o seminaristas.'; end if;
    select count(*) into matched from public.student_formation_periods where student_id=any(students)
        and period_id=p_period and stage_code=p_stage and semester=p_semester;
    if matched<>cardinality(students) then
        raise exception using errcode='22023',message='Selecciona únicamente seminaristas de este curso y periodo'; end if;
    target_group:=case when p_stage='introductorio' then 'CI' else ((p_semester+1)/2)::text||case when p_stage='filosofia' then 'F' else 'T' end end||'-'||p_semester;
    select count(*) into matched from public.course_offerings x join public.course_formation_groups g on g.course_id=x.id
        where x.id=any(classes) and x.active and x.period_id=p_period and g.group_code=target_group;
    if matched<>cardinality(classes) then
        raise exception using errcode='22023',message='Una materia ya no pertenece a este curso y periodo. Actualiza.'; end if;
    foreach course in array classes loop
        select * into c from public.course_offerings where id=course;
        foreach person in array students loop
            select * into previous from public.enrollments where student_id=person and subject_id=c.subject_id and period_id=p_period;
            if previous.active then skipped:=skipped+1;
            elsif previous.id is not null and not p_reactivate then kept_inactive:=kept_inactive+1;
            else
                perform public.portal_admin_write('enroll',jsonb_build_object('class_id',course,'person_id',person));
                if previous.id is null then added:=added+1; else restored:=restored+1; end if;
            end if;
        end loop;
    end loop;
    return jsonb_build_object('saved',true,'enrolled',added,'reactivated',restored,'already_enrolled',skipped,'kept_inactive',kept_inactive);
end;
$$;

revoke all on function public._formation_group_snapshot(uuid),public.portal_formation_group_read(uuid),
    public.portal_formation_group_write(text,uuid,text,integer,uuid[],text,uuid[],boolean) from public,anon,authenticated;
grant execute on function public.portal_formation_group_read(uuid),
    public.portal_formation_group_write(text,uuid,text,integer,uuid[],text,uuid[],boolean) to authenticated;
notify pgrst,'reload schema';
commit;
