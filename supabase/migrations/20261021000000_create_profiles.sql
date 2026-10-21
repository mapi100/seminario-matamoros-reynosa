-- Esquema inicial para un proyecto nuevo que todavía no tenga profiles.
-- El proyecto actual ya recibió este SQL manualmente desde SQL Editor.
begin;

create table public.profiles (
    id uuid primary key
        references auth.users(id)
        on delete cascade,

    full_name text not null
        check (length(btrim(full_name)) > 0),

    role text not null
        check (
            role in (
                'student',
                'professor',
                'control_escolar'
            )
        ),

    active boolean not null default true,

    created_at timestamptz not null default now()
);

alter table public.profiles
    enable row level security;

revoke all privileges
    on table public.profiles
    from public, anon, authenticated;

grant usage
    on schema public
    to authenticated;

grant select
    on table public.profiles
    to authenticated;

create policy "Users can read own active profile"
    on public.profiles
    for select
    to authenticated
    using (
        (select auth.uid()) = id
        and active = true
    );

commit;
