-- Control Escolar: captura final por rol y lotes de boletas por curso/periodo.
-- Repetible. No crea asignaciones docentes, no cambia notas al instalar.
begin;
do $$
begin
 if to_regprocedure('public._require_control_catalog_access()') is null
  or to_regprocedure('public._learning_require_course(uuid,boolean)') is null
  or to_regprocedure('public._grading_calculate(uuid,uuid,boolean)') is null
  or to_regprocedure('public._report_card_preview(uuid,uuid,jsonb)') is null
  or to_regclass('public.enrollment_grade_drafts') is null
  or to_regclass('public.learning_final_calculations') is null
  or to_regclass('public.course_formation_groups') is null then
  raise exception 'Faltan actualizaciones previas de aula, calificaciones o boletas. Instálalas antes de esta actualización; no se cambió ningún dato.';
 end if;
end;$$;

create or replace function public._school_finals_snapshot(p_course uuid)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb; students jsonb; c public.course_offerings%rowtype;
begin
 perform public._require_control_catalog_access();
 perform public._learning_require_course(p_course,true);
 select * into c from public.course_offerings where id=p_course;
 select coalesce(jsonb_agg(to_jsonb(x) order by x.name,x.enrollment_id),'[]') into students from (
  select e.id enrollment_id,p.id student_id,p.full_name name,k.student_number,
   case when g.published then g.score end published_score,coalesce(d.score,case when not g.published then g.score end) draft_score,coalesce(d.revision,0) revision,
   public._grading_calculate(p_course,e.id) calculation
  from public.enrollments e join public.profiles p on p.id=e.student_id
  left join public.kardex_students k on k.student_id=p.id
  left join public.enrollment_grades g on g.enrollment_id=e.id
  left join public.enrollment_grade_drafts d on d.enrollment_id=e.id
  where e.subject_id=c.subject_id and e.period_id=c.period_id and e.active and p.active and p.role='student'
 ) x;
 if jsonb_array_length(students)>500 then raise exception using errcode='22023',message='La clase supera el límite de 500 alumnos';end if;
 result:=jsonb_build_object('course',(select jsonb_build_object('id',c.id,'name',s.name,'period_name',p.name) from public.subjects s join public.academic_periods p on p.id=c.period_id where s.id=c.subject_id),'students',students);
 return result||jsonb_build_object('token',md5(result::text));
end;$$;
revoke all on function public._school_finals_snapshot(uuid) from public,anon,authenticated;

create or replace function public.portal_school_finals_read(p_course uuid)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
begin
 perform pg_catalog.pg_advisory_xact_lock_shared(72643219);
 return public._school_finals_snapshot(p_course);
end;$$;

create or replace function public.portal_school_finals_save(p_course uuid,p_token text,p_items jsonb,p_reason text default '')
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare actor uuid; state jsonb; r jsonb; before_row jsonb; eid uuid; score numeric; rev integer;
 reason text:=btrim(coalesce(p_reason,'')); changed integer:=0; audit_snapshot jsonb;
begin
 perform pg_catalog.pg_advisory_xact_lock(72643219);
 actor:=public._require_control_catalog_access();
 state:=public._school_finals_snapshot(p_course);
 if p_token is null or p_token is distinct from state->>'token' then raise exception using errcode='PT409',message='Las notas o alumnos cambiaron. Actualiza y revisa antes de publicar.';end if;
 if p_items is null or jsonb_typeof(p_items)<>'array' or jsonb_array_length(p_items) not between 1 and 500
  or char_length(reason)>1000 then raise exception using errcode='22023',message='Selecciona entre 1 y 500 calificaciones finales';end if;
 if (select count(distinct x->>'enrollment_id') from jsonb_array_elements(p_items) x)<>jsonb_array_length(p_items) then
  raise exception using errcode='22023',message='Hay alumnos duplicados';end if;
 -- Validar el lote completo antes de escribir una sola nota.
 for r in select value from jsonb_array_elements(p_items) loop
  if jsonb_typeof(r)<>'object' or (r-'enrollment_id'-'score')<>'{}'::jsonb or jsonb_typeof(r->'score') is distinct from 'number' then
   raise exception using errcode='22023',message='Calificación final inválida';end if;
  eid:=(r->>'enrollment_id')::uuid;score:=(r->>'score')::numeric;
  if score is null or score not between 0 and 100 or score<>round(score,2) then raise exception using errcode='22023',message='La calificación final debe estar entre 0 y 10';end if;
  select x into before_row from jsonb_array_elements(state->'students') x where x->>'enrollment_id'=eid::text;
  if before_row is null then raise exception using errcode='42501',message='El alumno no pertenece a esta clase activa';end if;
  if ((before_row->>'published_score')::numeric is not null and score<>(before_row->>'published_score')::numeric
      or coalesce((before_row->'calculation'->>'configured')::boolean,false)) and char_length(reason)<10 then
   raise exception using errcode='22023',message='Explica la captura/corrección con al menos 10 caracteres';end if;
 end loop;
 for r in select value from jsonb_array_elements(p_items) loop
  eid:=(r->>'enrollment_id')::uuid;score:=(r->>'score')::numeric;
  select x into before_row from jsonb_array_elements(state->'students') x where x->>'enrollment_id'=eid::text;
  if score is not distinct from (before_row->>'published_score')::numeric and score is not distinct from (before_row->>'draft_score')::numeric then continue;end if;
  rev:=(before_row->>'revision')::integer+1;
  audit_snapshot:=jsonb_build_object('source','control_escolar_manual','score',score,'before',before_row,'reason',reason,'course_id',p_course);
  insert into public.learning_final_calculations(enrollment_id,snapshot,reason,actor_id,created_at) values(eid,audit_snapshot,reason,actor,now())
   on conflict(enrollment_id)do update set snapshot=excluded.snapshot,reason=excluded.reason,actor_id=excluded.actor_id,created_at=excluded.created_at;
  insert into public.enrollment_grades(enrollment_id,score,published)values(eid,score,true)
   on conflict(enrollment_id)do update set score=excluded.score,published=true;
  insert into public.enrollment_grade_drafts(enrollment_id,score,revision,needs_publication,updated_by)values(eid,score,rev,false,actor)
   on conflict(enrollment_id)do update set score=excluded.score,revision=excluded.revision,needs_publication=false,updated_by=excluded.updated_by,updated_at=now();
  insert into public.enrollment_grade_events(enrollment_id,actor_id,assignment_id,action,old_draft_score,old_published_score,score,revision)
   values(eid,actor,p_course,'publish',(before_row->>'draft_score')::numeric,(before_row->>'published_score')::numeric,score,rev);
  insert into public.learning_audit(actor_id,course_id,action,entity_id,details)values(actor,p_course,'school_final_publish',eid,audit_snapshot);
  changed:=changed+1;
 end loop;
 return public._school_finals_snapshot(p_course)||jsonb_build_object('saved',true,'changed',changed);
