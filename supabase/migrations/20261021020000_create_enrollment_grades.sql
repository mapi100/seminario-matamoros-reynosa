-- Ejecutar una sola vez, después de profiles y create_academics.
-- Escala acordada: 0 a 100, con hasta dos decimales.
begin;

create table public.enrollment_grades (
    enrollment_id uuid primary key
        references public.enrollments(id) on delete restrict,
    score numeric(5, 2) not null check (score >= 0 and score <= 100),
    published boolean not null default false,
    created_at timestamptz not null default now()
);

alter table public.enrollment_grades enable row level security;

revoke all privileges on table public.enrollment_grades
    from public, anon, authenticated;
grant select on table public.enrollment_grades to authenticated;

-- Se repiten propietario, actividad y rol expresamente: una futura ampliación
-- de permisos sobre inscripciones no debe ampliar el acceso a calificaciones.
create policy "Active students read own published grades"
    on public.enrollment_grades for select to authenticated
    using (
        published = true
        and exists (
            select 1
            from public.enrollments e
            join public.profiles p on p.id = e.student_id
            where e.id = enrollment_grades.enrollment_id
              and e.student_id = (select auth.uid())
              and p.id = (select auth.uid())
              and p.active = true
              and p.role = 'student'
        )
    );

commit;
