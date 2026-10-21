-- Ejecutar una sola vez desde SQL Editor como administrador de confianza.
-- Control Escolar puede consultar y crear catálogos; no se concede DML directo.
begin;

-- No se reescriben datos existentes. Si hay duplicados normalizados, la
-- migración falla y revierte: deben revisarse antes de volver a aplicarla.
create unique index subjects_code_normalized_key
    on public.subjects (lower(btrim(code)));
create unique index academic_periods_name_normalized_key
    on public.academic_periods (lower(btrim(name)));

create policy "Active control staff read subjects"
    on public.subjects for select to authenticated
    using (exists (
        select 1 from public.profiles p
        where p.id = (select auth.uid()) and p.active = true and p.role = 'control_escolar'
    ));
create policy "Active control staff read periods"
    on public.academic_periods for select to authenticated
    using (exists (
        select 1 from public.profiles p
        where p.id = (select auth.uid()) and p.active = true and p.role = 'control_escolar'
    ));

create table public.catalog_events (
    id uuid primary key default gen_random_uuid(),
    actor_id uuid not null references public.profiles(id) on delete restrict,
    action text not null check (action in ('subject_created', 'period_created')),
    entity_id uuid not null,
    details jsonb not null,
    created_at timestamptz not null default now()
);
alter table public.catalog_events enable row level security;
revoke all privileges on public.catalog_events from public, anon, authenticated;

create function public._require_control_catalog_access()
returns uuid
language plpgsql volatile security definer set search_path = ''
as $$
declare
    actor uuid;
begin
    select p.id into actor from public.profiles p
    where p.id = auth.uid() and p.active = true and p.role = 'control_escolar'
    for share of p;
    if not found then
        raise exception using errcode = '42501', message = 'No tienes permiso para administrar catálogos';
    end if;
    return actor;
end;
$$;
revoke all privileges on function public._require_control_catalog_access()
    from public, anon, authenticated;

-- Mismo conjunto de espacios que String.trim() en el navegador. btrim(text)
-- solo recorta U+0020: sin esta comprobación un nombre de NBSP podría crearse
-- por RPC y luego ser rechazado como vacío al mostrar el catálogo.
create function public._catalog_text_has_content(p_value text)
returns boolean
language sql immutable parallel safe set search_path = ''
as $$
    select p_value is not null and length(btrim(p_value,
        U&'\0009\000A\000B\000C\000D\0020\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000\FEFF')) > 0
$$;
revoke all privileges on function public._catalog_text_has_content(text)
    from public, anon, authenticated;

create function public.create_subject(p_code text, p_name text)
returns table (id uuid, code text, name text, created_at timestamptz)
language plpgsql volatile security definer set search_path = ''
as $$
declare
    actor uuid := public._require_control_catalog_access();
    normalized_code text := upper(btrim(p_code));
    normalized_name text := btrim(p_name);
    created public.subjects%rowtype;
begin
    if not public._catalog_text_has_content(normalized_code)
       or char_length(normalized_code) not between 1 and 40
       or not public._catalog_text_has_content(normalized_name)
       or char_length(normalized_name) not between 1 and 160
       or normalized_code ~ '[[:cntrl:]]' or normalized_name ~ '[[:cntrl:]]' then
        raise exception using errcode = '22023', message = 'Código y nombre de materia inválidos';
    end if;
    begin
        insert into public.subjects as s (code, name)
        values (normalized_code, normalized_name) returning s.* into created;
    exception when unique_violation then
        raise exception using errcode = 'PT409', message = 'Ya existe una materia con ese código';
    end;
    insert into public.catalog_events(actor_id, action, entity_id, details)
    values (actor, 'subject_created', created.id,
        jsonb_build_object('code', created.code, 'name', created.name));
    return query select created.id, created.code, created.name, created.created_at;
end;
$$;

create function public.create_academic_period(p_name text, p_starts_on date, p_ends_on date)
returns table (id uuid, name text, starts_on date, ends_on date, created_at timestamptz)
language plpgsql volatile security definer set search_path = ''
as $$
declare
    actor uuid := public._require_control_catalog_access();
    normalized_name text := btrim(p_name);
    created public.academic_periods%rowtype;
begin
    if not public._catalog_text_has_content(normalized_name)
       or char_length(normalized_name) not between 1 and 120
       or normalized_name ~ '[[:cntrl:]]'
       or p_starts_on is null or p_ends_on is null
       or not isfinite(p_starts_on) or not isfinite(p_ends_on)
       or p_starts_on < date '0001-01-01' or p_ends_on > date '9999-12-31'
       or p_ends_on < p_starts_on then
        raise exception using errcode = '22023', message = 'Nombre o fechas del periodo inválidos';
    end if;
    begin
        insert into public.academic_periods as p (name, starts_on, ends_on)
        values (normalized_name, p_starts_on, p_ends_on) returning p.* into created;
    exception when unique_violation then
        raise exception using errcode = 'PT409', message = 'Ya existe un periodo con ese nombre';
    end;
    insert into public.catalog_events(actor_id, action, entity_id, details)
    values (actor, 'period_created', created.id, jsonb_build_object(
        'name', created.name, 'starts_on', created.starts_on, 'ends_on', created.ends_on));
    return query select created.id, created.name, created.starts_on, created.ends_on, created.created_at;
end;
$$;

revoke all privileges on function public.create_subject(text, text),
    public.create_academic_period(text, date, date) from public, anon, authenticated;
grant execute on function public.create_subject(text, text),
    public.create_academic_period(text, date, date) to authenticated;

commit;
