-- Calificaciones finales por grupo en Boletas y kardex.
-- Añade funciones. Al instalar no se actualiza ninguna nota ni boleta.
begin;

do $$
begin
    if to_regprocedure('public.portal_school_finals_save(uuid,text,jsonb,text)') is null
       or to_regprocedure('public._school_finals_snapshot(uuid)') is null
       or to_regclass('public.course_formation_groups') is null
       or to_regclass('public.student_formation_periods') is null then
        raise exception 'Faltan las actualizaciones de etapas y captura de finales de Control Escolar.';
    end if;
end;
$$;

create or replace function public._group_final_grades_snapshot(p_period uuid, p_group text)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_stage text;
    v_semester integer;
    v_result jsonb;
    v_revisions jsonb;
begin
    if p_period is null or not exists (select 1 from public.academic_periods where id = p_period)
       or p_group is null or p_group !~ '^(CI-[12]|[1-3]F-[1-6]|[1-4]T-[1-8])$' then
        raise exception using errcode = '22023', message = 'Selecciona un periodo y un grupo válidos.';
    end if;

    v_stage := case when left(p_group, 2) = 'CI' then 'introductorio'
                    when substr(p_group, 2, 1) = 'F' then 'filosofia' else 'teologia' end;
    v_semester := right(p_group, 1)::integer;
    if v_stage <> 'introductorio' and left(p_group, 1) <> ((v_semester + 1) / 2)::text then
        raise exception using errcode = '22023', message = 'Selecciona un grupo válido.';
    end if;

    -- Las bajas de inscripción no cuentan como pendientes. Las cuentas y clases
    -- inactivas conservan sus finales visibles en los periodos históricos.
    with roster as (
        select p.id, p.full_name as name, k.student_number,
               p.active and p.role = 'student' as editable, f.revision
        from public.student_formation_periods f
        join public.profiles p on p.id = f.student_id
        left join public.kardex_students k on k.student_id = p.id
        where f.period_id = p_period and f.stage_code = v_stage and f.semester = v_semester
    ), courses as (
        select c.id, c.subject_id, s.name, c.active,
               v.published is not null as configured, v.revision as scheme_revision,
               g.revision as group_revision
        from public.course_formation_groups g
        join public.course_offerings c on c.id = g.course_id
        join public.subjects s on s.id = c.subject_id
        left join public.learning_grading_schemes v on v.course_id = c.id
        where c.period_id = p_period and g.group_code = p_group
    ), cells as (
        select e.id as enrollment_id, e.student_id, c.id as course_id,
               case when g.published then g.score end as score,
               r.editable and c.active as editable,
               coalesce(g.published, false) or c.configured as requires_reason,
               g.score as grade_revision_score, d.revision as draft_revision,
               d.score as draft_revision_score, d.needs_publication as draft_needs_publication
        from public.enrollments e
        join roster r on r.id = e.student_id
        join courses c on c.subject_id = e.subject_id
        left join public.enrollment_grades g on g.enrollment_id = e.id
        left join public.enrollment_grade_drafts d on d.enrollment_id = e.id
        where e.period_id = p_period and e.active
    )
    select jsonb_build_object(
        'period_id', p_period,
        'group_code', p_group,
        'students', (select coalesce(jsonb_agg(to_jsonb(r) - 'revision' order by r.name, r.id), '[]') from roster r),
        'courses', (select coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name, 'active', c.active)
                                            order by c.name, c.id), '[]') from courses c),
        'cells', (select coalesce(jsonb_agg(to_jsonb(x) - 'grade_revision_score' - 'draft_revision'
                                              - 'draft_revision_score' - 'draft_needs_publication'
                                            order by x.enrollment_id), '[]') from cells x),
        'outside_count', (select count(*) from public.enrollments e join roster r on r.id = e.student_id
                          where e.period_id = p_period and e.active
                            and not exists (select 1 from courses c where c.subject_id = e.subject_id))
    ), jsonb_build_array(
        (select jsonb_agg(jsonb_build_array(id, revision) order by id) from roster),
        (select jsonb_agg(jsonb_build_array(id, group_revision, scheme_revision) order by id) from courses),
        (select jsonb_agg(jsonb_build_array(enrollment_id, grade_revision_score, draft_revision,
                                           draft_revision_score, draft_needs_publication) order by enrollment_id) from cells)
    )
    into v_result, v_revisions;

    if jsonb_array_length(v_result->'students') > 500 or jsonb_array_length(v_result->'courses') > 100
       or jsonb_array_length(v_result->'students') * jsonb_array_length(v_result->'courses') > 10000 then
        raise exception using errcode = '22023', message = 'El grupo es demasiado grande. Consulta las finales desde cada clase.';
    end if;
    return v_result || jsonb_build_object('token', md5(jsonb_build_array(v_result, v_revisions)::text));
