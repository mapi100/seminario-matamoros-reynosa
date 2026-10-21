-- Ejecutar una sola vez, después del esquema profiles ya aplicado.
-- Esta etapa permite consulta; las altas se realizan desde administración.
begin;

create table public.subjects (
    id uuid primary key default gen_random_uuid(),
    code text not null unique check (length(btrim(code)) > 0),
    name text not null check (length(btrim(name)) > 0),
    created_at timestamptz not null default now()
);

create table public.academic_periods (
    id uuid primary key default gen_random_uuid(),
    name text not null unique check (length(btrim(name)) > 0),
    starts_on date not null,
    ends_on date not null check (ends_on >= starts_on),
    created_at timestamptz not null default now()
);

create table public.enrollments (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.profiles(id) on delete cascade,
    subject_id uuid not null references public.subjects(id) on delete restrict,
    period_id uuid not null references public.academic_periods(id) on delete restrict,
    created_at timestamptz not null default now(),
    unique (student_id, subject_id, period_id)
);

-- La restricción única ya empieza por student_id.
create index enrollments_subject_id_idx on public.enrollments (subject_id);
create index enrollments_period_id_idx on public.enrollments (period_id);

alter table public.subjects enable row level security;
alter table public.academic_periods enable row level security;
alter table public.enrollments enable row level security;

revoke all privileges on table public.subjects, public.academic_periods,
    public.enrollments from public, anon, authenticated;
grant select on table public.subjects, public.academic_periods,
    public.enrollments to authenticated;

-- profiles ya filtra por usuario y actividad. Comprobar también el rol evita
-- que una inscripción accidental habilite este módulo a un profesor o a CE.
create policy "Active students read own enrollments"
    on public.enrollments for select to authenticated
    using (
        student_id = (select auth.uid())
        and exists (
            select 1 from public.profiles p
            where p.id = (select auth.uid())
              and p.active = true
              and p.role = 'student'
        )
    );

-- Solo los catálogos vinculados a una inscripción visible son consultables.
-- No hay ciclo: enrollments consulta profiles, nunca estos catálogos.
create policy "Students read enrolled subjects"
    on public.subjects for select to authenticated
    using (
        exists (
            select 1 from public.enrollments e
            where e.subject_id = subjects.id
        )
    );

create policy "Students read enrolled periods"
    on public.academic_periods for select to authenticated
    using (
        exists (
            select 1 from public.enrollments e
            where e.period_id = academic_periods.id
        )
    );

commit;
