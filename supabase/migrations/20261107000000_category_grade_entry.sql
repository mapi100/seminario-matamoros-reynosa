-- Captura por categorías sin crear actividades. Repetible; instalar no altera notas.
begin;
-- Copiar los cuerpos previos sin renombrar sus funciones públicas: conserva
-- sus OID y las referencias de las otras pantallas a los puntos de entrada.
do $$
declare definition text;
begin
 if to_regprocedure('public._grading_validate_before_categories(uuid,jsonb)') is null then
  definition:=pg_get_functiondef('public._grading_validate(uuid,jsonb)'::regprocedure);
  execute replace(definition,'FUNCTION public._grading_validate(', 'FUNCTION public._grading_validate_before_categories(');
  definition:=pg_get_functiondef('public._grading_calculate(uuid,uuid,boolean)'::regprocedure);
  execute replace(definition,'FUNCTION public._grading_calculate(', 'FUNCTION public._grading_calculate_before_categories(');
  definition:=pg_get_functiondef('public.portal_gradebook_read(uuid,text,integer,integer)'::regprocedure);
  execute replace(definition,'FUNCTION public.portal_gradebook_read(', 'FUNCTION public._gradebook_read_before_categories(');
  definition:=pg_get_functiondef('public.portal_gradebook_write(uuid,text,jsonb)'::regprocedure);
  execute replace(definition,'FUNCTION public.portal_gradebook_write(', 'FUNCTION public._gradebook_write_before_categories(');
 end if;
end;$$;
create table if not exists public.learning_category_grades (
 course_id uuid not null references public.course_offerings(id) on delete cascade,
 enrollment_id uuid not null references public.enrollments(id) on delete cascade,
 category text not null check(category in ('tasks','exams','projects','participation')),
 score numeric(5,2) check(score between 0 and 100),published_score numeric(5,2) check(published_score between 0 and 100),
 revision integer not null default 1,updated_by uuid not null references public.profiles(id),updated_at timestamptz not null default now(),
 primary key(course_id,enrollment_id,category)
);
alter table public.learning_category_grades enable row level security;
revoke all on public.learning_category_grades from public,anon,authenticated;

create or replace function public._grading_validate(p_course uuid,p_schema jsonb)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare c jsonb; total numeric:=0; weight numeric;
begin
 if p_schema->>'entry_mode' is distinct from 'categories' then
  return public._grading_validate_before_categories(p_course,p_schema);
 end if;
 if jsonb_typeof(p_schema->'categories') is distinct from 'array' or jsonb_array_length(p_schema->'categories')<>4
  or p_schema->'items' is distinct from '[]'::jsonb then return '["Configura las cuatro categorías, sin actividades."]';end if;
 if (select count(distinct x->>'code') from jsonb_array_elements(p_schema->'categories') x where x->>'code' in ('tasks','exams','projects','participation'))<>4 then
  return '["Se requieren Tareas, Exámenes, Proyectos y Participación, sin duplicados."]';end if;
 for c in select value from jsonb_array_elements(p_schema->'categories') loop
  if jsonb_typeof(c->'weight') is distinct from 'number' then return '["Introduce porcentajes numéricos."]';end if;
  weight:=(c->>'weight')::numeric;
  if weight not between 0 and 100 or weight<>round(weight,2) then return '["Los porcentajes deben estar entre 0 y 100, con hasta dos decimales."]';end if;
  total:=total+weight;
 end loop;
 if total<>100 then return '["Los porcentajes deben sumar exactamente 100 %."]';end if;
 return '[]';
end;$$;

create or replace function public._grading_calculate(p_course uuid,p_enrollment uuid,p_drafts boolean default false)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare scheme jsonb;cat jsonb;g public.learning_category_grades%rowtype;categories jsonb:='[]';reasons jsonb;
 result jsonb;marks jsonb;weight numeric;value numeric;earned numeric:=0;covered numeric:=0;pending integer:=0;unpublished integer:=0;
begin
 select published into scheme from public.learning_grading_schemes where course_id=p_course;
 if scheme->>'entry_mode' is distinct from 'categories' then return public._grading_calculate_before_categories(p_course,p_enrollment,p_drafts);end if;
 reasons:=public._grading_validate(p_course,scheme);
 for cat in select j.value from jsonb_array_elements(scheme->'categories') j loop
  weight:=(cat->>'weight')::numeric;
  select * into g from public.learning_category_grades where course_id=p_course and enrollment_id=p_enrollment and category=cat->>'code';
  value:=case when p_drafts then g.score else g.published_score end;
  if weight>0 then
   if value is null then pending:=pending+1;else covered:=covered+weight;earned:=earned+value*weight/100;end if;
   if g.score is distinct from g.published_score then unpublished:=unpublished+1;end if;
  end if;
  categories:=categories||jsonb_build_array(jsonb_build_object('code',cat->>'code','weight',weight,'average',case when weight>0 then value end,'coverage',case when value is not null and weight>0 then weight else 0 end));
 end loop;
 if pending>0 then reasons:=reasons||jsonb_build_array(pending||' categorías con peso sin calificación.');end if;
 if unpublished>0 then reasons:=reasons||jsonb_build_array('Hay notas de categorías pendientes de publicación.');end if;
 result:=jsonb_build_object('configured',true,'entry_mode','categories','average',case when covered=100 then round(earned,2) end,
  'coverage',covered,'categories',categories,'items','[]'::jsonb,'pending',pending,'unpublished',unpublished,
  'ready',jsonb_array_length(reasons)=0 and covered=100,'reasons',reasons);
 select coalesce(jsonb_agg(to_jsonb(x) order by category),'[]') into marks from public.learning_category_grades x where course_id=p_course and enrollment_id=p_enrollment;
 return result||jsonb_build_object('token',md5(result::text||scheme::text||marks::text||coalesce((select to_jsonb(f)::text from public.enrollment_grades f where enrollment_id=p_enrollment),'')));
