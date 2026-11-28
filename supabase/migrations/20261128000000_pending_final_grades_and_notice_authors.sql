-- Restituye calificaciones finales a Pendiente y agrega la autoría de los avisos.
-- Al instalar se conservan las notas, los borradores, las boletas y las lecturas.
begin;

select pg_catalog.pg_advisory_xact_lock(72643219);

alter table public.enrollment_grades
    alter column score drop not null,
    drop constraint if exists enrollment_grades_published_score_check,
    add constraint enrollment_grades_published_score_check check (not published or score is not null);

alter table public.enrollment_grade_drafts
    alter column score drop not null,
    drop constraint if exists enrollment_grade_drafts_pending_score_check,
    add constraint enrollment_grade_drafts_pending_score_check check (not needs_publication or score is not null);

alter table public.enrollment_grade_events
    alter column score drop not null,
    drop constraint if exists enrollment_grade_events_action_check,
    add constraint enrollment_grade_events_action_check check (action in ('save_draft', 'publish', 'unpublish')),
    drop constraint if exists enrollment_grade_events_pending_score_check,
    add constraint enrollment_grade_events_pending_score_check check ((action = 'unpublish') = (score is null));

alter table public.control_activity_notices
    add column if not exists actor_id uuid,
    drop constraint if exists control_activity_notices_kind_check,
    add constraint control_activity_notices_kind_check check (kind in ('final_corrected', 'final_pending', 'personal_updated')),
    drop constraint if exists control_activity_notices_check,
    add constraint control_activity_notices_check check (
        (kind in ('final_corrected', 'final_pending') and subject_id is not null and period_id is not null)
        or (kind = 'personal_updated' and subject_id is null and period_id is null)
    );

-- Los avisos de expediente solo se emitían para la edición propia.
update public.control_activity_notices set actor_id = student_id
where kind = 'personal_updated' and actor_id is null;

-- El aviso y la auditoría de una corrección se insertaron en la misma
-- transacción. Recuperamos el autor únicamente si coincide la inscripción,
-- la transacción se puede identificar y hay un único autor en la auditoría.
with authors as (
    select n.id, min(ev.actor_id::text)::uuid as actor_id
    from public.control_activity_notices n
    join public.enrollments e
      on e.student_id = n.student_id and e.subject_id = n.subject_id and e.period_id = n.period_id
    join public.enrollment_grade_events ev
      on ev.enrollment_id = e.id and ev.xmin = n.xmin
      and ev.created_at <= n.created_at and n.created_at - ev.created_at < interval '1 day'
    where n.kind = 'final_corrected' and n.actor_id is null and n.xmin::text::bigint >= 3
      and ev.action = 'publish' and ev.old_published_score is not null
      and ev.old_published_score is distinct from ev.score
    group by n.id
    having count(distinct ev.actor_id) = 1
)
update public.control_activity_notices n set actor_id = a.actor_id
from authors a where a.id = n.id;

create or replace function public._control_notice_final_corrected()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    insert into public.control_activity_notices(kind, student_id, subject_id, period_id, actor_id)
    select case when new.published then 'final_corrected' else 'final_pending' end,
           e.student_id, e.subject_id, e.period_id, p.id
    from public.enrollments e
    join public.profiles p on p.id = auth.uid() and p.active and p.role in ('professor', 'control_escolar')
    where e.id = new.enrollment_id;
    return new;
end;
$$;

create or replace trigger control_notice_final_corrected
after update of score, published on public.enrollment_grades
for each row
when (old.published and (not new.published or old.score is distinct from new.score))
execute function public._control_notice_final_corrected();

create or replace function public._control_notice_personal_updated()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    insert into public.control_activity_notices(kind, student_id, actor_id)
    select 'personal_updated', new.entity_id, p.id
    from public.profiles p
    where p.id = new.actor_id and p.id = auth.uid() and p.active and p.role = 'student';
    return new;
end;
$$;