end;
$$;

create or replace function public.portal_group_final_grades_read(p_period uuid default null, p_group text default null)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_period uuid := p_period;
    v_group text := p_group;
    v_periods jsonb;
    v_groups jsonb := '[]';
    v_snapshot jsonb;
    v_today date := (now() at time zone 'America/Matamoros')::date;
begin
    perform pg_catalog.pg_advisory_xact_lock_shared(72643219);
    perform public._require_control_catalog_access();

    select coalesce(jsonb_agg(jsonb_build_object('id', id, 'name', name) order by starts_on desc, id), '[]')
    into v_periods from public.academic_periods;
    if v_period is null then
        select id into v_period from public.academic_periods
        order by case when v_today between starts_on and ends_on then 0
                      when starts_on <= v_today then 1 else 2 end,
                 case when starts_on > v_today then starts_on end,
                 starts_on desc, id
        limit 1;
    elsif not exists (select 1 from public.academic_periods where id = v_period) then
        raise exception using errcode = '22023', message = 'El periodo ya no está disponible.';
    end if;

    if v_period is not null then
        select coalesce(jsonb_agg(jsonb_build_object('code', code, 'stage', stage)
                                  order by stage_order, semester), '[]'),
               (array_agg(code order by (has_students and has_courses) desc, stage_order, semester))[1]
        into v_groups, v_group
        from (
            select stage_order, stage, semester, code,
                   exists (select 1 from public.student_formation_periods f
                           where f.period_id = v_period and f.stage_code = g.stage_code and f.semester = g.semester) as has_students,
                   exists (select 1 from public.course_formation_groups m
                           join public.course_offerings c on c.id = m.course_id
                           where c.period_id = v_period and m.group_code = g.code) as has_courses
            from (
                select s.code as stage_code, s.name as stage, s.position as stage_order, n.semester,
                       (case when s.code = 'introductorio' then 'CI'
                             else ((n.semester + 1) / 2)::text || case when s.code = 'filosofia' then 'F' else 'T' end
                        end) || '-' || n.semester as code
                from public.formation_stages s
                cross join lateral generate_series(1, s.semesters) n(semester)
            ) g
        ) available
        where has_students or has_courses;

        if p_group is not null then
            if not exists (select 1 from jsonb_array_elements(v_groups) g where g->>'code' = p_group) then
                raise exception using errcode = '22023', message = 'El grupo ya no tiene seminaristas ni materias en este periodo.';
            end if;
            v_group := p_group;
        end if;
        if v_group is not null then
            v_snapshot := public._group_final_grades_snapshot(v_period, v_group);
        end if;
    end if;
    return jsonb_build_object('periods', v_periods, 'period_id', v_period, 'groups', v_groups, 'snapshot', v_snapshot);
end;
$$;

