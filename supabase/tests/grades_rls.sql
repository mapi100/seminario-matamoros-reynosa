-- Prueba de solo lectura. Requiere al menos una calificación publicada propia.
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
    if not exists (
        select 1 from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relname = 'enrollment_grades'
          and c.relrowsecurity = true
    ) then
        raise exception 'FALLO: RLS no está activado en enrollment_grades';
    end if;
    if not has_table_privilege(current_user, 'public.enrollment_grades', 'SELECT') then
        raise exception 'FALLO: falta SELECT sobre enrollment_grades';
    end if;
    if has_table_privilege(current_user, 'public.enrollment_grades',
        'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege(current_user, 'public.enrollment_grades',
        'INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: authenticated conserva escritura sobre enrollment_grades';
    end if;
    if has_table_privilege('anon', 'public.enrollment_grades',
        'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege('anon', 'public.enrollment_grades',
        'SELECT, INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: anon conserva permisos sobre enrollment_grades';
    end if;
    if not exists (select 1 from public.enrollment_grades) then
        raise exception 'FALLO: el alumno no tiene calificaciones publicadas visibles';
    end if;
    if exists (
        select 1 from public.enrollment_grades g
        where g.published is not true
           or not exists (
               select 1 from public.enrollments e
               where e.id = g.enrollment_id and e.student_id = expected_uid
           )
    ) then
        raise exception 'FALLO: son visibles calificaciones ajenas o sin publicar';
    end if;

    perform set_config('request.jwt.claim.sub', other_uid::text, true);
    perform set_config('request.jwt.claims', json_build_object(
        'sub', other_uid::text, 'role', 'authenticated')::text, true);
    if exists (select 1 from public.enrollment_grades) then
        raise exception 'FALLO: una identidad sin perfil consulta calificaciones';
    end if;
end;
$$;
rollback;
select 'Calificaciones: RLS y permisos OK' as resultado;
