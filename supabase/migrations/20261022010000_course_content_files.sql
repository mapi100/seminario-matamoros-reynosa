-- Aplicar una vez después de 20261022000000_staff_teaching_deletion.sql.
-- Archivos docentes privados; no cambia el estado de los temas existentes.
begin;
create table public.learning_content_files (
    id uuid primary key default gen_random_uuid(),
    course_id uuid not null references public.course_offerings(id) on delete restrict,
    topic_id uuid not null references public.learning_topics(id) on delete restrict,
    object_path text not null unique check(char_length(object_path)<=400),
    name text not null check(char_length(name) between 1 and 160),
    size bigint not null check(size between 1 and 10485760),
    mimetype text not null,
    uploaded_by uuid not null references public.profiles(id) on delete restrict,
    created_at timestamptz not null default now()
);
create index learning_content_files_topic_idx on public.learning_content_files(topic_id,created_at,id);
alter table public.learning_content_files enable row level security;
revoke all on public.learning_content_files from public,anon,authenticated;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('portal-content','portal-content',false,10485760,array[
    'application/pdf','application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-powerpoint','application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/rtf','text/plain','image/jpeg','image/png','image/webp','application/zip']);

create function public._content_mime(p_extension text)
returns text language sql immutable set search_path=''
as $$ select case p_extension
    when 'pdf' then 'application/pdf' when 'doc' then 'application/msword'
    when 'docx' then 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    when 'ppt' then 'application/vnd.ms-powerpoint'
    when 'pptx' then 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    when 'xls' then 'application/vnd.ms-excel'
    when 'xlsx' then 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    when 'rtf' then 'application/rtf' when 'txt' then 'text/plain'
    when 'jpg' then 'image/jpeg' when 'jpeg' then 'image/jpeg'
    when 'png' then 'image/png' when 'webp' then 'image/webp' when 'zip' then 'application/zip' end $$;
revoke all on function public._content_mime(text) from public,anon,authenticated;

create function public._content_file_authorized(p_path text,p_action text)
returns boolean language plpgsql volatile security definer set search_path=''
as $$
declare parts text[]; course uuid; topic uuid; staff boolean; person_role text;
begin
    if p_path is null or char_length(p_path)>400 or p_action is null or p_action not in ('read','insert','delete','attach') then return false; end if;
    parts:=string_to_array(p_path,'/');
    if cardinality(parts)<>4 or parts[4] !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(pdf|doc|docx|ppt|pptx|xls|xlsx|rtf|txt|jpg|jpeg|png|webp|zip)$' then return false; end if;
    course:=parts[1]::uuid;topic:=parts[2]::uuid;perform parts[3]::uuid;
    if not public._learning_can_course(course) then return false; end if;
    select p.role into person_role from public.profiles p where p.id=auth.uid() and p.active;
    if person_role is null then return false; end if;
    staff:=person_role in ('professor','control_escolar');
    if not exists(select 1 from public.learning_topics t join public.learning_modules m on m.id=t.module_id and m.course_id=t.course_id
        where t.id=topic and t.course_id=course and (staff or t.published and m.published)) then return false; end if;
    if p_action='read' then
        return exists(select 1 from public.learning_content_files f where f.object_path=p_path and f.course_id=course and f.topic_id=topic);
    end if;
    if not staff then return false; end if;
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._learning_require_course(course,true);
    if p_action='delete' then
        return not exists(select 1 from public.learning_content_files f where f.object_path=p_path);
    end if;
    return (select count(*) from public.learning_content_files f where f.topic_id=topic)<5
        and (select count(*) from storage.objects o where o.bucket_id='portal-content'
            and lower(split_part(o.name,'/',1))=course::text and lower(split_part(o.name,'/',2))=topic::text)
            <case when p_action='attach' then 6 else 5 end;
exception when invalid_text_representation or insufficient_privilege then return false;
end;
$$;
revoke all on function public._content_file_authorized(text,text) from public,anon,authenticated;
grant execute on function public._content_file_authorized(text,text) to authenticated;
create policy "Staff upload course content" on storage.objects for insert to authenticated
    with check(bucket_id='portal-content' and owner_id=auth.uid()::text and public._content_file_authorized(name,'insert'));
create policy "Course content stays private" on storage.objects for select to authenticated
    using(bucket_id='portal-content' and public._content_file_authorized(name,'read'));
