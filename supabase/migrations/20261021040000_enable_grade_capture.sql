-- Ejecutar una sola vez desde SQL Editor como administrador de confianza.
-- Los borradores se guardan separados de la nota que ve el alumno.
begin;

create table public.enrollment_grade_drafts (
    enrollment_id uuid primary key references public.enrollments(id) on delete restrict,
    score numeric(5, 2) not null check (score >= 0 and score <= 100),
    revision integer not null check (revision > 0),
    needs_publication boolean not null default true,
    updated_by uuid not null references public.profiles(id) on delete restrict,
    updated_at timestamptz not null default now()
);

create table public.enrollment_grade_events (
    id uuid primary key default gen_random_uuid(),
    enrollment_id uuid not null references public.enrollments(id) on delete restrict,
    actor_id uuid not null references public.profiles(id) on delete restrict,
    assignment_id uuid not null,
    action text not null check (action in ('save_draft', 'publish')),
    old_draft_score numeric(5, 2) check (old_draft_score >= 0 and old_draft_score <= 100),
    old_published_score numeric(5, 2) check (old_published_score >= 0 and old_published_score <= 100),
    score numeric(5, 2) not null check (score >= 0 and score <= 100),
    revision integer not null check (revision > 0),
    created_at timestamptz not null default now(),
    unique (enrollment_id, revision)
);
create index enrollment_grade_events_enrollment_idx
    on public.enrollment_grade_events(enrollment_id, created_at);

alter table public.enrollment_grade_drafts enable row level security;
alter table public.enrollment_grade_events enable row level security;
revoke all privileges on public.enrollment_grade_drafts, public.enrollment_grade_events
    from public, anon, authenticated;

-- Helper privado: el usuario no puede ejecutarlo. Los escritores adquieren
-- siempre el mismo bloqueo de inscripción y mantienen autorización y alumno
-- estables hasta terminar la transacción (FOR SHARE bloquea bajas/cambios de rol).
create function public._lock_teaching_grade(p_assignment_id uuid, p_enrollment_id uuid)
returns void
language plpgsql volatile security definer set search_path = ''
as $$
begin
    perform e.id
    from public.enrollments e
    join public.teaching_assignments t
      on t.subject_id = e.subject_id and t.period_id = e.period_id
    join public.profiles teacher on teacher.id = t.professor_id
    join public.profiles student on student.id = e.student_id
    where e.id = p_enrollment_id and t.id = p_assignment_id
      and t.professor_id = auth.uid()
      and teacher.active = true and teacher.role = 'professor'
      and student.active = true and student.role = 'student'
    for update of e
    for share of t, teacher, student;
    if not found then
        raise exception using errcode = '42501', message = 'No tienes acceso a esta calificación';
    end if;
end;
$$;
revoke all privileges on function public._lock_teaching_grade(uuid, uuid)
    from public, anon, authenticated;

create function public.get_teaching_grade(p_assignment_id uuid, p_enrollment_id uuid)
returns table (
    enrollment_id uuid, published_score numeric, draft_score numeric,
    revision integer, has_unpublished_changes boolean
)
language plpgsql stable security definer set search_path = ''
as $$
begin
    if not exists (
        select 1 from public.enrollments e
        join public.teaching_assignments t
          on t.subject_id = e.subject_id and t.period_id = e.period_id
        join public.profiles teacher on teacher.id = t.professor_id
        join public.profiles student on student.id = e.student_id
        where e.id = p_enrollment_id and t.id = p_assignment_id
          and t.professor_id = auth.uid()
          and teacher.active = true and teacher.role = 'professor'
          and student.active = true and student.role = 'student'
    ) then
        raise exception using errcode = '42501', message = 'No tienes acceso a esta calificación';
    end if;
    return query
        select e.id,
               case when g.published then g.score else null end,
               coalesce(d.score, case when g.published = false then g.score else null end),
               coalesce(d.revision, 0),
               coalesce(d.needs_publication, false)
        from public.enrollments e
        left join public.enrollment_grades g on g.enrollment_id = e.id
        left join public.enrollment_grade_drafts d on d.enrollment_id = e.id
        where e.id = p_enrollment_id;
end;
$$;

create function public.save_teaching_grade(
    p_assignment_id uuid, p_enrollment_id uuid, p_score numeric,
    p_expected_revision integer
)
returns table (
    enrollment_id uuid, published_score numeric, draft_score numeric,
    revision integer, has_unpublished_changes boolean
)
language plpgsql volatile security definer set search_path = ''
as $$
declare
    current_revision integer;
    new_revision integer;
    previous_draft numeric;
    previous_published numeric;
    legacy_draft numeric;
