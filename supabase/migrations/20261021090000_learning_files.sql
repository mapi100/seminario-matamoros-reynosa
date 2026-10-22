-- Adjuntos privados: aplicar una vez después de 20261021080000_learning_workspace.sql.
-- Supabase Storage debe estar disponible. No modifica los buckets existentes.
begin;

create table public.learning_submission_files (
    id uuid primary key default gen_random_uuid(),
    assignment_id uuid not null references public.learning_assignments(id) on delete restrict,
    enrollment_id uuid not null references public.enrollments(id) on delete restrict,
    object_path text not null unique check (char_length(object_path)<=400),
    name text not null check (char_length(name) between 1 and 160),
    size bigint not null check (size between 1 and 5242880),
    mimetype text not null,
    uploaded_by uuid not null references public.profiles(id) on delete restrict,
    created_at timestamptz not null default now()
);
create index learning_submission_files_task_idx on public.learning_submission_files(assignment_id,enrollment_id,created_at,id);
alter table public.learning_submission_files enable row level security;
revoke all on public.learning_submission_files from public,anon,authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('portal-coursework','portal-coursework',false,5242880,array[
    'application/pdf','image/jpeg','image/png','text/plain',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
]);

-- Solo una proyección booleana se concede al rol de Storage. No expone registros.
-- SELECT permite al alumno leer su objeto y al profesor leer adjuntos registrados;
-- INSERT no permite escribir en el nombre de otro alumno ni sobrescribir objetos.
create function public._learning_file_authorized(p_path text,p_action text)
returns boolean language plpgsql volatile security definer set search_path=''
as $$
declare parts text[]; path_course uuid; path_assignment uuid; path_student uuid;
    person_role text; task public.learning_assignments%rowtype; enrollment uuid;
begin
    if p_path is null or char_length(p_path)>400 or p_action is null or p_action not in ('read','insert','attach','delete') then return false; end if;
    parts:=pg_catalog.string_to_array(p_path,'/');
    if cardinality(parts)<>5 or parts[5] !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(pdf|jpg|jpeg|png|txt|docx)$' then return false; end if;
    path_course:=parts[1]::uuid; path_assignment:=parts[2]::uuid; path_student:=parts[3]::uuid;
    perform parts[4]::uuid;
    if not public._learning_can_course(path_course) then return false; end if;
    select p.role into person_role from public.profiles p where p.id=auth.uid() and p.active;
    select t.* into task from public.learning_assignments t where t.id=path_assignment and t.course_id=path_course;
    if not found then return false; end if;
    select e.id into enrollment from public.enrollments e
      join public.course_offerings c on c.id=path_course and c.subject_id=e.subject_id and c.period_id=e.period_id
      join public.profiles p on p.id=e.student_id and p.active and p.role='student'
      where e.student_id=path_student and e.active;
    if enrollment is null then return false; end if;
    if p_action='read' then
        if person_role='student' then return path_student=auth.uid() and task.published; end if;
        return person_role in ('professor','control_escolar') and exists (
            select 1 from public.learning_submission_files f
            where f.object_path=p_path and f.assignment_id=path_assignment and f.enrollment_id=enrollment);
    end if;
    if person_role<>'student' or path_student<>auth.uid() then return false; end if;
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._learning_require_course(path_course,false);
    select t.* into task from public.learning_assignments t where t.id=path_assignment and t.course_id=path_course for share of t;
    if p_action='delete' then
        -- Los objetos no registrados pueden limpiarse después del cierre de la tarea.
        return not exists(select 1 from public.learning_submission_files f where f.object_path=p_path);
    end if;
    return task.published and (task.allow_late or task.due_at is null or clock_timestamp()<=task.due_at)
        and (select count(*) from public.learning_submission_files f where f.assignment_id=path_assignment and f.enrollment_id=enrollment)<3
        -- Contar también subidas sin registrar evita agotar Storage con objetos huérfanos.
        -- Al adjuntar, el objeto ya está almacenado y debe permitirse el tercero.
        and (select count(*) from storage.objects o where o.bucket_id='portal-coursework'
            and lower(split_part(o.name,'/',1))=path_course::text
            and lower(split_part(o.name,'/',2))=path_assignment::text
            and lower(split_part(o.name,'/',3))=path_student::text)
            < case when p_action='attach' then 4 else 3 end;
exception when invalid_text_representation or insufficient_privilege then
    return false;
