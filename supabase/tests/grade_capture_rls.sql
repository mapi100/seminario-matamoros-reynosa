-- Solo lectura: no guarda ni publica notas. Ejecutar como administrador.
begin read only;
set local request.jwt.claim.sub = 'PROFESSOR_UID_AQUI';
select set_config('request.jwt.claims', json_build_object(
    'sub', current_setting('request.jwt.claim.sub'), 'role', 'authenticated'
)::text, true);
set local role authenticated;

do $$
declare
    expected_uid uuid := current_setting('request.jwt.claim.sub')::uuid;
    table_name text;
    signature text;
    function_id oid;
    row_info record;
    grade_info record;
begin
    if current_user <> 'authenticated' or auth.uid() is distinct from expected_uid
       or not exists (select 1 from public.profiles where id = expected_uid and active and role = 'professor') then
        raise exception 'FALLO: se requiere un profesor de prueba activo';
    end if;
    foreach table_name in array array['enrollment_grade_drafts', 'enrollment_grade_events'] loop
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
            raise exception 'FALLO: acceso directo a borradores o auditoría en %', table_name;
        end if;
    end loop;
    if has_table_privilege(current_user, 'public.enrollment_grades',
        'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege(current_user, 'public.enrollment_grades', 'INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: escritura directa de calificaciones';
    end if;
    foreach signature in array array[
        'public.get_teaching_grade(uuid,uuid)',
        'public.save_teaching_grade(uuid,uuid,numeric,integer)',
        'public.publish_teaching_grade(uuid,uuid,integer)'
    ] loop
        function_id := signature::regprocedure;
        if not has_function_privilege(current_user, function_id, 'EXECUTE')
           or has_function_privilege('anon', function_id, 'EXECUTE')
           or exists (
               select 1 from pg_catalog.pg_proc p,
                   lateral pg_catalog.aclexplode(coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))) a
               where p.oid = function_id and a.grantee = 0 and a.privilege_type = 'EXECUTE'
           ) then
            raise exception 'FALLO: permisos de ejecución incorrectos para %', signature;
        end if;
        if not exists (
            select 1 from pg_catalog.pg_proc p
            where p.oid = function_id and p.prosecdef
              and p.proconfig @> array['search_path=""']
        ) then
            raise exception 'FALLO: configuración insegura para %', signature;
        end if;
    end loop;
    if has_function_privilege(current_user, 'public._lock_teaching_grade(uuid,uuid)', 'EXECUTE')
       or has_function_privilege('anon', 'public._lock_teaching_grade(uuid,uuid)', 'EXECUTE') then
        raise exception 'FALLO: el helper privado es ejecutable desde el navegador';
    end if;
    if not exists (select 1 from public.teaching_assignments) then
        raise exception 'FALLO: faltan asignaciones del profesor de prueba';
    end if;
    for row_info in
        select t.id as assignment_id, r.enrollment_id
        from public.teaching_assignments t
        cross join lateral public.get_teaching_roster(t.id, 0, 1) r
    loop
        select * into grade_info from public.get_teaching_grade(row_info.assignment_id, row_info.enrollment_id);
        if not found or grade_info.enrollment_id is distinct from row_info.enrollment_id
           or grade_info.revision < 0 or grade_info.has_unpublished_changes is null
           or (grade_info.published_score is not null and
               (grade_info.published_score < 0 or grade_info.published_score > 100))
           or (grade_info.draft_score is not null and
               (grade_info.draft_score < 0 or grade_info.draft_score > 100)) then
            raise exception 'FALLO: lectura de calificación inválida';
        end if;
    end loop;
    begin
        perform 1 from public.get_teaching_grade(
            '00000000-0000-0000-0000-000000000000',
            '00000000-0000-0000-0000-000000000000');
        raise exception 'FALLO: lectura de una calificación no autorizada';
    exception when insufficient_privilege then null;
    end;
end;
$$;
rollback;
select 'Captura: RLS y permisos OK' as resultado;