exception when invalid_text_representation or numeric_value_out_of_range then raise exception using errcode='22023',message='Revisa alumnos y calificaciones finales';
end;$$;

create table if not exists public.report_card_group_batches (
 id uuid primary key,actor_id uuid not null references public.profiles(id) on delete restrict,
 request_hash text not null,result jsonb not null,created_at timestamptz not null default now()
);
alter table public.report_card_group_batches enable row level security;
revoke all on public.report_card_group_batches from public,anon,authenticated;

create or replace function public._report_group_snapshot(p_period uuid,p_stage text,p_semester integer)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare code text; period_name text; r record; preview jsonb; latest jsonb; rows jsonb:='[]'; result jsonb; usable boolean; reuse boolean;
begin
 perform public._require_control_catalog_access();
 if p_semester is null or not exists(select 1 from public.formation_stages where formation_stages.code=p_stage and p_semester between 1 and semesters) then
  raise exception using errcode='22023',message='Selecciona un curso válido';end if;
 select name into period_name from public.academic_periods where id=p_period;
 if not found then raise exception using errcode='22023',message='Periodo no encontrado';end if;
 code:=(case when p_stage='introductorio' then 'CI' else ((p_semester+1)/2)::text||case when p_stage='filosofia' then 'F' else 'T' end end)||'-'||p_semester;
 for r in select p.id,p.full_name from public.student_formation_periods f join public.profiles p on p.id=f.student_id
  where f.period_id=p_period and f.stage_code=p_stage and f.semester=p_semester and p.role='student'
   and exists(select 1 from public.enrollments e where e.student_id=p.id and e.period_id=p_period and e.active)
  order by p.full_name,p.id loop
  if jsonb_array_length(rows)>=200 then raise exception using errcode='22023',message='El grupo supera el límite de 200 boletas';end if;
  preview:=public._report_card_preview(r.id,p_period,'{}');
  -- Una inscripción equivocada no debe llegar a una emisión masiva.
  if exists(select 1 from public.enrollments e left join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
    left join public.course_formation_groups g on g.course_id=c.id where e.student_id=r.id and e.period_id=p_period and e.active and g.group_code is distinct from code) then
   preview:=jsonb_set(preview,'{ready}','false');
   preview:=jsonb_set(preview,'{reasons}',(preview->'reasons')||jsonb_build_array('Hay materias fuera de '||code||'; revisa sus inscripciones antes de emitir.'));
  end if;
  select to_jsonb(i)-'request_hash'-'issued_by' into latest from public.report_card_issues i where i.student_id=r.id and i.period_id=p_period order by i.issued_at desc,i.id desc limit 1;
  usable:=(preview->>'ready')::boolean;
  reuse:=usable and latest is not null and ((latest->'snapshot')-'token')=(preview-'token');
  rows:=rows||jsonb_build_array(jsonb_build_object('student_id',r.id,'name',r.full_name,'preview',preview,
    'existing',latest,'action',case when not usable then 'pending' when reuse then 'reuse' else 'issue' end));
 end loop;
 result:=jsonb_build_object('period_id',p_period,'period_name',period_name,'stage',p_stage,'semester',p_semester,'group_code',code,'items',rows);
 return result||jsonb_build_object('token',md5(result::text));