end;
$$;
revoke all on function public._learning_file_authorized(text,text) from public,anon,authenticated;
grant execute on function public._learning_file_authorized(text,text) to authenticated;

create policy "Learning students upload own coursework" on storage.objects
for insert to authenticated with check (
    bucket_id='portal-coursework' and owner_id=auth.uid()::text
    and public._learning_file_authorized(name,'insert')
);
create policy "Learning coursework stays private" on storage.objects
for select to authenticated using (
    bucket_id='portal-coursework' and public._learning_file_authorized(name,'read')
);
create policy "Learning students clean unattached coursework" on storage.objects
for delete to authenticated using (
    bucket_id='portal-coursework' and owner_id=auth.uid()::text
    and public._learning_file_authorized(name,'delete')
);

create or replace function public._learning_has_submission_file(p_assignment uuid,p_enrollment uuid)
returns boolean language sql stable security definer set search_path=''
as $$ select exists(select 1 from public.learning_submission_files f where f.assignment_id=p_assignment and f.enrollment_id=p_enrollment) $$;
revoke all on function public._learning_has_submission_file(uuid,uuid) from public,anon,authenticated;

create function public.portal_learning_files(p_action text,p_course uuid,p_assignment uuid,p_data jsonb default '{}'::jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare person_role text; task public.learning_assignments%rowtype; enrollment uuid;
    selected_file public.learning_submission_files%rowtype; object_row storage.objects%rowtype;
    course public.course_offerings%rowtype; current_submission public.learning_submissions%rowtype;
    object_path text; original_name text; detected_size bigint; detected_mime text;
    extension text; expected_mime text; entity uuid; result jsonb; submission_result jsonb;
begin
    if p_action is null or p_action not in ('list','attach','remove') or p_data is null or jsonb_typeof(p_data)<>'object' then
        raise exception using errcode='22023',message='Solicitud de archivos inválida'; end if;
    if p_action<>'list' then perform pg_catalog.pg_advisory_xact_lock(72643219); end if;
    person_role:=public._learning_require_course(p_course,false);
    select t.* into task from public.learning_assignments t where t.id=p_assignment and t.course_id=p_course for share of t;
    if not found or (person_role='student' and not task.published) then
        raise exception using errcode='42501',message='No tienes acceso a los archivos de esta tarea'; end if;
    select c.* into course from public.course_offerings c where c.id=p_course;
    if person_role='student' then
        select e.id into enrollment from public.enrollments e where e.student_id=auth.uid()
          and e.subject_id=course.subject_id and e.period_id=course.period_id and e.active for share of e;
        if p_data ? 'enrollment_id' and (p_data->>'enrollment_id')::uuid is distinct from enrollment then
            raise exception using errcode='42501',message='Solo puedes consultar tus propios archivos'; end if;
    else
        if p_action<>'list' then raise exception using errcode='42501',message='Solo el alumno puede cambiar sus adjuntos'; end if;
        if not (p_data ? 'enrollment_id') then return jsonb_build_object('items','[]'::jsonb,'can_upload',false); end if;
        select e.id into enrollment from public.enrollments e join public.profiles p on p.id=e.student_id and p.active and p.role='student'
          where e.id=(p_data->>'enrollment_id')::uuid and e.subject_id=course.subject_id and e.period_id=course.period_id and e.active for share of e,p;
    end if;
    if enrollment is null then raise exception using errcode='42501',message='Inscripción no disponible'; end if;

    if p_action='list' then
        select coalesce(jsonb_agg(to_jsonb(rows)),'[]'::jsonb) into result from (
            select f.id,f.name,f.size,f.mimetype,f.created_at,f.object_path
            from public.learning_submission_files f where f.assignment_id=p_assignment and f.enrollment_id=enrollment
            order by f.created_at,f.id limit 3
        ) rows;
        return jsonb_build_object('items',result,'can_upload',person_role='student' and task.published
          and (task.allow_late or task.due_at is null or clock_timestamp()<=task.due_at) and jsonb_array_length(result)<3
          and (select count(*) from storage.objects o where o.bucket_id='portal-coursework'
            and lower(split_part(o.name,'/',1))=p_course::text
            and lower(split_part(o.name,'/',2))=p_assignment::text
            and lower(split_part(o.name,'/',3))=auth.uid()::text)<3,
          'can_remove',person_role='student' and task.published and (task.allow_late or task.due_at is null or clock_timestamp()<=task.due_at));
    end if;
    if not task.published or (not task.allow_late and task.due_at is not null and clock_timestamp()>task.due_at) then
        raise exception using errcode='22023',message='La fecha límite de esta tarea ya pasó'; end if;
    select s.* into current_submission from public.learning_submissions s where s.assignment_id=p_assignment and s.enrollment_id=enrollment for update of s;
    if p_action='attach' then
        object_path:=p_data->>'object_path'; original_name:=btrim(p_data->>'name');
        if original_name is null or char_length(original_name) not between 1 and 160 or original_name ~ '[[:cntrl:]/\\]' then
            raise exception using errcode='22023',message='Nombre de archivo inválido'; end if;
        if not public._learning_file_authorized(object_path,'attach') then
            raise exception using errcode='42501',message='No puedes adjuntar este archivo'; end if;
        select o.* into object_row from storage.objects o
          where o.bucket_id='portal-coursework' and o.name=object_path and o.owner_id=auth.uid()::text for share of o;
        if not found then raise exception using errcode='22023',message='Primero sube el archivo de tu entrega'; end if;
        if coalesce(object_row.metadata->>'size','') !~ '^[0-9]{1,10}$' then
            raise exception using errcode='22023',message='Tamaño de archivo no disponible'; end if;
        detected_size:=(object_row.metadata->>'size')::bigint; detected_mime:=object_row.metadata->>'mimetype';
        extension:=lower(substring(original_name from '\.([A-Za-z0-9]+)$'));
        expected_mime:=case extension when 'pdf' then 'application/pdf' when 'jpg' then 'image/jpeg'
          when 'jpeg' then 'image/jpeg' when 'png' then 'image/png' when 'txt' then 'text/plain'
          when 'docx' then 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' else null end;
        if detected_size not between 1 and 5242880 or expected_mime is null or detected_mime is distinct from expected_mime
          or lower(substring(object_path from '\.([A-Za-z0-9]+)$')) is distinct from extension then
            raise exception using errcode='22023',message='Usa PDF, JPG, PNG, TXT o DOCX de hasta 5 MB'; end if;
        insert into public.learning_submission_files(assignment_id,enrollment_id,object_path,name,size,mimetype,uploaded_by)
          values(p_assignment,enrollment,object_path,original_name,detected_size,detected_mime,auth.uid()) returning id into entity;
        -- Registrar el archivo y la entrega es una sola transacción; conserva texto y liga.
        submission_result:=public.portal_learning_write('submit',p_course,jsonb_build_object('assignment_id',p_assignment,
          'body',coalesce(current_submission.body,''),'url',coalesce(current_submission.url,'')));
        insert into public.learning_audit(actor_id,course_id,action,entity_id,details)
          values(auth.uid(),p_course,'file_attach',entity,jsonb_build_object('assignment_id',p_assignment,'name',original_name,'size',detected_size));
    else
        select f.* into selected_file from public.learning_submission_files f where f.id=(p_data->>'id')::uuid
          and f.assignment_id=p_assignment and f.enrollment_id=enrollment for update of f;
        if not found then raise exception using errcode='42501',message='Archivo no disponible'; end if;
        if (select count(*) from public.learning_submission_files f where f.assignment_id=p_assignment and f.enrollment_id=enrollment)<=1
          and coalesce(btrim(current_submission.body),'')='' and coalesce(btrim(current_submission.url),'')='' then
            raise exception using errcode='22023',message='Conserva un archivo o escribe una entrega antes de retirar el último adjunto'; end if;
        entity:=selected_file.id;
        delete from public.learning_submission_files f where f.id=entity;
        submission_result:=public.portal_learning_write('submit',p_course,jsonb_build_object('assignment_id',p_assignment,
          'body',coalesce(current_submission.body,''),'url',coalesce(current_submission.url,'')));
        insert into public.learning_audit(actor_id,course_id,action,entity_id,details)
          values(auth.uid(),p_course,'file_remove',entity,jsonb_build_object('assignment_id',p_assignment,'name',selected_file.name,'size',selected_file.size));
    end if;
    return jsonb_build_object('id',entity,'saved',true);
exception when unique_violation then
    raise exception using errcode='PT409',message='Este archivo ya está registrado';
end;
$$;
revoke all on function public.portal_learning_files(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.portal_learning_files(text,uuid,uuid,jsonb) to authenticated;

commit;
