-- Ejecutar una sola vez después de las migraciones de perfiles, materias y notas.
begin;

create table public.teaching_assignments (
    id uuid primary key default gen_random_uuid(),
    professor_id uuid not null references public.profiles(id) on delete restrict,
    subject_id uuid not null references public.subjects(id) on delete restrict,
    period_id uuid not null references public.academic_periods(id) on delete restrict,
    created_at timestamptz not null default now(),
    unique (professor_id, subject_id, period_id)
);

create index teaching_assignments_subject_id_idx on public.teaching_assignments (subject_id);
create index teaching_assignments_period_id_idx on public.teaching_assignments (period_id);
alter table public.teaching_assignments enable row level security;
revoke all privileges on table public.teaching_assignments from public, anon, authenticated;
grant select on table public.teaching_assignments to authenticated;

create policy "Active professors read own teaching assignments"
    on public.teaching_assignments for select to authenticated
    using (
        professor_id = (select auth.uid())
        and exists (
            select 1 from public.profiles p
            where p.id = (select auth.uid()) and p.active = true and p.role = 'professor'
        )
    );

-- Los catálogos se amplían solo para las asignaciones visibles del profesor.
-- No se amplían profiles, enrollments ni enrollment_grades.
create policy "Professors read assigned subjects"
    on public.subjects for select to authenticated
    using (exists (
        select 1 from public.teaching_assignments t where t.subject_id = subjects.id
    ));

create policy "Professors read assigned periods"
    on public.academic_periods for select to authenticated
    using (exists (
        select 1 from public.teaching_assignments t where t.period_id = academic_periods.id
    ));

-- Único acceso al listado de alumnos: dos columnas y autorización explícita.
-- El propietario de esta función debe ser el administrador de confianza que
-- aplica la migración. search_path vacío y nombres completos evitan sustituciones.
create function public.get_teaching_roster(
    p_assignment_id uuid,
    p_offset integer default 0,
    p_limit integer default 20
)
returns table (enrollment_id uuid, student_name text)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    actor uuid := auth.uid();
    assigned_subject uuid;
    assigned_period uuid;
begin
    select t.subject_id, t.period_id into assigned_subject, assigned_period
    from public.teaching_assignments t
    join public.profiles p on p.id = t.professor_id
    where t.id = p_assignment_id and t.professor_id = actor
      and p.active = true and p.role = 'professor';

    if not found then
        raise exception using errcode = '42501', message = 'No tienes acceso a esta lista';
    end if;
    if p_offset is null or p_offset < 0 or p_offset > 100000
       or p_limit is null or p_limit < 1 or p_limit > 100 then
        raise exception using errcode = '22023', message = 'Paginación inválida';
    end if;

    return query
        select e.id, p.full_name
        from public.enrollments e
        join public.profiles p on p.id = e.student_id
        where e.subject_id = assigned_subject and e.period_id = assigned_period
          and p.active = true and p.role = 'student'
        order by p.full_name asc, e.id asc
        offset p_offset limit p_limit;
end;
$$;

revoke all privileges on function public.get_teaching_roster(uuid, integer, integer)
    from public, anon, authenticated;
grant execute on function public.get_teaching_roster(uuid, integer, integer)
    to authenticated;

commit;