begin
    perform public._lock_teaching_grade(p_assignment_id, p_enrollment_id);
    if p_score is null or p_score < 0 or p_score > 100 or p_score <> round(p_score, 2)
       or p_expected_revision is null or p_expected_revision < 0 then
        raise exception using errcode = '22023', message = 'La nota debe estar entre 0 y 100 y tener hasta dos decimales';
    end if;
    select d.revision, d.score into current_revision, previous_draft from public.enrollment_grade_drafts d
    where d.enrollment_id = p_enrollment_id;
    select case when g.published then g.score else null end,
           case when g.published = false then g.score else null end
    into previous_published, legacy_draft
    from public.enrollment_grades g where g.enrollment_id = p_enrollment_id;
    previous_draft := coalesce(previous_draft, legacy_draft);
    current_revision := coalesce(current_revision, 0);
    if current_revision <> p_expected_revision then
        raise exception using errcode = 'PT409', message = 'La calificación cambió; vuelve a cargarla antes de guardar';
    end if;
    new_revision := current_revision + 1;
    insert into public.enrollment_grade_drafts as d
        (enrollment_id, score, revision, needs_publication, updated_by, updated_at)
    values (p_enrollment_id, p_score, new_revision, true, auth.uid(), clock_timestamp())
    on conflict on constraint enrollment_grade_drafts_pkey do update
    set score = excluded.score, revision = excluded.revision,
        needs_publication = true, updated_by = excluded.updated_by,
        updated_at = excluded.updated_at;
    insert into public.enrollment_grade_events
        (enrollment_id, actor_id, assignment_id, action, old_draft_score, old_published_score, score, revision)
    values (p_enrollment_id, auth.uid(), p_assignment_id, 'save_draft', previous_draft, previous_published, p_score, new_revision);
    return query select * from public.get_teaching_grade(p_assignment_id, p_enrollment_id);
end;
$$;

create function public.publish_teaching_grade(
    p_assignment_id uuid, p_enrollment_id uuid, p_expected_revision integer
)
returns table (
    enrollment_id uuid, published_score numeric, draft_score numeric,
    revision integer, has_unpublished_changes boolean
)
language plpgsql volatile security definer set search_path = ''
as $$
declare
    draft public.enrollment_grade_drafts%rowtype;
    previous_published numeric;
begin
    perform public._lock_teaching_grade(p_assignment_id, p_enrollment_id);
    if p_expected_revision is null or p_expected_revision < 0 then
        raise exception using errcode = '22023', message = 'Revisión inválida';
    end if;
    select d.* into draft from public.enrollment_grade_drafts d
    where d.enrollment_id = p_enrollment_id;
    if coalesce(draft.revision, 0) <> p_expected_revision then
        raise exception using errcode = 'PT409', message = 'La calificación cambió; vuelve a cargarla antes de publicar';
    end if;
    if draft.enrollment_id is null or draft.needs_publication = false then
        raise exception using errcode = '22023', message = 'Guarda un borrador nuevo antes de publicar';
    end if;
    select g.score into previous_published from public.enrollment_grades g
    where g.enrollment_id = p_enrollment_id and g.published = true;
    insert into public.enrollment_grades(enrollment_id, score, published)
    values (p_enrollment_id, draft.score, true)
    on conflict on constraint enrollment_grades_pkey do update
    set score = excluded.score, published = true;
    update public.enrollment_grade_drafts d
    set revision = d.revision + 1, needs_publication = false,
        updated_by = auth.uid(), updated_at = clock_timestamp()
    where d.enrollment_id = p_enrollment_id;
    insert into public.enrollment_grade_events
        (enrollment_id, actor_id, assignment_id, action, old_draft_score, old_published_score, score, revision)
    values (p_enrollment_id, auth.uid(), p_assignment_id, 'publish', draft.score, previous_published, draft.score, draft.revision + 1);
    return query select * from public.get_teaching_grade(p_assignment_id, p_enrollment_id);
end;
$$;

revoke all privileges on function public.get_teaching_grade(uuid, uuid),
    public.save_teaching_grade(uuid, uuid, numeric, integer),
    public.publish_teaching_grade(uuid, uuid, integer)
    from public, anon, authenticated;
grant execute on function public.get_teaching_grade(uuid, uuid),
    public.save_teaching_grade(uuid, uuid, numeric, integer),
    public.publish_teaching_grade(uuid, uuid, integer)
    to authenticated;

commit;
