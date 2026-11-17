-- Inicio de Control Escolar: avisos, tareas y calendario de su docencia personal.
-- El directorio y la administración de cualquier curso conservan sus permisos.
-- Ejecutar completo como postgres. Repetible; no cambia datos ni calificaciones.
begin;

do $$
begin
 if to_regprocedure('public._learning_read_before_weights(text,uuid,integer,integer)') is null
  or to_regprocedure('public._learning_require_actor()') is null then
  raise exception 'Faltan las actualizaciones existentes de aula y evaluación. No se instaló este cambio.';
 end if;
end;$$;

create or replace function public._learning_control_personal_dashboard(
 p_offset integer,p_limit integer
)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare
 person public.profiles%rowtype;
 personal_courses uuid[];
 courses jsonb;announcements jsonb;work jsonb;events jsonb;institutional jsonb;
begin
 person:=public._learning_require_actor();
 if person.role<>'control_escolar' then
  raise exception using errcode='42501',message='Consulta exclusiva de Control Escolar';
 end if;
 if p_offset is null or p_offset<0 or p_offset>100000
  or p_limit is null or p_limit<1 or p_limit>100 then
  raise exception using errcode='22023',message='Paginación inválida';
 end if;

 -- Todas las titularidades activas, sin depender de la página del directorio.
 select coalesce(array_agg(c.id),'{}'::uuid[]) into personal_courses
 from public.course_offerings c
 where c.active and exists(
  select 1 from public.teaching_assignments t
  where t.professor_id=person.id and t.active
   and t.subject_id=c.subject_id and t.period_id=c.period_id
 );

 -- Conserva la consulta paginada de cursos para entrar desde el directorio general.
 select coalesce(jsonb_agg(to_jsonb(r)),'[]') into courses from (
  select c.id,c.subject_id,c.period_id,s.code,s.name,
   a.name period_name,a.starts_on,a.ends_on,person.role role,null::numeric final_score
  from public.course_offerings c join public.subjects s on s.id=c.subject_id
  join public.academic_periods a on a.id=c.period_id
  where c.active
  order by a.starts_on desc,s.code,c.id offset p_offset limit p_limit+1
 ) r;

 -- Filtra ANTES de los límites: otras materias no desplazan las propias.
 select coalesce(jsonb_agg(to_jsonb(r)),'[]') into announcements from (
  select n.id,n.course_id,s.name course_name,n.title,n.body,n.pinned,n.published_at
  from public.learning_announcements n
  left join public.course_offerings c on c.id=n.course_id
  left join public.subjects s on s.id=c.subject_id
  where n.published and (n.course_id is null or n.course_id=any(personal_courses))
  order by n.pinned desc,n.published_at desc,n.id limit 50
 ) r;

 select coalesce(jsonb_agg(to_jsonb(r)),'[]') into work from (
  select t.id,t.course_id,s.name course_name,t.title,t.due_at,
   case when t.due_at<now() and not t.allow_late then 'closed'
    when t.due_at<now() then 'late' else 'pending' end status,
   null::timestamptz submitted_at
  from public.learning_assignments t
  join public.course_offerings c on c.id=t.course_id
  join public.subjects s on s.id=c.subject_id
  where t.published and t.course_id=any(personal_courses)
  order by t.due_at asc nulls last,t.id limit 50
 ) r;

 select coalesce(jsonb_agg(to_jsonb(r)),'[]') into events from (
  select v.id,v.course_id,s.name course_name,v.title,v.body,v.starts_at,v.ends_at
  from public.learning_events v
  left join public.course_offerings c on c.id=v.course_id
  left join public.subjects s on s.id=c.subject_id
  where (v.course_id is null or v.course_id=any(personal_courses))
   and v.starts_at>=now()-interval '30 days'
  order by v.starts_at,v.id limit 100
 ) r;

 -- Los avisos institucionales siguen disponibles para su administración.
 select coalesce(jsonb_agg(to_jsonb(r)),'[]') into institutional from (
  select n.id,n.title,n.body,n.pinned,n.published,n.revision,n.published_at
  from public.learning_announcements n where n.course_id is null
  order by n.pinned desc,n.created_at desc,n.id limit 200
 ) r;

 return jsonb_build_object(
  'courses',(select coalesce(jsonb_agg(v),'[]') from jsonb_array_elements(courses)
   with ordinality j(v,n) where n<=p_limit),
  'has_more_courses',jsonb_array_length(courses)>p_limit,
  'announcements',announcements,'institutional_announcements',institutional,
  'work',work,'events',events
 );
end;$$;
revoke all on function public._learning_control_personal_dashboard(integer,integer)
 from public,anon,authenticated;

create or replace function public.portal_learning_read(
 p_resource text,p_course uuid default null,p_offset integer default 0,p_limit integer default 30
)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb;
begin
 if p_resource='dashboard' and exists(
  select 1 from public.profiles p where p.id=auth.uid() and p.active and p.role='control_escolar'
 ) then
  return public._learning_control_personal_dashboard(p_offset,p_limit);
 end if;
 result:=public._learning_read_before_weights(p_resource,p_course,p_offset,p_limit);
 if p_resource='course' then
  result:=jsonb_set(result,'{assignments}',(
   select coalesce(jsonb_agg(x||jsonb_build_object(
    'grading_category',a.grading_category,'requires_submission',a.requires_submission
   )),'[]'::jsonb)
   from jsonb_array_elements(result->'assignments') x
   join public.learning_assignments a on a.id=(x->>'id')::uuid
  ));
 end if;
 return result;
end;$$;
revoke all on function public.portal_learning_read(text,uuid,integer,integer)
 from public,anon,authenticated;
grant execute on function public.portal_learning_read(text,uuid,integer,integer) to authenticated;
notify pgrst,'reload schema';
commit;
