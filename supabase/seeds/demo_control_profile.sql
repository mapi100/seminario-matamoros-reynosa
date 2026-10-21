-- Crear antes una cuenta Auth nueva y distinta de alumno/profesor.
-- Sustituye el marcador solo en SQL Editor; consérvalo en GitHub.
begin;
set local seminario.demo_control_uid = 'CONTROL_UID_AQUI';
do $$
declare
    control_uid uuid := current_setting('seminario.demo_control_uid')::uuid;
begin
    if not exists (select 1 from auth.users where id = control_uid) then
        raise exception 'Primero crea la cuenta nueva de Control Escolar en Authentication';
    end if;
    insert into public.profiles(id, full_name, role, active)
    values (control_uid, 'Control Escolar de prueba', 'control_escolar', true)
    on conflict (id) do nothing;
    if not exists (
        select 1 from public.profiles
        where id = control_uid and role = 'control_escolar' and active = true
    ) then
        raise exception 'La cuenta elegida ya tiene otro rol o está inactiva; no se modificó';
    end if;
end;
$$;
commit;
select 'Perfil de Control Escolar de prueba listo' as resultado;
