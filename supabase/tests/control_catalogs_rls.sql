-- Solo lectura; requiere una cuenta activa de Control Escolar.
begin read only;
set local request.jwt.claim.sub = 'CONTROL_UID_AQUI';
select set_config('request.jwt.claims', json_build_object(
    'sub', current_setting('request.jwt.claim.sub'), 'role', 'authenticated'
)::text, true);
set local role authenticated;
do $$
declare
    actor uuid := current_setting('request.jwt.claim.sub')::uuid;
    missing_actor constant uuid := '00000000-0000-0000-0000-000000000000';
    table_name text;
    function_id oid;
begin
    if current_user <> 'authenticated' or auth.uid() is distinct from actor
       or actor = missing_actor then
        raise exception 'FALLO: no se pudo simular Control Escolar';
    end if;
    if (select count(*) from public.profiles) <> 1 or not exists (
        select 1 from public.profiles
        where id = actor and role = 'control_escolar' and active = true
    ) then
        raise exception 'FALLO: se requiere Control Escolar activo y solo su perfil visible';
    end if;
    foreach table_name in array array['subjects', 'academic_periods'] loop
        if not has_table_privilege(current_user, 'public.' || table_name, 'SELECT')
           or has_table_privilege(current_user, 'public.' || table_name,
               'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
           or has_any_column_privilege(current_user, 'public.' || table_name,
               'INSERT, UPDATE, REFERENCES') then
            raise exception 'FALLO: permisos de catálogo incorrectos en %', table_name;
        end if;
        if has_table_privilege('anon', 'public.' || table_name,
               'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
           or has_any_column_privilege('anon', 'public.' || table_name,
               'SELECT, INSERT, UPDATE, REFERENCES') then
            raise exception 'FALLO: anon conserva permisos de catálogo';
        end if;
        if not exists (
            select 1 from pg_catalog.pg_class c
            join pg_catalog.pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relname = table_name and c.relrowsecurity
        ) then
            raise exception 'FALLO: RLS no está activado en %', table_name;
        end if;
    end loop;
    if exists (select 1 from public.enrollments)
       or exists (select 1 from public.enrollment_grades)
       or exists (select 1 from public.teaching_assignments) then
        raise exception 'FALLO: se amplió lectura académica fuera de los catálogos';
    end if;
    foreach table_name in array array['catalog_events', 'enrollment_grade_drafts', 'enrollment_grade_events'] loop
        if not exists (
            select 1 from pg_catalog.pg_class c
            join pg_catalog.pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relname = table_name and c.relrowsecurity
        ) then
            raise exception 'FALLO: RLS no está activado en %', table_name;
        end if;
        if has_table_privilege(current_user, 'public.' || table_name,
            'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
           or has_any_column_privilege(current_user, 'public.' || table_name,
               'SELECT, INSERT, UPDATE, REFERENCES')
           or has_table_privilege('anon', 'public.' || table_name,
               'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
           or has_any_column_privilege('anon', 'public.' || table_name,
               'SELECT, INSERT, UPDATE, REFERENCES') then
            raise exception 'FALLO: acceso directo a tabla privada %', table_name;
        end if;
    end loop;
    foreach function_id in array array[
        'public.create_subject(text,text)'::regprocedure::oid,
        'public.create_academic_period(text,date,date)'::regprocedure::oid
    ] loop
        if not has_function_privilege(current_user, function_id, 'EXECUTE')
           or has_function_privilege('anon', function_id, 'EXECUTE')
           or exists (
               select 1 from pg_catalog.pg_proc p,
                   lateral pg_catalog.aclexplode(coalesce(p.proacl, pg_catalog.acldefault('f',p.proowner))) a
               where p.oid = function_id and a.grantee = 0 and a.privilege_type = 'EXECUTE'
           ) then
            raise exception 'FALLO: permisos de ejecución de catálogos incorrectos';
        end if;
        if not exists (
            select 1 from pg_catalog.pg_proc p where p.oid = function_id
              and p.prosecdef and p.provolatile = 'v'
              and p.proconfig @> array['search_path=""']
        ) then
            raise exception 'FALLO: configuración segura del RPC incorrecta';
        end if;
    end loop;
    if has_function_privilege(current_user,
       'public._require_control_catalog_access()'::regprocedure,'EXECUTE')
       or has_function_privilege(current_user,
       'public._catalog_text_has_content(text)'::regprocedure,'EXECUTE')
       or has_function_privilege('anon',
       'public._catalog_text_has_content(text)'::regprocedure,'EXECUTE') then
        raise exception 'FALLO: el helper privado conserva ejecución del navegador';
    end if;
    perform set_config('request.jwt.claim.sub', missing_actor::text, true);
    perform set_config('request.jwt.claims', json_build_object(
        'sub', missing_actor::text, 'role', 'authenticated')::text, true);
    if exists (select 1 from public.subjects) or exists (select 1 from public.academic_periods) then
        raise exception 'FALLO: una identidad sin perfil consulta catálogos';
    end if;
end;
$$;
rollback;
select 'Control Escolar: RLS y permisos OK' as resultado;