-- SELECT permite que la API de Storage localice una subida todavía sin registrar.
create policy "Staff read unregistered content" on storage.objects for select to authenticated
    using(bucket_id='portal-content' and public._content_file_authorized(name,'delete'));
create policy "Staff clean unregistered content" on storage.objects for delete to authenticated
    using(bucket_id='portal-content' and public._content_file_authorized(name,'delete'));

-- Ampliar la limpieza reanudable a ambos buckets privados, conservando pendientes.
alter table public.portal_file_cleanup add column bucket_id text not null default 'portal-coursework'
    check(bucket_id in ('portal-coursework','portal-content'));
alter table public.portal_file_cleanup drop constraint portal_file_cleanup_pkey;
alter table public.portal_file_cleanup add primary key(bucket_id,object_path);
create function public._portal_cleanup_authorized(p_path text,p_bucket text)
returns boolean language sql stable security definer set search_path=''
as $$ select exists(select 1 from public.profiles p where p.id=auth.uid() and p.active and p.role='control_escolar')
    and exists(select 1 from public.portal_file_cleanup q where q.object_path=p_path and q.bucket_id=p_bucket) $$;
revoke all on function public._portal_cleanup_authorized(text,text) from public,anon,authenticated;
grant execute on function public._portal_cleanup_authorized(text,text) to authenticated;
create or replace function public._portal_cleanup_authorized(p_path text)
returns boolean language sql stable security definer set search_path=''
as $$ select public._portal_cleanup_authorized(p_path,'portal-coursework') $$;
create policy "Control reads queued course content" on storage.objects for select to authenticated
    using(bucket_id='portal-content' and public._portal_cleanup_authorized(name,'portal-content'));
create policy "Control deletes queued course content" on storage.objects for delete to authenticated
    using(bucket_id='portal-content' and public._portal_cleanup_authorized(name,'portal-content'));

