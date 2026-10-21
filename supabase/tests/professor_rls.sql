-- Solo lectura: requiere al menos una asignación del profesor de prueba.
begin read only;
set local request.jwt.claim.sub = 'PROFESSOR_UID_AQUI';
select set_config('request.jwt.claims', json_build_object(
    'sub', current_setting('request.jwt.claim.sub'), 'role', 'authenticated'
)::text, true);
set local role authenticated;

do $$
declare
    expected_uid uuid := current_setting('request.jwt.claim.sub')::uuid;
    missing_uid constant uuid := '00000000-0000-0000-0000-000000000000';
    assignment record;
    function_id oid := 'public.get_teaching_roster(uuid,integer,integer)'::regprocedure;
begin
    if current_user <> 'authenticated' or auth.uid() is distinct from expected_uid
       or expected_uid = missing_uid then
        raise exception 'FALLO: no se pudo simular la identidad del profesor';
    end if;
    if (select count(*) from public.profiles) <> 1 or not exists (
        select 1 from public.profiles
        where id = expected_uid and active = true and role = 'professor'
    ) then
        raise exception 'FALLO: se requiere un profesor activo y solo su perfil visible';
    end if;
    if not exists (
        select 1 from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relname = 'teaching_assignments' and c.relrowsecurity
    ) then
        raise exception 'FALLO: RLS no está activado en teaching_assignments';
    end if;
    if not has_table_privilege(current_user, 'public.teaching_assignments', 'SELECT')
       or has_table_privilege(current_user, 'public.teaching_assignments',
           'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege(current_user, 'public.teaching_assignments',
           'INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: permisos de asignaciones distintos de solo consulta';
    end if;
    if has_table_privilege('anon', 'public.teaching_assignments',
           'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege('anon', 'public.teaching_assignments',
           'SELECT, INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: anon conserva permisos de asignaciones';
    end if;
    if not has_function_privilege(current_user, function_id, 'EXECUTE')
       or has_function_privilege('anon', function_id, 'EXECUTE')
       or exists (
           select 1 from pg_catalog.pg_proc p,
               lateral pg_catalog.aclexplode(coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))) a
           where p.oid = function_id and a.grantee = 0 and a.privilege_type = 'EXECUTE'
       ) then
        raise exception 'FALLO: permisos de ejecución del listado incorrectos';
    end if;
    if not exists (
        select 1 from pg_catalog.pg_proc p
        where p.oid = function_id and p.prosecdef and p.provolatile = 's'
          and p.proconfig @> array['search_path=""']
    ) then
        raise exception 'FALLO: configuración segura del listado incorrecta';
    end if;
    if not exists (select 1 from public.teaching_assignments)
       or exists (select 1 from public.teaching_assignments where professor_id <> expected_uid) then
        raise exception 'FALLO: faltan asignaciones propias o son visibles asignaciones ajenas';
    end if;
    if exists (select 1 from public.enrollments)
       or exists (select 1 from public.enrollment_grades) then
        raise exception 'FALLO: el profesor puede leer directamente inscripciones o notas';
    end if;
    if exists (
        select 1 from public.subjects s
        where not exists (select 1 from public.teaching_assignments t where t.subject_id = s.id)
    ) or exists (
        select 1 from public.academic_periods p
        where not exists (select 1 from public.teaching_assignments t where t.period_id = p.id)
    ) then
        raise exception 'FALLO: son visibles catálogos sin asignación';
    end if;

    for assignment in select id from public.teaching_assignments loop
        if exists (
            select 1 from public.get_teaching_roster(assignment.id, 0, 20)
            where enrollment_id is null or student_name is null or length(btrim(student_name)) = 0
        ) then
            raise exception 'FALLO: el listado devuelve datos incompletos';
        end if;
    end loop;
    begin
        perform 1 from public.get_teaching_roster(missing_uid, 0, 20);
        raise exception 'FALLO: la función permite una asignación inexistente';
    exception when insufficient_privilege then null;
    end;
    perform set_config('request.jwt.claim.sub', missing_uid::text, true);
    perform set_config('request.jwt.claims', json_build_object(
        'sub', missing_uid::text, 'role', 'authenticated')::text, true);
    if exists (select 1 from public.teaching_assignments) then
        raise exception 'FALLO: una identidad sin perfil ve asignaciones';
    end if;
    begin
        perform 1 from public.get_teaching_roster(assignment.id, 0, 20);
        raise exception 'FALLO: la función permite una identidad sin perfil';
    exception when insufficient_privilege then null;
    end;
end;
$$;
rollback;
select 'Profesor: RLS y permisos OK' as resultado;
