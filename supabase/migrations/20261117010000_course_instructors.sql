-- Nombres de docentes por clase y periodo, visibles solo a usuarios autorizados.
-- Repetible. No cambia asignaciones, perfiles, notas ni documentos.
begin;
do $$
begin
 if to_regprocedure('public.portal_learning_read(text,uuid,integer,integer)') is null
  or to_regprocedure('public.portal_course_board_read(uuid)') is null then
  raise exception 'Faltan las actualizaciones existentes de aula y clases. No se instaló este cambio.';
 end if;
end;$$;

create or replace function public._course_instructor_names(p_course uuid)
returns jsonb language sql stable security definer set search_path='' as $$
 select coalesce(jsonb_agg(jsonb_build_object('name',p.full_name)
  order by lower(p.full_name),p.id),'[]'::jsonb)
 from public.course_offerings c
 join public.teaching_assignments t on t.subject_id=c.subject_id and t.period_id=c.period_id
 join public.profiles p on p.id=t.professor_id
 where c.id=p_course and t.active and p.active and p.role in ('professor','control_escolar')
$$;
revoke all on function public._course_instructor_names(uuid) from public,anon,authenticated;

-- Conserva el lector instalado, incluido el filtro del inicio personal de Control Escolar.
do $$
begin
 if to_regprocedure('public._learning_read_before_instructors(text,uuid,integer,integer)') is null then
  alter function public.portal_learning_read(text,uuid,integer,integer)
   rename to _learning_read_before_instructors;
 end if;
end;$$;
revoke all on function public._learning_read_before_instructors(text,uuid,integer,integer)
 from public,anon,authenticated;

create or replace function public.portal_learning_read(
 p_resource text,p_course uuid default null,p_offset integer default 0,p_limit integer default 30
)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb;
begin
 -- El lector anterior valida identidad, rol, clase, inscripción/asignación y paginación.
 result:=public._learning_read_before_instructors(p_resource,p_course,p_offset,p_limit);
 if p_resource='course' then
  result:=result||jsonb_build_object('instructors',public._course_instructor_names(p_course));
 end if;
 return result;
end;$$;
revoke all on function public.portal_learning_read(text,uuid,integer,integer)
 from public,anon,authenticated;
grant execute on function public.portal_learning_read(text,uuid,integer,integer) to authenticated;

create or replace function public.portal_course_board_read(p_period uuid default null)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare chosen uuid;periods jsonb;subjects jsonb;classes jsonb;
begin
 perform public._require_control_catalog_access();
 select coalesce(jsonb_agg(to_jsonb(p) order by p.starts_on desc,p.id),'[]') into periods
  from (select id,name,starts_on,ends_on from public.academic_periods) p;
 if p_period is null then
  select id into chosen from public.academic_periods
  order by case when (now() at time zone 'America/Matamoros')::date between starts_on and ends_on
   then 0 else 1 end,starts_on desc,id limit 1;
 else
  select id into chosen from public.academic_periods where id=p_period;
  if not found then raise exception using errcode='22023',message='El periodo ya no está disponible';end if;
 end if;
 select coalesce(jsonb_agg(to_jsonb(s) order by s.name,s.id),'[]') into subjects
  from (select id,code,name from public.subjects) s;
 select coalesce(jsonb_agg(to_jsonb(x) order by x.name,x.id),'[]') into classes from (
  select c.id,c.subject_id,c.period_id,c.active,s.name,s.code,p.name period_name,
   g.group_code,coalesce(g.revision,0) revision,coalesce(n.instructors,'[]'::jsonb) instructors
  from public.course_offerings c join public.subjects s on s.id=c.subject_id
  join public.academic_periods p on p.id=c.period_id
  left join public.course_formation_groups g on g.course_id=c.id
  -- Una agregación para todo el periodo; evita consultas HTTP por cada tarjeta.
  left join (
   select t.subject_id,t.period_id,jsonb_agg(jsonb_build_object('name',teacher.full_name)
    order by lower(teacher.full_name),teacher.id) instructors
   from public.teaching_assignments t join public.profiles teacher on teacher.id=t.professor_id
   where t.period_id=chosen and t.active and teacher.active and teacher.role in ('professor','control_escolar')
   group by t.subject_id,t.period_id
  ) n on n.subject_id=c.subject_id and n.period_id=c.period_id
  where c.period_id=chosen
 ) x;
 return jsonb_build_object('periods',periods,'period_id',chosen,'subjects',subjects,'classes',classes);
end;$$;
revoke all on function public.portal_course_board_read(uuid) from public,anon,authenticated;
grant execute on function public.portal_course_board_read(uuid) to authenticated;
notify pgrst,'reload schema';
commit;
