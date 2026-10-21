-- Datos FICTICIOS para una cuenta de prueba. Ejecutar como administrador
-- desde SQL Editor, después de 20261021010000_create_academics.sql.
-- Sustituir el marcador solo en la consulta, no en el archivo de GitHub.
begin;
set local seminario.demo_student_uid = 'PEGA_AQUI_EL_UID';

do $$
declare
    student_uid uuid := current_setting('seminario.demo_student_uid')::uuid;
    demo_period uuid;
    philosophy_id uuid;
    history_id uuid;
begin
    if not exists (
        select 1 from public.profiles
        where id = student_uid and role = 'student' and active = true
    ) then
        raise exception 'Se requiere el UID de un alumno de prueba activo con perfil';
    end if;

    insert into public.academic_periods (name, starts_on, ends_on)
    values ('DEMO 2026 — semestre de prueba', '2026-08-01', '2026-12-18')
    on conflict (name) do nothing;

    select id into demo_period from public.academic_periods
    where name = 'DEMO 2026 — semestre de prueba'
      and starts_on = '2026-08-01' and ends_on = '2026-12-18';
    if demo_period is null then
        raise exception 'Ya existe el periodo DEMO con fechas distintas; no se modificó';
    end if;

    insert into public.subjects (code, name) values
        ('DEMO-FIL-101', 'Filosofía — ejemplo'),
        ('DEMO-HIS-101', 'Historia — ejemplo')
    on conflict (code) do nothing;

    select id into philosophy_id from public.subjects
    where code = 'DEMO-FIL-101' and name = 'Filosofía — ejemplo';
    select id into history_id from public.subjects
    where code = 'DEMO-HIS-101' and name = 'Historia — ejemplo';
    if philosophy_id is null or history_id is null then
        raise exception 'Ya existe un código DEMO con otro nombre; no se modificó';
    end if;

    insert into public.enrollments (student_id, subject_id, period_id) values
        (student_uid, philosophy_id, demo_period),
        (student_uid, history_id, demo_period)
    on conflict (student_id, subject_id, period_id) do nothing;
end;
$$;
commit;

select 'Datos de ejemplo listos: dos inscripciones DEMO para la cuenta elegida' as resultado;
