-- Prueba de solo lectura. Requiere al menos una inscripción del alumno.
begin read only;
set local request.jwt.claim.sub = 'PEGA_AQUI_EL_UID';
select set_config(
    'request.jwt.claims',
    json_build_object('sub', current_setting('request.jwt.claim.sub'),
                      'role', 'authenticated')::text,
    true
);
set local role authenticated;

do $$
declare
    expected_uid uuid := current_setting('request.jwt.claim.sub')::uuid;
    other_uid constant uuid := '00000000-0000-0000-0000-000000000000';
    table_name text;
begin
    if current_user <> 'authenticated' or auth.uid() is distinct from expected_uid
       or expected_uid = other_uid then
        raise exception 'FALLO: no se pudo simular la identidad de prueba';
    end if;
    if not exists (
        select 1 from public.profiles
        where id = expected_uid and role = 'student' and active = true
    ) then
        raise exception 'FALLO: se requiere un alumno de prueba activo';
    end if;

    foreach table_name in array array['subjects', 'academic_periods', 'enrollments'] loop
        if not exists (
            select 1 from pg_catalog.pg_class c
            join pg_catalog.pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relname = table_name
              and c.relrowsecurity = true
        ) then
            raise exception 'FALLO: RLS no está activado en %', table_name;
        end if;
        if not has_table_privilege(current_user, 'public.' || table_name, 'SELECT') then
            raise exception 'FALLO: falta SELECT sobre %', table_name;
        end if;
        if has_table_privilege(current_user, 'public.' || table_name,
            'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
           or has_any_column_privilege(current_user, 'public.' || table_name,
            'INSERT, UPDATE, REFERENCES') then
            raise exception 'FALLO: authenticated conserva escritura sobre %', table_name;
        end if;
        if has_table_privilege('anon', 'public.' || table_name,
            'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
           or has_any_column_privilege('anon', 'public.' || table_name,
            'SELECT, INSERT, UPDATE, REFERENCES') then
            raise exception 'FALLO: anon conserva permisos sobre %', table_name;
        end if;
    end loop;

    if not exists (select 1 from public.enrollments) then
        raise exception 'FALLO: el alumno de prueba no tiene inscripciones visibles';
    end if;
    if exists (select 1 from public.enrollments where student_id <> expected_uid) then
        raise exception 'FALLO: son visibles inscripciones ajenas';
    end if;
    if exists (
        select 1 from public.subjects s
        where not exists (select 1 from public.enrollments e where e.subject_id = s.id)
    ) or exists (
        select 1 from public.academic_periods p
        where not exists (select 1 from public.enrollments e where e.period_id = p.id)
    ) then
        raise exception 'FALLO: es visible un catálogo no vinculado al alumno';
    end if;
    if exists (
        select 1 from public.enrollments e
        left join public.subjects s on s.id = e.subject_id
        left join public.academic_periods p on p.id = e.period_id
        where s.id is null or p.id is null
    ) then
        raise exception 'FALLO: faltan catálogos de una inscripción propia';
    end if;

    perform set_config('request.jwt.claim.sub', other_uid::text, true);
    perform set_config('request.jwt.claims', json_build_object(
        'sub', other_uid::text, 'role', 'authenticated')::text, true);
    if exists (select 1 from public.enrollments)
       or exists (select 1 from public.subjects)
       or exists (select 1 from public.academic_periods) then
        raise exception 'FALLO: una identidad sin perfil consulta datos académicos';
    end if;
end;
$$;
rollback;
select 'Materias: RLS y permisos OK' as resultado;
