begin read only;

-- Sustituye este valor por el UID de la cuenta de prueba, una sola vez.
set local request.jwt.claim.sub = 'PEGA_AQUI_EL_UID';

select set_config(
    'request.jwt.claims',
    json_build_object(
        'sub', current_setting('request.jwt.claim.sub'),
        'role', 'authenticated'
    )::text,
    true
);

-- Ejecutar las comprobaciones con los permisos reales del navegador.
set local role authenticated;

do $$
declare
    expected_uid uuid := current_setting('request.jwt.claim.sub')::uuid;
    other_uid constant uuid := '00000000-0000-0000-0000-000000000000';
begin
    if current_user <> 'authenticated'
       or auth.uid() is distinct from expected_uid then
        raise exception 'FALLO: no se pudo simular la identidad de prueba';
    end if;

    if expected_uid = other_uid then
        raise exception 'FALLO: el UID de prueba debe ser distinto del UUID cero';
    end if;

    if not has_table_privilege(current_user, 'public.profiles', 'SELECT') then
        raise exception 'FALLO: falta permiso SELECT para authenticated';
    end if;

    if (select count(*) from public.profiles) <> 1
       or exists (
           select 1 from public.profiles
           where id is distinct from expected_uid or active is not true
       ) then
        raise exception 'FALLO: debe ser visible exactamente el perfil propio activo';
    end if;

    if has_table_privilege(current_user, 'public.profiles', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege(current_user, 'public.profiles', 'INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: authenticated conserva permisos distintos de SELECT';
    end if;

    if has_table_privilege('anon', 'public.profiles', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
       or has_any_column_privilege('anon', 'public.profiles', 'SELECT, INSERT, UPDATE, REFERENCES') then
        raise exception 'FALLO: anon conserva permisos sobre profiles';
    end if;

    -- Simular otra identidad sin crear otra cuenta ni modificar registros.
    perform set_config('request.jwt.claim.sub', other_uid::text, true);
    perform set_config(
        'request.jwt.claims',
        json_build_object('sub', other_uid::text, 'role', 'authenticated')::text,
        true
    );

    if exists (select 1 from public.profiles) then
        raise exception 'FALLO: una identidad distinta puede leer perfiles ajenos';
    end if;
end;
$$;

-- Restaurar el rol y la identidad originales de esta conexión.
rollback;

select 'RLS y permisos: OK' as resultado;