create or replace function public.portal_control_activity_read(
    p_count_only boolean default false, p_before bigint default null
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_reader uuid := public._require_control_catalog_access();
    v_rows jsonb := '[]';
    v_unread bigint;
    v_next bigint;
begin
    if p_count_only is null or p_before is not null and (p_before <= 0 or p_count_only) then
        raise exception using errcode = '22023', message = 'Consulta de avisos inválida.';
    end if;

    -- Una sola sentencia comparte la misma vista de datos para contador y lista.
    select public._control_activity_unread(v_reader), coalesce((
        select jsonb_agg(to_jsonb(x) order by x.id desc)
        from (
            select n.id, n.kind, n.created_at, p.full_name as student_name,
                   s.name as subject_name, a.name as period_name, actor.full_name as actor_name,
                   r.notice_id is not null as read
            from public.control_activity_notices n
            left join public.control_activity_notice_reads r on r.reader_id = v_reader and r.notice_id = n.id
            left join public.profiles p on p.id = n.student_id
            left join public.profiles actor on actor.id = n.actor_id
            left join public.subjects s on s.id = n.subject_id
            left join public.academic_periods a on a.id = n.period_id
            where not p_count_only and (p_before is null or n.id < p_before)
            order by n.id desc
            limit 21
        ) x
    ), '[]')
    into v_unread, v_rows;

    if jsonb_array_length(v_rows) > 20 then
        v_rows := v_rows - 20;
        v_next := (v_rows->19->>'id')::bigint;
    end if;
    return jsonb_build_object('unread', v_unread, 'items', v_rows, 'next_before', v_next);
end;
$$;

create or replace function public.portal_group_final_grades_save(
    p_period uuid, p_group text, p_token text, p_items jsonb, p_reason text, p_confirmed boolean
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_actor uuid;
    v_snapshot jsonb;
    v_item jsonb;
    v_course record;
    v_pending record;
    v_revision integer;
    v_course_state jsonb;
    v_saved jsonb;
    v_changed integer := 0;
    v_score numeric;
    v_reason text := btrim(coalesce(p_reason, ''));
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    v_actor := public._require_control_catalog_access();

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
           or coalesce(jsonb_typeof(v_item->'score'), '') not in ('number', 'null') then
            raise exception using errcode = '22023', message = 'Revisa las inscripciones y las notas que vas a publicar.';
        end if;
        v_score := (v_item->>'score')::numeric;
        if v_score is not null and (v_score not between 0 and 100 or v_score <> trunc(v_score)) then
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

    -- La captura numérica conserva sus validaciones y auditoría.
    for v_course in
        select (cell->>'course_id')::uuid as id, jsonb_agg(item order by item->>'enrollment_id') as items
        from jsonb_array_elements(p_items) item
        join jsonb_array_elements(v_snapshot->'cells') cell on cell->>'enrollment_id' = item->>'enrollment_id'
        where item->>'score' is not null
          and (cell->>'score')::numeric is distinct from (item->>'score')::numeric
        group by 1
        order by 1
    loop
        v_course_state := public._school_finals_snapshot(v_course.id);
        v_saved := public.portal_school_finals_save(v_course.id, v_course_state->>'token', v_course.items, v_reason);
        v_changed := v_changed + (v_saved->>'changed')::integer;
    end loop;

    -- Una nota pendiente conserva su revisión y el historial. Un borrador
    -- docente con cambios sin publicar es independiente de la nota final.
    for v_pending in
        select (cell->>'enrollment_id')::uuid as enrollment_id,
               (cell->>'course_id')::uuid as course_id,
               (cell->>'score')::numeric as previous_final,
               d.score as previous_draft
        from jsonb_array_elements(p_items) item
        join jsonb_array_elements(v_snapshot->'cells') cell on cell->>'enrollment_id' = item->>'enrollment_id'
        left join public.enrollment_grade_drafts d on d.enrollment_id = (cell->>'enrollment_id')::uuid
        where item->'score' = 'null'::jsonb and cell->>'score' is not null
        order by (cell->>'enrollment_id')::uuid
    loop
        update public.enrollment_grades
        set score = null, published = false
        where enrollment_id = v_pending.enrollment_id;

        insert into public.enrollment_grade_drafts as d
            (enrollment_id, score, revision, needs_publication, updated_by)
        values (v_pending.enrollment_id, null, 1, false, v_actor)
        on conflict (enrollment_id) do update
        set revision = d.revision + 1,
            score = case when d.needs_publication then d.score end,
            updated_by = case when d.needs_publication then d.updated_by else excluded.updated_by end,
            updated_at = case when d.needs_publication then d.updated_at else now() end
        returning revision into v_revision;

        insert into public.enrollment_grade_events
            (enrollment_id, actor_id, assignment_id, action, old_draft_score, old_published_score, score, revision)
        values (v_pending.enrollment_id, v_actor, v_pending.course_id, 'unpublish',
                v_pending.previous_draft, v_pending.previous_final, null, v_revision);
        insert into public.learning_audit(actor_id, course_id, action, entity_id, details)
        values (v_actor, v_pending.course_id, 'school_final_unpublish', v_pending.enrollment_id,
                jsonb_build_object('before', v_pending.previous_final, 'after', null));
        v_changed := v_changed + 1;
    end loop;

    return jsonb_build_object('saved', true, 'changed', v_changed,
                              'snapshot', public._group_final_grades_snapshot(p_period, p_group));
end;
$$;

notify pgrst, 'reload schema';
commit;
