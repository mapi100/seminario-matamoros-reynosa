-- Calificaciones FICTICIAS; ejecutar como administrador desde SQL Editor.
-- Requiere las dos inscripciones creadas por demo_enrollments.sql.
-- Sustituir el marcador solo en SQL Editor; conservarlo en GitHub.
begin;
set local seminario.demo_student_uid = 'PEGA_AQUI_EL_UID';

do $$
declare
    student_uid uuid := current_setting('seminario.demo_student_uid')::uuid;
    philosophy_enrollment uuid;
    history_enrollment uuid;
begin
    if not exists (
        select 1 from public.profiles
        where id = student_uid and role = 'student' and active = true
    ) then
        raise exception 'Se requiere el UID de un alumno de prueba activo con perfil';
    end if;

    select e.id into philosophy_enrollment
    from public.enrollments e
    join public.subjects s on s.id = e.subject_id
    join public.academic_periods p on p.id = e.period_id
    where e.student_id = student_uid
      and s.code = 'DEMO-FIL-101' and s.name = 'Filosofía — ejemplo'
      and p.name = 'DEMO 2026 — semestre de prueba'
      and p.starts_on = '2026-08-01' and p.ends_on = '2026-12-18';

    select e.id into history_enrollment
    from public.enrollments e
    join public.subjects s on s.id = e.subject_id
    join public.academic_periods p on p.id = e.period_id
    where e.student_id = student_uid
      and s.code = 'DEMO-HIS-101' and s.name = 'Historia — ejemplo'
      and p.name = 'DEMO 2026 — semestre de prueba'
      and p.starts_on = '2026-08-01' and p.ends_on = '2026-12-18';

    if philosophy_enrollment is null or history_enrollment is null then
        raise exception 'Faltan las dos inscripciones DEMO; ejecuta primero demo_enrollments.sql para este alumno';
    end if;

    insert into public.enrollment_grades (enrollment_id, score, published) values
        (philosophy_enrollment, 85.50, true),
        (history_enrollment, 72.00, false)
    on conflict (enrollment_id) do nothing;

    if not exists (
        select 1 from public.enrollment_grades
        where enrollment_id = philosophy_enrollment and score = 85.50 and published = true
    ) or not exists (
        select 1 from public.enrollment_grades
        where enrollment_id = history_enrollment and score = 72.00 and published = false
    ) then
        raise exception 'Ya existe una calificación DEMO con otra nota o publicación; no se sobrescribió';
    end if;
end;
$$;
commit;

select 'Calificaciones DEMO listas: Filosofía publicada e Historia sin publicar' as resultado;
