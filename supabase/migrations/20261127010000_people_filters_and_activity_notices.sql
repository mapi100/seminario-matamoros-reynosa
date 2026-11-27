-- Filtros de Personas y avisos privados de Actividad para Control Escolar.
-- Transaccional y repetible. No crea avisos históricos ni altera personas, notas o expedientes.
begin;

create or replace function public.portal_people_by_role(
    p_role text, p_search text default '', p_offset integer default 0, p_limit integer default 30
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_needle text := lower(btrim(coalesce(p_search, '')));
    v_rows jsonb;
    v_more boolean;
begin
    perform public._require_control_catalog_access();
    if p_role is null or p_role not in ('student', 'professor', 'control_escolar')
       or p_offset is null or p_offset not between 0 and 100000
       or p_limit is null or p_limit not between 1 and 100 or char_length(v_needle) > 160 then
        raise exception using errcode = '22023', message = 'Consulta de personas inválida.';
    end if;

    select coalesce(jsonb_agg(to_jsonb(x) order by x.full_name, x.id), '[]')
    into v_rows
    from (
        select p.id, p.full_name, p.role, p.active, p.management_revision, u.email
        from public.profiles p join auth.users u on u.id = p.id
        where p.role = p_role
          and (v_needle = '' or strpos(lower(p.full_name || ' ' || coalesce(u.email, '')), v_needle) > 0)
        order by p.full_name, p.id
        offset p_offset limit p_limit + 1
    ) x;

    v_more := jsonb_array_length(v_rows) > p_limit;
    return jsonb_build_object('items', case when v_more then v_rows - p_limit else v_rows end, 'has_more', v_more);
end;
$$;

create table if not exists public.control_activity_notices (
    id bigint generated always as identity primary key,
    kind text not null check (kind in ('final_corrected', 'personal_updated')),
    student_id uuid not null,
    subject_id uuid,
    period_id uuid,
    created_at timestamptz not null default clock_timestamp(),
    check (
        (kind = 'final_corrected' and subject_id is not null and period_id is not null)
        or (kind = 'personal_updated' and subject_id is null and period_id is null)
    )
);

create table if not exists public.control_activity_notice_reads (
    reader_id uuid not null references public.profiles(id) on delete cascade,
    notice_id bigint not null references public.control_activity_notices(id) on delete cascade,
    primary key (reader_id, notice_id)
);

alter table public.control_activity_notices enable row level security;
alter table public.control_activity_notice_reads enable row level security;
revoke all on public.control_activity_notices, public.control_activity_notice_reads from public, anon, authenticated;
revoke all on sequence public.control_activity_notices_id_seq from public, anon, authenticated;

-- La tabla de finales recibe todos los caminos de publicación, incluida la
-- captura por grupo. El WHEN excluye inserciones, primera publicación y no-op.
create or replace function public._control_notice_final_corrected()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    insert into public.control_activity_notices(kind, student_id, subject_id, period_id)
    select 'final_corrected', e.student_id, e.subject_id, e.period_id
    from public.enrollments e
    where e.id = new.enrollment_id
      and exists (select 1 from public.profiles p
                  where p.id = auth.uid() and p.active and p.role in ('professor', 'control_escolar'));
    return new;
end;
$$;

create or replace trigger control_notice_final_corrected
after update of score, published on public.enrollment_grades
for each row
when (old.published and new.published and old.score is distinct from new.score)
execute function public._control_notice_final_corrected();

-- El guardado del expediente ya audita solamente cambios efectivos. Se toma
-- el evento de edición propia, sin copiar campos personales ni sus valores.
create or replace function public._control_notice_personal_updated()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    insert into public.control_activity_notices(kind, student_id)
    select 'personal_updated', new.entity_id
    where new.actor_id = auth.uid()
      and exists (select 1 from public.profiles p where p.id = new.actor_id and p.active and p.role = 'student');
    return new;
end;
$$;

create or replace trigger control_notice_personal_updated
after insert on public.management_events
for each row
when (
    new.action = 'student_record_saved'
    and new.actor_id = new.entity_id
    and new.details->>'source' = 'student'
)
execute function public._control_notice_personal_updated();

create or replace function public._control_activity_unread(p_reader uuid)
returns bigint
language sql stable set search_path = ''
as $$
    select count(*) from public.control_activity_notices n
    where not exists (select 1 from public.control_activity_notice_reads r
                      where r.reader_id = p_reader and r.notice_id = n.id)
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
                   s.name as subject_name, a.name as period_name,
                   r.notice_id is not null as read
            from public.control_activity_notices n
            left join public.control_activity_notice_reads r on r.reader_id = v_reader and r.notice_id = n.id
            left join public.profiles p on p.id = n.student_id
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

create or replace function public.portal_control_activity_mark(
    p_notice_id bigint default null, p_all boolean default false
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
    v_reader uuid := public._require_control_catalog_access();
begin
    if p_all is null or (p_all and p_notice_id is not null)
       or (not p_all and (p_notice_id is null or p_notice_id <= 0)) then
        raise exception using errcode = '22023', message = 'Selecciona un aviso o marca todos como leídos.';
    end if;

    insert into public.control_activity_notice_reads(reader_id, notice_id)
    select v_reader, n.id
    from public.control_activity_notices n
    where (p_all or n.id = p_notice_id)
      and not exists (select 1 from public.control_activity_notice_reads r
                      where r.reader_id = v_reader and r.notice_id = n.id)
    order by n.id
    on conflict (reader_id, notice_id) do nothing;
    return jsonb_build_object('saved', true, 'unread', public._control_activity_unread(v_reader));
end;
$$;

revoke all on function public._control_notice_final_corrected(),
    public._control_notice_personal_updated(), public._control_activity_unread(uuid),
    public.portal_people_by_role(text, text, integer, integer),
    public.portal_control_activity_read(boolean, bigint),
    public.portal_control_activity_mark(bigint, boolean)
from public, anon, authenticated;

grant execute on function public.portal_people_by_role(text, text, integer, integer),
    public.portal_control_activity_read(boolean, bigint),
    public.portal_control_activity_mark(bigint, boolean)
to authenticated;

notify pgrst, 'reload schema';
commit;