end;$$;

create or replace function public.portal_gradebook_read(p_course uuid,p_resource text default 'book',p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb;rows jsonb;mode text;
begin
 result:=public._gradebook_read_before_categories(p_course,p_resource,p_offset,p_limit);
 select published->>'entry_mode' into mode from public.learning_grading_schemes where course_id=p_course;
 if p_resource='book' then
  select coalesce(jsonb_agg(x||jsonb_build_object('category_grades',(select coalesce(jsonb_agg(jsonb_build_object('category',g.category,'score',g.score,'published_score',g.published_score,'revision',g.revision) order by g.category),'[]')
   from public.learning_category_grades g where g.course_id=p_course and g.enrollment_id=(x->>'enrollment_id')::uuid))),'[]') into rows from jsonb_array_elements(result->'students') x;
  result:=jsonb_set(result,'{students}',rows);
 end if;
 return result||jsonb_build_object('entry_mode',coalesce(mode,'activities'));
end;$$;

create or replace function public.portal_gradebook_write(p_course uuid,p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare actor uuid;scheme public.learning_grading_schemes%rowtype;errors jsonb;r jsonb;cat jsonb;marks jsonb;old_marks jsonb;
 eid uuid;code text;score numeric;weight numeric;publishing boolean;reason text;finals jsonb:='[]';result jsonb;calc jsonb;override_value numeric;
begin
 perform pg_catalog.pg_advisory_xact_lock(72643219);
 perform public._learning_require_course(p_course,true);actor:=auth.uid();
 if p_action not in ('category_scheme_publish','category_marks_save') or p_action is null then
  return public._gradebook_write_before_categories(p_course,p_action,p_data);
 end if;
 if jsonb_typeof(p_data) is distinct from 'object' then raise exception using errcode='22023',message='Datos inválidos';end if;
 reason:=btrim(coalesce(p_data->>'reason',''));
 if char_length(reason)>1000 then raise exception using errcode='22023',message='El motivo supera 1000 caracteres';end if;
 select * into scheme from public.learning_grading_schemes where course_id=p_course for update;
 if p_action='category_scheme_publish' then
  if p_data->'confirmed' is distinct from 'true'::jsonb then raise exception using errcode='22023',message='Confirma los porcentajes antes de guardarlos';end if;
  if (p_data->>'revision')::integer is distinct from coalesce(scheme.revision,0) then raise exception using errcode='PT409',message='Los porcentajes cambiaron. Actualiza y revisa de nuevo.';end if;
  if p_data->'schema'->>'entry_mode' is distinct from 'categories' then raise exception using errcode='22023',message='Modo de captura inválido';end if;
  errors:=public._grading_validate(p_course,p_data->'schema');
  if jsonb_array_length(errors)>0 then raise exception using errcode='22023',message=errors->>0;end if;
  if scheme.published is not null and scheme.published is distinct from p_data->'schema' and char_length(reason)<10 then
   raise exception using errcode='22023',message='Explica el cambio de evaluación con al menos 10 caracteres';end if;
  insert into public.learning_grading_schemes(course_id,draft,published,revision,updated_by)values(p_course,p_data->'schema',p_data->'schema',1,actor)
   on conflict(course_id)do update set draft=excluded.draft,published=excluded.published,revision=public.learning_grading_schemes.revision+1,updated_by=actor,updated_at=now();
  insert into public.learning_audit(actor_id,course_id,action,entity_id,details)values(actor,p_course,p_action,p_course,jsonb_build_object('before',scheme.published,'after',p_data->'schema','reason',reason));
  return jsonb_build_object('saved',true,'id',p_course);
 end if;
 if scheme.published->>'entry_mode' is distinct from 'categories' then raise exception using errcode='22023',message='Primero configura una nota por categoría';end if;
 if jsonb_typeof(p_data->'publish') is distinct from 'boolean' or jsonb_typeof(p_data->'students') is distinct from 'array'
  or jsonb_array_length(p_data->'students') not between 1 and 100 then raise exception using errcode='22023',message='Selecciona entre 1 y 100 alumnos';end if;
 publishing:=(p_data->>'publish')::boolean;
 if publishing and p_data->'confirmed' is distinct from 'true'::jsonb then raise exception using errcode='22023',message='Revisa y confirma las finales';end if;
 if (select count(distinct x->>'id') from jsonb_array_elements(p_data->'students') x)<>jsonb_array_length(p_data->'students') then raise exception using errcode='22023',message='Hay alumnos duplicados';end if;
 for r in select value from jsonb_array_elements(p_data->'students') loop
  eid:=(r->>'id')::uuid;
  perform e.id from public.enrollments e join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id join public.profiles p on p.id=e.student_id
   where e.id=eid and c.id=p_course and e.active and p.active and p.role='student' for update of e;
  if not found then raise exception using errcode='42501',message='Alumno fuera de esta clase activa';end if;
  calc:=public._grading_calculate(p_course,eid);
  if r->>'token' is null or r->>'token' is distinct from calc->>'token' then raise exception using errcode='PT409',message='Las notas o los porcentajes cambiaron. Actualiza y revisa antes de guardar.';end if;
  marks:=r->'marks';
  if jsonb_typeof(marks) is distinct from 'object' or marks-array['tasks','exams','projects','participation']<>'{}'::jsonb then raise exception using errcode='22023',message='Categorías inválidas';end if;
  if r ? 'override' and r->'override'<>'null'::jsonb then
   if not publishing or jsonb_typeof(r->'override')<>'number' then raise exception using errcode='22023',message='El ajuste final se confirma al publicar';end if;
   override_value:=(r->>'override')::numeric;
   if override_value not between 0 and 100 or override_value<>round(override_value,2) then raise exception using errcode='22023',message='Ajuste fuera de escala';end if;
  end if;
  for cat in select value from jsonb_array_elements(scheme.published->'categories') loop
   code:=cat->>'code';weight:=(cat->>'weight')::numeric;
   if marks ? code and marks->code<>'null'::jsonb then
    if jsonb_typeof(marks->code)<>'number' then raise exception using errcode='22023',message='Usa números de 0 a 10';end if;
    score:=(marks->>code)::numeric;
    if score not between 0 and 100 or score<>round(score,2) or weight=0 then raise exception using errcode='22023',message='Revisa la escala y las categorías que no cuentan';end if;
   elsif publishing and weight>0 then raise exception using errcode='22023',message='Completa todas las categorías con peso antes de publicar la final';end if;
  end loop;
 end loop;
 -- Todo el lote se validó antes de escribir. Una publicación fallida revierte también las categorías.
 for r in select value from jsonb_array_elements(p_data->'students') loop
  eid:=(r->>'id')::uuid;marks:=r->'marks';
  select coalesce(jsonb_agg(to_jsonb(g)),'[]') into old_marks from public.learning_category_grades g where course_id=p_course and enrollment_id=eid;
  for cat in select value from jsonb_array_elements(scheme.published->'categories') loop
   code:=cat->>'code';weight:=(cat->>'weight')::numeric;
   if weight=0 then continue;end if;
   score:=(marks->>code)::numeric;
   insert into public.learning_category_grades(course_id,enrollment_id,category,score,published_score,updated_by)
    values(p_course,eid,code,score,case when publishing then score end,actor)
    on conflict(course_id,enrollment_id,category)do update set score=excluded.score,
     published_score=case when publishing then excluded.score else public.learning_category_grades.published_score end,
     revision=public.learning_category_grades.revision+1,updated_by=actor,updated_at=now();
  end loop;
  insert into public.learning_audit(actor_id,course_id,action,entity_id,details)values(actor,p_course,p_action,eid,jsonb_build_object('before',old_marks,'marks',marks,'publish',publishing,'reason',reason));
  if publishing then
   calc:=public._grading_calculate(p_course,eid);
   finals:=finals||jsonb_build_array(jsonb_build_object('id',eid,'token',calc->>'token','override',r->'override'));
  end if;
 end loop;
 if publishing then result:=public._gradebook_write_before_categories(p_course,'final_publish',jsonb_build_object('confirmed',true,'reason',reason,'students',finals));end if;
 return jsonb_build_object('saved',true,'id',p_course);
exception when invalid_text_representation or numeric_value_out_of_range then raise exception using errcode='22023',message='Revisa alumnos, porcentajes y notas';
end;$$;
revoke all on function public._grading_validate_before_categories(uuid,jsonb),public._grading_calculate_before_categories(uuid,uuid,boolean),
 public._gradebook_read_before_categories(uuid,text,integer,integer),public._gradebook_write_before_categories(uuid,text,jsonb),
 public._grading_validate(uuid,jsonb),public._grading_calculate(uuid,uuid,boolean),
 public.portal_gradebook_read(uuid,text,integer,integer),public.portal_gradebook_write(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.portal_gradebook_read(uuid,text,integer,integer),public.portal_gradebook_write(uuid,text,jsonb) to authenticated;
notify pgrst,'reload schema';
commit;