end;$$;
revoke all on function public._report_group_snapshot(uuid,text,integer) from public,anon,authenticated;

create or replace function public.portal_report_group_read(p_period uuid,p_stage text,p_semester integer)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
begin
 perform pg_catalog.pg_advisory_xact_lock_shared(72643219);
 return public._report_group_snapshot(p_period,p_stage,p_semester);
end;$$;

create or replace function public._report_group_result(p_batch uuid)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare batch public.report_card_group_batches%rowtype; documents jsonb;
begin
 perform public._require_control_catalog_access();
 select * into batch from public.report_card_group_batches where id=p_batch and actor_id=auth.uid();
 if not found then raise exception using errcode='42501',message='Lote no disponible';end if;
 select coalesce(jsonb_agg(to_jsonb(i)-'request_hash'-'issued_by' order by i.snapshot->'student'->>'full_name',i.id),'[]') into documents
 from public.report_card_issues i where i.id in (select value::text::uuid from jsonb_array_elements_text(batch.result->'issue_ids'));
 if jsonb_array_length(documents)<>jsonb_array_length(batch.result->'issue_ids') then raise exception using errcode='22023',message='Falta una boleta del lote confirmado';end if;
 return (batch.result-'issue_ids')||jsonb_build_object('saved',true,'batch_id',batch.id,'documents',documents);
end;$$;
revoke all on function public._report_group_result(uuid) from public,anon,authenticated;

create or replace function public.portal_report_group_issue(p_period uuid,p_stage text,p_semester integer,p_token text,p_request uuid,p_confirmed boolean)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare actor uuid; fingerprint text; batch public.report_card_group_batches%rowtype; plan jsonb; r jsonb; issued jsonb;
 ids jsonb:='[]'; pending jsonb:='[]'; result jsonb; total integer:=0; newly integer:=0; reused integer:=0;
begin
 perform pg_catalog.pg_advisory_xact_lock(72643219);
 actor:=public._require_control_catalog_access();
 if p_request is null or p_confirmed is distinct from true then raise exception using errcode='22023',message='Revisa y confirma el grupo antes de descargar';end if;
 fingerprint:=md5(jsonb_build_object('period',p_period,'stage',p_stage,'semester',p_semester,'token',p_token)::text);
 select * into batch from public.report_card_group_batches where id=p_request;
 if found then
  if batch.actor_id<>actor or batch.request_hash<>fingerprint then raise exception using errcode='PT409',message='La solicitud corresponde a otro lote';end if;
  return public._report_group_result(batch.id);
 end if;
 plan:=public._report_group_snapshot(p_period,p_stage,p_semester);
 if p_token is null or p_token is distinct from plan->>'token' then raise exception using errcode='PT409',message='Cambió el grupo o sus notas. Actualiza y revisa el lote otra vez.';end if;
 for r in select value from jsonb_array_elements(plan->'items') loop
  total:=total+1;
  if r->>'action'='pending' then
   pending:=pending||jsonb_build_array(jsonb_build_object('name',r->>'name','reasons',r->'preview'->'reasons'));
  elsif r->>'action'='reuse' then
   ids:=ids||jsonb_build_array(r->'existing'->>'id');reused:=reused+1;
  else
   issued:=public.portal_report_card_issue((r->>'student_id')::uuid,p_period,'{}',r->'preview'->>'token',gen_random_uuid());
   ids:=ids||jsonb_build_array(issued->>'id');newly:=newly+1;
  end if;
 end loop;
 if jsonb_array_length(ids)=0 then raise exception using errcode='22023',message='No hay boletas listas. Completa matrículas, finales y firmantes antes de emitir.';end if;
 result:=jsonb_build_object('period_id',p_period,'period_name',plan->>'period_name','group_code',plan->>'group_code',
  'issue_ids',ids,'pending',pending,'total',total,'newly_issued',newly,'reused',reused);
 insert into public.report_card_group_batches(id,actor_id,request_hash,result)values(p_request,actor,fingerprint,result);
 insert into public.management_events(actor_id,action,entity_id,details)values(actor,'report_card_group_batch',p_request,result-'issue_ids'-'pending');
 return public._report_group_result(p_request);
end;$$;

revoke all on function public.portal_school_finals_read(uuid),public.portal_school_finals_save(uuid,text,jsonb,text),
 public.portal_report_group_read(uuid,text,integer),public.portal_report_group_issue(uuid,text,integer,text,uuid,boolean) from public,anon,authenticated;
grant execute on function public.portal_school_finals_read(uuid),public.portal_school_finals_save(uuid,text,jsonb,text),
 public.portal_report_group_read(uuid,text,integer),public.portal_report_group_issue(uuid,text,integer,text,uuid,boolean) to authenticated;
notify pgrst,'reload schema';
commit;