create function public.portal_content_files(p_action text,p_course uuid,p_topic uuid,p_data jsonb default '{}'::jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare person_role text; staff boolean; topic public.learning_topics%rowtype; selected public.learning_content_files%rowtype;
    object_row storage.objects%rowtype; path text; original_name text; extension text; size_value bigint; expected text;
    result jsonb; pending jsonb; entity uuid;
begin
    if p_action is null or p_action not in ('list','attach','remove') or p_data is null or jsonb_typeof(p_data)<>'object' then
        raise exception using errcode='22023',message='Solicitud de archivos inválida'; end if;
    if p_action<>'list' then perform pg_catalog.pg_advisory_xact_lock(72643219); end if;
    person_role:=public._learning_require_course(p_course,p_action<>'list');staff:=person_role in ('professor','control_escolar');
    select t.* into topic from public.learning_topics t join public.learning_modules m on m.id=t.module_id and m.course_id=t.course_id
        where t.id=p_topic and t.course_id=p_course and (staff or t.published and m.published) for share of t,m;
    if not found then raise exception using errcode='42501',message='No tienes acceso a este contenido'; end if;
    if p_action='list' then
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from (
            select f.id,f.name,f.size,f.mimetype,f.object_path from public.learning_content_files f where f.topic_id=p_topic order by f.created_at,f.id limit 5) r;
        pending:='[]'::jsonb;
        if staff then
            select coalesce(jsonb_agg(r.name),'[]'::jsonb) into pending from (
                select o.name from storage.objects o where o.bucket_id='portal-content' and o.owner_id=auth.uid()::text
                and lower(split_part(o.name,'/',1))=p_course::text and lower(split_part(o.name,'/',2))=p_topic::text
                and not exists(select 1 from public.learning_content_files f where f.object_path=o.name) order by o.name limit 5) r;
        end if;
        return jsonb_build_object('items',result,'pending',pending,'can_manage',staff);
    end if;
    if p_action='remove' then
        select f.* into selected from public.learning_content_files f where f.id=(p_data->>'id')::uuid
            and f.course_id=p_course and f.topic_id=p_topic for update;
        if not found then raise exception using errcode='22023',message='El archivo ya no está en este tema'; end if;
        entity:=selected.id;
        insert into public.portal_file_cleanup(bucket_id,object_path,deleted_course_id,requested_by)
            values('portal-content',selected.object_path,p_course,auth.uid()) on conflict do nothing;
        delete from public.learning_content_files where id=entity;
    else
        path:=p_data->>'object_path';original_name:=btrim(p_data->>'name');
        if original_name is null or char_length(original_name) not between 1 and 160 or original_name ~ '[[:cntrl:]/\\]' then
            raise exception using errcode='22023',message='Nombre de archivo inválido'; end if;
        if split_part(path,'/',1) is distinct from p_course::text or split_part(path,'/',2) is distinct from p_topic::text then
            raise exception using errcode='42501',message='El archivo no corresponde a este tema'; end if;
        -- Un reintento con la misma ruta confirma el registro sin duplicarlo.
        select f.* into selected from public.learning_content_files f where f.object_path=path;
        if found then
            if selected.name is distinct from original_name or selected.topic_id<>p_topic or selected.course_id<>p_course then
                raise exception using errcode='22023',message='La ruta ya pertenece a otro archivo'; end if;
            return jsonb_build_object('saved',true,'id',selected.id);
        end if;
        if not public._content_file_authorized(path,'attach') then raise exception using errcode='22023',message='El tema admite hasta 5 archivos; limpia las subidas incompletas si es necesario'; end if;
        select o.* into object_row from storage.objects o where o.bucket_id='portal-content' and o.name=path and o.owner_id=auth.uid()::text for share;
        if not found then raise exception using errcode='PT404',message='Primero sube este archivo'; end if;
        extension:=lower(substring(original_name from '\.([A-Za-z0-9]+)$'));expected:=public._content_mime(extension);
        if coalesce(object_row.metadata->>'size','') !~ '^[0-9]{1,10}$' then raise exception using errcode='22023',message='Tamaño inválido'; end if;
        size_value:=(object_row.metadata->>'size')::bigint;
        if expected is null or object_row.metadata->>'mimetype' is distinct from expected or size_value not between 1 and 10485760
            or lower(substring(path from '\.([A-Za-z0-9]+)$')) is distinct from extension then
            raise exception using errcode='22023',message='Formato o tamaño inválido; usa archivos de hasta 10 MB'; end if;
        insert into public.learning_content_files(course_id,topic_id,object_path,name,size,mimetype,uploaded_by)
            values(p_course,p_topic,path,original_name,size_value,expected,auth.uid()) returning id into entity;
    end if;
    insert into public.learning_audit(actor_id,course_id,action,entity_id,details)
        values(auth.uid(),p_course,'content_file_'||p_action,entity,jsonb_build_object('topic_id',p_topic));
    return jsonb_build_object('saved',true,'id',entity);
exception when invalid_text_representation then raise exception using errcode='22023',message='Datos de archivo inválidos';
end;
$$;
revoke all on function public.portal_content_files(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.portal_content_files(text,uuid,uuid,jsonb) to authenticated;

create or replace function public.portal_learning_read(p_resource text,p_course uuid default null,p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare person public.profiles%rowtype; actor uuid; actor_role text; manage boolean; own_enrollment uuid;
    course public.course_offerings%rowtype; result jsonb; courses jsonb; announcements jsonb;
    modules jsonb; assignments jsonb; events jsonb; work jsonb; students jsonb; items jsonb; institutional jsonb;
begin
    person:=public._learning_require_actor(); actor:=person.id; actor_role:=person.role;
    if p_offset is null or p_offset<0 or p_offset>100000 or p_limit is null or p_limit<1 or p_limit>100 then
        raise exception using errcode='22023',message='Paginación inválida'; end if;
    if p_resource='dashboard' then
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into courses from (
            select c.id,c.subject_id,c.period_id,s.code,s.name,a.name as period_name,a.starts_on,a.ends_on,
                actor_role as role,case when g.published then g.score else null end as final_score
            from public.course_offerings c join public.subjects s on s.id=c.subject_id
            join public.academic_periods a on a.id=c.period_id
            left join public.enrollments e on e.student_id=actor and e.subject_id=c.subject_id and e.period_id=c.period_id and e.active and actor_role='student'
            left join public.enrollment_grades g on g.enrollment_id=e.id
            where public._learning_can_course(c.id)
            order by a.starts_on desc,s.code,c.id offset p_offset limit p_limit+1
        ) r;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into announcements from (
            select n.id,n.course_id,s.name as course_name,n.title,n.body,n.pinned,n.published_at
            from public.learning_announcements n left join public.course_offerings c on c.id=n.course_id
            left join public.subjects s on s.id=c.subject_id
            where n.published and (n.course_id is null or public._learning_can_course(n.course_id))
            order by n.pinned desc,n.published_at desc,n.id limit 50
        ) r;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into work from (
            select t.id,t.course_id,s.name as course_name,t.title,t.due_at,
                case when t.due_at<now() and not t.allow_late then 'closed'
                     when t.due_at<now() then 'late' else 'pending' end as status,
                null::timestamptz as submitted_at
            from public.learning_assignments t join public.course_offerings c on c.id=t.course_id
            join public.subjects s on s.id=c.subject_id
            where t.published and public._learning_can_course(t.course_id)
                and (actor_role<>'student' or not exists(select 1 from public.learning_submissions x
                    join public.enrollments e on e.id=x.enrollment_id where x.assignment_id=t.id and e.student_id=actor and e.active))
            order by t.due_at asc nulls last,t.id limit 50
        ) r;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into events from (
            select v.id,v.course_id,s.name as course_name,v.title,v.body,v.starts_at,v.ends_at
            from public.learning_events v left join public.course_offerings c on c.id=v.course_id
            left join public.subjects s on s.id=c.subject_id
            where (v.course_id is null or public._learning_can_course(v.course_id)) and v.starts_at>=now()-interval '30 days'
            order by v.starts_at,v.id limit 100
        ) r;
        institutional:='[]'::jsonb;
        if actor_role='control_escolar' then
            select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into institutional from (
                select n.id,n.title,n.body,n.pinned,n.published,n.revision,n.published_at
                from public.learning_announcements n where n.course_id is null
                order by n.pinned desc,n.created_at desc,n.id limit 200
            ) r;
        end if;
        return jsonb_build_object('courses',(select coalesce(jsonb_agg(v),'[]'::jsonb) from jsonb_array_elements(courses) with ordinality j(v,n) where n<=p_limit),
            'has_more_courses',jsonb_array_length(courses)>p_limit,'announcements',announcements,'institutional_announcements',institutional,'work',work,'events',events);
    end if;
    if p_resource is null or p_resource not in ('course','gradebook','participants') then raise exception using errcode='22023',message='Sección inválida'; end if;
    actor_role:=public._learning_require_course(p_course,p_resource in ('gradebook','participants'));
    manage:=actor_role in ('professor','control_escolar');
    select c.* into course from public.course_offerings c where c.id=p_course;
    select e.id into own_enrollment from public.enrollments e where e.student_id=actor and e.subject_id=course.subject_id and e.period_id=course.period_id and e.active and actor_role='student';
    if p_resource='course' then
        select jsonb_build_object('id',c.id,'code',s.code,'name',s.name,'period_name',a.name,'syllabus',coalesce(z.syllabus,''),'role',actor_role,
            'final_score',case when g.published then g.score else null end) into result
        from public.course_offerings c join public.subjects s on s.id=c.subject_id
        join public.academic_periods a on a.id=c.period_id left join public.learning_course_settings z on z.course_id=c.id
        left join public.enrollment_grades g on g.enrollment_id=own_enrollment where c.id=p_course;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into announcements from (
            select n.id,n.title,n.body,n.pinned,n.published,n.published_at,n.revision from public.learning_announcements n
            where n.course_id=p_course and (manage or n.published) order by n.pinned desc,n.published_at desc nulls last,n.created_at desc,n.id limit 200
        ) r;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into modules from (
            select m.id,m.title,m.position,m.published,m.revision,
                (select coalesce(jsonb_agg(to_jsonb(q) order by q.position,q.id),'[]'::jsonb) from (
                    select t.id,t.title,t.body,t.url,t.position,t.published,t.revision,coalesce(x.completed,false) as completed,
                        (select coalesce(jsonb_agg(to_jsonb(f) order by f.created_at,f.id),'[]'::jsonb) from (
                            select cf.id,cf.name,cf.size,cf.mimetype,cf.object_path,cf.created_at
                            from public.learning_content_files cf where cf.topic_id=t.id order by cf.created_at,cf.id limit 5
                        ) f) as files
                    from public.learning_topics t left join public.learning_topic_progress x on x.topic_id=t.id and x.student_id=actor
                    where t.module_id=m.id and (manage or t.published) order by t.position,t.id limit 250
                ) q) as topics
            from public.learning_modules m where m.course_id=p_course and (manage or m.published) order by m.position,m.id limit 50
        ) r;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into assignments from (
            select t.id,t.title,t.instructions,t.due_at,t.allow_late,t.published,t.revision,
                case when x.id is null then null else jsonb_build_object('id',x.id,'body',x.body,'url',x.url,'submitted_at',x.submitted_at,'late',x.late) end as submission,
                g.published_score,g.published_feedback,g.published_at
            from public.learning_assignments t left join public.learning_submissions x on x.assignment_id=t.id and x.enrollment_id=own_enrollment
            left join public.learning_grades g on g.assignment_id=t.id and g.enrollment_id=own_enrollment
            where t.course_id=p_course and (manage or t.published) order by t.due_at asc nulls last,t.created_at,t.id limit 100
        ) r;
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into events from (
            select v.id,v.title,v.body,v.starts_at,v.ends_at,v.revision from public.learning_events v
            where v.course_id=p_course order by v.starts_at,v.id limit 200
        ) r;
        return jsonb_build_object('course',result,'announcements',announcements,'modules',modules,'assignments',assignments,'events',events,'can_manage',manage);
    elsif p_resource='participants' then
        select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into items from (
            select e.id as enrollment_id,p.full_name as name from public.enrollments e join public.profiles p on p.id=e.student_id
            where e.subject_id=course.subject_id and e.period_id=course.period_id and e.active and p.active and p.role='student'
            order by p.full_name,e.id offset p_offset limit p_limit+1
        ) r;
        return jsonb_build_object('items',(select coalesce(jsonb_agg(v),'[]'::jsonb) from jsonb_array_elements(items) with ordinality j(v,n) where n<=p_limit),'has_more',jsonb_array_length(items)>p_limit);
    end if;
    select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into assignments from (
        select t.id,t.title,t.due_at from public.learning_assignments t where t.course_id=p_course order by t.due_at asc nulls last,t.created_at,t.id limit 100
    ) r;
    select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into students from (
        select e.id as enrollment_id,p.id as student_id,p.full_name as name,case when final.published then final.score else null end as final_score,
            (select coalesce(jsonb_agg(to_jsonb(q) order by q.assignment_id),'[]'::jsonb) from (
                select t.id as assignment_id,x.id as submission_id,x.body,x.url,x.submitted_at,g.score,g.feedback,
                    g.published_score,g.published_feedback,g.published_at,coalesce(g.revision,0) as revision
                from public.learning_assignments t left join public.learning_submissions x on x.assignment_id=t.id and x.enrollment_id=e.id
                left join public.learning_grades g on g.assignment_id=t.id and g.enrollment_id=e.id
                where t.course_id=p_course order by t.id limit 100
            ) q) as grades
        from public.enrollments e join public.profiles p on p.id=e.student_id
        left join public.enrollment_grades final on final.enrollment_id=e.id
        where e.subject_id=course.subject_id and e.period_id=course.period_id and e.active and p.active and p.role='student'
        order by p.full_name,e.id offset p_offset limit p_limit+1
    ) r;
    return jsonb_build_object('assignments',assignments,'students',(select coalesce(jsonb_agg(v),'[]'::jsonb) from jsonb_array_elements(students) with ordinality j(v,n) where n<=p_limit),'has_more',jsonb_array_length(students)>p_limit);
end;
$$;

create or replace function public._portal_delete_snapshot(p_kind text,p_id uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare label text; courses uuid[]; enrollment_ids uuid[]; tasks uuid[]; topics uuid[];
    counts jsonb; result jsonb;
begin
    if p_kind='class' then
        select s.code||' · '||s.name||' · '||a.name into label
        from public.course_offerings c join public.subjects s on s.id=c.subject_id
        join public.academic_periods a on a.id=c.period_id where c.id=p_id;
    elsif p_kind='subject' then
        select s.code||' · '||s.name into label from public.subjects s where s.id=p_id;
    elsif p_kind='period' then
        select a.name into label from public.academic_periods a where a.id=p_id;
    else raise exception using errcode='22023',message='Tipo de registro inválido'; end if;
    if label is null then raise exception using errcode='22023',message='El registro ya no existe; actualiza la lista'; end if;
    select coalesce(array_agg(c.id order by c.id),'{}'::uuid[]) into courses
      from public.course_offerings c where (p_kind='class' and c.id=p_id)
        or (p_kind='subject' and c.subject_id=p_id) or (p_kind='period' and c.period_id=p_id);
    select coalesce(array_agg(e.id order by e.id),'{}'::uuid[]) into enrollment_ids
      from public.enrollments e where (p_kind='subject' and e.subject_id=p_id)
        or (p_kind='period' and e.period_id=p_id)
        or exists(select 1 from public.course_offerings c where c.id=any(courses)
            and c.subject_id=e.subject_id and c.period_id=e.period_id);
    select coalesce(array_agg(t.id order by t.id),'{}'::uuid[]) into tasks
      from public.learning_assignments t where t.course_id=any(courses);
    select coalesce(array_agg(t.id order by t.id),'{}'::uuid[]) into topics
      from public.learning_topics t where t.course_id=any(courses);
    counts:=jsonb_build_object(
        'classes',cardinality(courses),'enrollments',cardinality(enrollment_ids),
        'professors',(select count(*) from public.teaching_assignments t where
            (p_kind='subject' and t.subject_id=p_id) or (p_kind='period' and t.period_id=p_id)
            or exists(select 1 from public.course_offerings c where c.id=any(courses)
                and c.subject_id=t.subject_id and c.period_id=t.period_id)),
        'announcements',(select count(*) from public.learning_announcements n where n.course_id=any(courses)),
        'modules',(select count(*) from public.learning_modules m where m.course_id=any(courses)),
        'topics',cardinality(topics),'assignments',cardinality(tasks),
        'submissions',(select count(*) from public.learning_submissions s where s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids)),
        'grades',(select count(*) from public.learning_grades g where g.assignment_id=any(tasks) or g.enrollment_id=any(enrollment_ids))
          +(select count(*) from public.enrollment_grades g where g.enrollment_id=any(enrollment_ids))
          +(select count(*) from public.enrollment_grade_drafts g where g.enrollment_id=any(enrollment_ids)),
        'history',(select count(*) from public.enrollment_grade_events g where g.enrollment_id=any(enrollment_ids))
          +(select count(*) from public.learning_submission_history h join public.learning_submissions s on s.id=h.submission_id
            where s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids)),
        'events',(select count(*) from public.learning_events e where e.course_id=any(courses)),
        'progress',(select count(*) from public.learning_topic_progress t where t.topic_id=any(topics)),
        'files',(select count(*) from public.learning_content_files f where f.course_id=any(courses))+(select count(*) from public.learning_submission_files f where f.assignment_id=any(tasks) or f.enrollment_id=any(enrollment_ids)),
        'stored_files',(select count(*) from storage.objects o where o.bucket_id in ('portal-coursework','portal-content')
            and lower(split_part(o.name,'/',1))=any(courses::text[])));
    result:=jsonb_build_object('id',p_id,'kind',p_kind,'label',label,'counts',counts,
        'course_ids',to_jsonb(courses),'enrollment_ids',to_jsonb(enrollment_ids),'task_ids',to_jsonb(tasks),'topic_ids',to_jsonb(topics));
    return result||jsonb_build_object('token',md5(result::text));
end;
$$;
revoke all on function public._portal_delete_snapshot(text,uuid) from public,anon,authenticated;

create or replace function public.portal_admin_delete_preview(p_kind text,p_id uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    return public._portal_delete_snapshot(p_kind,p_id)-array['course_ids','enrollment_ids','task_ids','topic_ids'];
end;
$$;

create or replace function public.portal_admin_delete(p_kind text,p_id uuid,p_token text,p_confirmation text)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; snapshot jsonb; courses uuid[]; enrollment_ids uuid[]; tasks uuid[]; topics uuid[];
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_confirmation is distinct from 'ELIMINAR' then
        raise exception using errcode='22023',message='Escribe ELIMINAR para confirmar'; end if;
    snapshot:=public._portal_delete_snapshot(p_kind,p_id);
    if p_token is distinct from snapshot->>'token' then
        raise exception using errcode='PT409',message='Los registros cambiaron; cierra y revisa de nuevo la eliminación'; end if;
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into courses from jsonb_array_elements_text(snapshot->'course_ids') j(v);
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into enrollment_ids from jsonb_array_elements_text(snapshot->'enrollment_ids') j(v);
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into tasks from jsonb_array_elements_text(snapshot->'task_ids') j(v);
    select coalesce(array_agg(v::uuid),'{}'::uuid[]) into topics from jsonb_array_elements_text(snapshot->'topic_ids') j(v);
    -- Congelar relaciones frente a escritores de notas finales (usan estos bloqueos).
    perform e.id from public.enrollments e where e.id=any(enrollment_ids) order by e.id for update;
    perform c.id from public.course_offerings c where c.id=any(courses) order by c.id for update;
    snapshot:=public._portal_delete_snapshot(p_kind,p_id);
    if p_token is distinct from snapshot->>'token' then
        raise exception using errcode='PT409',message='Los registros cambiaron; cierra y revisa de nuevo la eliminación'; end if;
    insert into public.portal_file_cleanup(bucket_id,object_path,deleted_course_id,requested_by)
        select o.bucket_id,o.name,lower(split_part(o.name,'/',1))::uuid,actor from storage.objects o
        where o.bucket_id in ('portal-coursework','portal-content') and lower(split_part(o.name,'/',1))=any(courses::text[])
        on conflict(bucket_id,object_path) do nothing;
    -- Hijos primero. No se usa CASCADE sobre personas, Auth, otros cursos ni Storage.
    delete from public.learning_content_files f where f.course_id=any(courses);
    delete from public.learning_submission_files f where f.assignment_id=any(tasks) or f.enrollment_id=any(enrollment_ids);
    delete from public.learning_grades g where g.assignment_id=any(tasks) or g.enrollment_id=any(enrollment_ids);
    delete from public.learning_submission_history h using public.learning_submissions s
        where h.submission_id=s.id and (s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids));
    delete from public.learning_submissions s where s.assignment_id=any(tasks) or s.enrollment_id=any(enrollment_ids);
    delete from public.learning_topic_progress p where p.topic_id=any(topics);
    delete from public.learning_topics t where t.id=any(topics);
    delete from public.learning_modules m where m.course_id=any(courses);
    delete from public.learning_assignments t where t.id=any(tasks);
    delete from public.learning_course_settings s where s.course_id=any(courses);
    delete from public.learning_announcements n where n.course_id=any(courses);
    delete from public.learning_events e where e.course_id=any(courses);
    -- Conservar solo la auditoría administrativa, sin mantener el curso eliminado.
    update public.learning_audit a set details=a.details||jsonb_build_object('deleted_course_id',a.course_id),course_id=null
        where a.course_id=any(courses);
    delete from public.enrollment_grade_events g where g.enrollment_id=any(enrollment_ids);
    delete from public.enrollment_grade_drafts g where g.enrollment_id=any(enrollment_ids);
    delete from public.enrollment_grades g where g.enrollment_id=any(enrollment_ids);
    delete from public.enrollments e where e.id=any(enrollment_ids);
    delete from public.teaching_assignments t where (p_kind='subject' and t.subject_id=p_id)
        or (p_kind='period' and t.period_id=p_id) or exists(select 1 from public.course_offerings c
            where c.id=any(courses) and c.subject_id=t.subject_id and c.period_id=t.period_id);
    delete from public.course_offerings c where c.id=any(courses);
    if p_kind='subject' then delete from public.subjects s where s.id=p_id;
    elsif p_kind='period' then delete from public.academic_periods a where a.id=p_id; end if;
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,p_kind||'_delete',p_id,jsonb_build_object('label',snapshot->>'label','counts',snapshot->'counts'));
    return jsonb_build_object('id',p_id,'saved',true,'pending_files',snapshot->'counts'->'stored_files');
end;
$$;


create or replace function public.portal_admin_cleanup_files(p_ack boolean default false)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; total bigint; selected_bucket text;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._require_control_catalog_access();
    if p_ack then
        delete from public.portal_file_cleanup q where not exists(select 1 from storage.objects o
            where o.bucket_id=q.bucket_id and o.name=q.object_path);
    end if;
    select count(*) into total from public.portal_file_cleanup;
    select q.bucket_id into selected_bucket from public.portal_file_cleanup q order by q.created_at,q.bucket_id,q.object_path limit 1;
    select coalesce(jsonb_agg(r.object_path),'[]'::jsonb) into result from (
        select q.object_path from public.portal_file_cleanup q where q.bucket_id=selected_bucket
        order by q.created_at,q.object_path limit 100
    ) r;
    return jsonb_build_object('bucket_id',coalesce(selected_bucket,'portal-coursework'),'paths',result,'remaining',total);
end;
$$;
commit;
