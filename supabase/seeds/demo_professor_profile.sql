-- Después de crear una cuenta Auth NUEVA y distinta de la cuenta de alumno.
-- Sustituir el marcador solo en SQL Editor, no en el archivo de GitHub.
begin;
set local seminario.demo_professor_uid = 'PROFESSOR_UID_AQUI';

do $$
declare
    professor_uid uuid := current_setting('seminario.demo_professor_uid')::uuid;
begin
    if not exists (select 1 from auth.users where id = professor_uid) then
        raise exception 'Primero crea la cuenta nueva del profesor en Authentication';
    end if;
    insert into public.profiles (id, full_name, role, active)
    values (professor_uid, 'Profesor de prueba', 'professor', true)
    on conflict (id) do nothing;

    if not exists (
        select 1 from public.profiles
        where id = professor_uid and role = 'professor' and active = true
    ) then
        raise exception 'La cuenta elegida ya tiene otro rol o está inactiva; no se modificó';
    end if;
end;
$$;
commit;
select 'Perfil de profesor de prueba listo' as resultado;