create or replace function public.portal_group_final_grades_save(
    p_period uuid, p_group text, p_token text, p_items jsonb, p_reason text, p_confirmed boolean
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_snapshot jsonb;
    v_item jsonb;
    v_course record;
    v_course_state jsonb;
    v_saved jsonb;
    v_changed integer := 0;
    v_score numeric;
    v_reason text := btrim(coalesce(p_reason, ''));
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();

    if p_confirmed is distinct from true then
        raise exception using errcode = '22023', message = 'Confirma la publicación de las notas finales.';
    end if;
    if p_items is null or jsonb_typeof(p_items) <> 'array' then
        raise exception using errcode = '22023', message = 'Selecciona las notas que vas a publicar.';
    end if;
    if jsonb_array_length(p_items) not between 1 and 500 or char_length(v_reason) > 1000 then
        raise exception using errcode = '22023', message = 'Selecciona entre 1 y 500 notas finales por publicación.';
    end if;

    v_snapshot := public._group_final_grades_snapshot(p_period, p_group);
    if p_token is null or p_token is distinct from v_snapshot->>'token' then
        raise exception using errcode = 'PT409', message = 'El grupo o sus notas cambiaron. Actualiza y vuelve a revisar antes de publicar.';
    end if;

    for v_item in select value from jsonb_array_elements(p_items) loop
        if jsonb_typeof(v_item) <> 'object' or v_item - 'enrollment_id' - 'score' <> '{}'::jsonb
           or jsonb_typeof(v_item->'enrollment_id') is distinct from 'string'
           or (v_item->>'enrollment_id') !~ '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
           or jsonb_typeof(v_item->'score') is distinct from 'number' then
            raise exception using errcode = '22023', message = 'Revisa las inscripciones y las notas que vas a publicar.';
        end if;
        v_score := (v_item->>'score')::numeric;
        if v_score not between 0 and 100 or v_score <> trunc(v_score) then
            raise exception using errcode = '22023', message = 'Escribe una calificación de 0 a 10 con un decimal.';
        end if;
    end loop;

    if (select count(distinct item->>'enrollment_id') from jsonb_array_elements(p_items) item)
        <> jsonb_array_length(p_items) then
        raise exception using errcode = '22023', message = 'Hay notas duplicadas en la selección.';
    end if;

    if exists (
        select 1 from jsonb_array_elements(p_items) item
        where not exists (
            select 1 from jsonb_array_elements(v_snapshot->'cells') cell
            where cell->>'enrollment_id' = item->>'enrollment_id' and (cell->>'editable')::boolean
        )
    ) then
        raise exception using errcode = '22023', message = 'Una inscripción no está activa o no pertenece al grupo seleccionado.';
    end if;

    -- Todas las materias se guardan en la misma transacción. La captura
    -- existente valida los motivos y conserva revisiones, autoría y auditoría.
    for v_course in
        select (cell->>'course_id')::uuid as id, jsonb_agg(item order by item->>'enrollment_id') as items
        from jsonb_array_elements(p_items) item
        join jsonb_array_elements(v_snapshot->'cells') cell on cell->>'enrollment_id' = item->>'enrollment_id'
        where (cell->>'score')::numeric is distinct from (item->>'score')::numeric
        group by 1
        order by 1
    loop
        v_course_state := public._school_finals_snapshot(v_course.id);
        v_saved := public.portal_school_finals_save(v_course.id, v_course_state->>'token', v_course.items, v_reason);
        v_changed := v_changed + (v_saved->>'changed')::integer;
    end loop;

    return jsonb_build_object('saved', true, 'changed', v_changed,
                              'snapshot', public._group_final_grades_snapshot(p_period, p_group));
end;
$$;

revoke all on function public._group_final_grades_snapshot(uuid, text),
    public.portal_group_final_grades_read(uuid, text),
    public.portal_group_final_grades_save(uuid, text, text, jsonb, text, boolean)
from public, anon, authenticated;
grant execute on function public.portal_group_final_grades_read(uuid, text),
    public.portal_group_final_grades_save(uuid, text, text, jsonb, text, boolean)
to authenticated;

notify pgrst, 'reload schema';
commit;
