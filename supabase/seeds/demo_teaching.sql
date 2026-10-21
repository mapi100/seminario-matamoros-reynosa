-- Asigna las dos materias DEMO existentes a un profesor de prueba activo.
-- Requiere demo_enrollments.sql y un perfil profesor previamente creado.
begin;
set local seminario.demo_student_uid = 'STUDENT_UID_AQUI';
set local seminario.demo_professor_uid = 'PROFESSOR_UID_AQUI';

do $$
declare
    student_uid uuid := current_setting('seminario.demo_student_uid')::uuid;
    professor_uid uuid := current_setting('seminario.demo_professor_uid')::uuid;
begin
    if student_uid = professor_uid then
        raise exception 'El alumno y el profesor deben ser cuentas distintas';
    end if;
    if not exists (
        select 1 from public.profiles
        where id = student_uid and role = 'student' and active = true
    ) then
        raise exception 'Se requiere el UID del alumno de prueba activo';
    end if;
    if not exists (
        select 1 from public.profiles
        where id = professor_uid and role = 'professor' and active = true
    ) then
        raise exception 'Se requiere el UID de un profesor activo con perfil';
    end if;
    if (
        select count(*)
        from public.enrollments e
        join public.subjects s on s.id = e.subject_id
        join public.academic_periods p on p.id = e.period_id
        where e.student_id = student_uid
          and ((s.code = 'DEMO-FIL-101' and s.name = 'Filosofía — ejemplo')
            or (s.code = 'DEMO-HIS-101' and s.name = 'Historia — ejemplo'))
          and p.name = 'DEMO 2026 — semestre de prueba'
          and p.starts_on = '2026-08-01' and p.ends_on = '2026-12-18'
    ) <> 2 then
        raise exception 'Faltan las dos inscripciones DEMO del alumno';
    end if;

    insert into public.teaching_assignments (professor_id, subject_id, period_id)
    select professor_uid, e.subject_id, e.period_id
    from public.enrollments e
    join public.subjects s on s.id = e.subject_id
    join public.academic_periods p on p.id = e.period_id
    where e.student_id = student_uid
      and ((s.code = 'DEMO-FIL-101' and s.name = 'Filosofía — ejemplo')
        or (s.code = 'DEMO-HIS-101' and s.name = 'Historia — ejemplo'))
      and p.name = 'DEMO 2026 — semestre de prueba'
      and p.starts_on = '2026-08-01' and p.ends_on = '2026-12-18'
    on conflict (professor_id, subject_id, period_id) do nothing;
end;
$$;
commit;
select 'Dos materias DEMO asignadas al profesor de prueba' as resultado;
