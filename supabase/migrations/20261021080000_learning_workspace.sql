-- Aula virtual: aplicar una vez después de las migraciones 600 y 700.
-- No añade datos de demostración ni modifica las calificaciones finales existentes.
begin;

create table public.learning_course_settings (
    course_id uuid primary key references public.course_offerings(id) on delete restrict,
    syllabus text not null default '' check (char_length(syllabus)<=40000),
    revision integer not null default 1 check (revision>0),
    updated_at timestamptz not null default now()
);
create table public.learning_announcements (
    id uuid primary key default gen_random_uuid(),
    course_id uuid references public.course_offerings(id) on delete restrict,
    author_id uuid not null references public.profiles(id) on delete restrict,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    body text not null check (char_length(body)<=20000),
    pinned boolean not null default false,
    published boolean not null default false,
    published_at timestamptz,
    revision integer not null default 1 check (revision>0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index learning_announcements_course_idx on public.learning_announcements(course_id,pinned desc,published_at desc,id);
create table public.learning_modules (
    id uuid primary key default gen_random_uuid(),
    course_id uuid not null references public.course_offerings(id) on delete restrict,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    position integer not null default 0 check (position between 0 and 10000),
    published boolean not null default false,
    revision integer not null default 1 check (revision>0),
    created_at timestamptz not null default now(),
    unique(id,course_id)
);
create index learning_modules_course_idx on public.learning_modules(course_id,position,id);
create table public.learning_topics (
    id uuid primary key default gen_random_uuid(),
    course_id uuid not null references public.course_offerings(id) on delete restrict,
    module_id uuid not null,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    body text not null default '' check (char_length(body)<=40000),
    url text not null default '' check (char_length(url)<=2048 and (url='' or url ~ '^https?://[^[:space:]]+$')),
    position integer not null default 0 check (position between 0 and 10000),
    published boolean not null default false,
    revision integer not null default 1 check (revision>0),
    created_at timestamptz not null default now(),
    foreign key(module_id,course_id) references public.learning_modules(id,course_id) on delete restrict
);
create index learning_topics_module_idx on public.learning_topics(module_id,position,id);
create table public.learning_topic_progress (
    topic_id uuid not null references public.learning_topics(id) on delete restrict,
    student_id uuid not null references public.profiles(id) on delete restrict,
    completed boolean not null default false,
    completed_at timestamptz,
    primary key(topic_id,student_id)
);
create table public.learning_assignments (
    id uuid primary key default gen_random_uuid(),
    course_id uuid not null references public.course_offerings(id) on delete restrict,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    instructions text not null default '' check (char_length(instructions)<=40000),
    due_at timestamptz check(due_at is null or isfinite(due_at)),
    allow_late boolean not null default true,
    published boolean not null default false,
    revision integer not null default 1 check (revision>0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index learning_assignments_course_idx on public.learning_assignments(course_id,due_at,id);
create table public.learning_submissions (
    id uuid primary key default gen_random_uuid(),
    assignment_id uuid not null references public.learning_assignments(id) on delete restrict,
    enrollment_id uuid not null references public.enrollments(id) on delete restrict,
    body text not null default '' check (char_length(body)<=40000),
    url text not null default '' check (char_length(url)<=2048 and (url='' or url ~ '^https?://[^[:space:]]+$')),
    submitted_at timestamptz not null default now(),
    late boolean not null default false,
    revision integer not null default 1 check (revision>0),
    unique(assignment_id,enrollment_id)
);
create index learning_submissions_enrollment_idx on public.learning_submissions(enrollment_id,assignment_id);
create table public.learning_submission_history (
    id uuid primary key default gen_random_uuid(),
    submission_id uuid not null references public.learning_submissions(id) on delete restrict,
    body text not null,
    url text not null,
    submitted_at timestamptz not null,
    late boolean not null,
    revision integer not null,
    replaced_at timestamptz not null default now()
);
create table public.learning_grades (
    id uuid primary key default gen_random_uuid(),
    assignment_id uuid not null references public.learning_assignments(id) on delete restrict,
    enrollment_id uuid not null references public.enrollments(id) on delete restrict,
    score numeric(5,2) not null check(score between 0 and 100),
    feedback text not null default '' check (char_length(feedback)<=12000),
    published_score numeric(5,2) check(published_score between 0 and 100),
    published_feedback text,
    published_at timestamptz,
    revision integer not null default 1 check(revision>0),
    graded_by uuid not null references public.profiles(id) on delete restrict,
    updated_at timestamptz not null default now(),
    unique(assignment_id,enrollment_id),
    check ((published_at is null and published_score is null and published_feedback is null)
        or (published_at is not null and published_score is not null and published_feedback is not null))
);
create index learning_grades_enrollment_idx on public.learning_grades(enrollment_id,assignment_id);
create table public.learning_events (
    id uuid primary key default gen_random_uuid(),
    course_id uuid references public.course_offerings(id) on delete restrict,
    title text not null check(char_length(btrim(title)) between 1 and 200),
    body text not null default '' check(char_length(body)<=12000),
    starts_at timestamptz not null check(isfinite(starts_at)),
    ends_at timestamptz check(isfinite(ends_at) and ends_at>=starts_at),
    revision integer not null default 1 check(revision>0),
    created_by uuid not null references public.profiles(id) on delete restrict,
    created_at timestamptz not null default now()
);
create index learning_events_course_idx on public.learning_events(course_id,starts_at,id);
create table public.learning_audit (
    id uuid primary key default gen_random_uuid(),
    actor_id uuid not null references public.profiles(id) on delete restrict,
    course_id uuid references public.course_offerings(id) on delete restrict,
    action text not null,
    entity_id uuid not null,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- Las tablas permanecen privadas; el navegador solo recibe proyecciones de las RPC.
alter table public.learning_course_settings enable row level security;
alter table public.learning_announcements enable row level security;
alter table public.learning_modules enable row level security;
alter table public.learning_topics enable row level security;
alter table public.learning_topic_progress enable row level security;
alter table public.learning_assignments enable row level security;
alter table public.learning_submissions enable row level security;
alter table public.learning_submission_history enable row level security;
alter table public.learning_grades enable row level security;
alter table public.learning_events enable row level security;
alter table public.learning_audit enable row level security;
revoke all on public.learning_course_settings,public.learning_announcements,public.learning_modules,
 public.learning_topics,public.learning_topic_progress,public.learning_assignments,
 public.learning_submissions,public.learning_submission_history,public.learning_grades,
 public.learning_events,public.learning_audit from public,anon,authenticated;

create function public._learning_require_actor()
returns public.profiles language plpgsql volatile security definer set search_path=''
as $$
declare person public.profiles%rowtype;
begin
    select p.* into person from public.profiles p where p.id=auth.uid() and p.active for share of p;
    if not found then raise exception using errcode='42501',message='Tu cuenta no tiene acceso al aula'; end if;
    return person;
end;
$$;
create function public._learning_can_course(p_course uuid)
returns boolean language sql stable security definer set search_path=''
as $$
    select exists(select 1 from public.course_offerings c join public.profiles p on p.id=auth.uid()
        where c.id=p_course and c.active and p.active and (
            p.role='control_escolar'
            or p.role='professor' and exists(select 1 from public.teaching_assignments t
                where t.professor_id=p.id and t.subject_id=c.subject_id and t.period_id=c.period_id and t.active)
            or p.role='student' and exists(select 1 from public.enrollments e
                where e.student_id=p.id and e.subject_id=c.subject_id and e.period_id=c.period_id and e.active)))
$$;
create function public._learning_require_course(p_course uuid,p_manage boolean default false)
returns text language plpgsql volatile security definer set search_path=''
as $$
declare person public.profiles%rowtype; course public.course_offerings%rowtype;
begin
    person:=public._learning_require_actor();
    select c.* into course from public.course_offerings c where c.id=p_course and c.active for share of c;
    if not found then raise exception using errcode='42501',message='No tienes acceso a este curso'; end if;
    if person.role='control_escolar' then return person.role; end if;
    if person.role='professor' then
        perform t.id from public.teaching_assignments t where t.professor_id=person.id
            and t.subject_id=course.subject_id and t.period_id=course.period_id and t.active for share of t;
        if found then return person.role; end if;
    elsif person.role='student' and not p_manage then
        perform e.id from public.enrollments e where e.student_id=person.id
            and e.subject_id=course.subject_id and e.period_id=course.period_id and e.active for share of e;
        if found then return person.role; end if;
    end if;
    raise exception using errcode='42501',message='No tienes permiso para esta sección del curso';
end;
$$;
-- La migración de adjuntos sustituye este helper para admitir entregas solo con archivo.
create function public._learning_has_submission_file(p_assignment uuid,p_enrollment uuid)
returns boolean language sql stable security definer set search_path=''
as $$ select false $$;
revoke all on function public._learning_require_actor(),public._learning_can_course(uuid),
 public._learning_require_course(uuid,boolean),public._learning_has_submission_file(uuid,uuid)
 from public,anon,authenticated;

create function public.portal_learning_read(p_resource text,p_course uuid default null,p_offset integer default 0,p_limit integer default 30)
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
                    select t.id,t.title,t.body,t.url,t.position,t.published,t.revision,coalesce(x.completed,false) as completed
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

create function public.portal_learning_write(p_action text,p_course uuid,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare person public.profiles%rowtype; course public.course_offerings%rowtype; actor_role text;
    entity uuid; target uuid; parent uuid; enrollment uuid; expected integer; current_revision integer; saved_revision integer;
    title_value text; body_value text; url_value text; published_value boolean; position_value integer; score_value numeric;
    due_value timestamptz; starts_value timestamptz; ends_value timestamptz; allow_late_value boolean; target_table text;
    task public.learning_assignments%rowtype; submission public.learning_submissions%rowtype; grade public.learning_grades%rowtype;
begin
    -- Orden compartido con Control Escolar: las bajas y las escrituras se serializan.
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    person:=public._learning_require_actor();
    if p_data is null or jsonb_typeof(p_data)<>'object' then raise exception using errcode='22023',message='Datos inválidos'; end if;
    if p_action is null or p_action not in ('syllabus_save','announcement_save','module_save','topic_save','assignment_save','event_save','grade_save','grade_publish','grade_unpublish','topic_complete','submit') then
        raise exception using errcode='22023',message='Acción inválida'; end if;
    if p_course is null then
        if person.role<>'control_escolar' or p_action not in ('announcement_save','event_save') then
            raise exception using errcode='42501',message='Solo Control Escolar publica información institucional'; end if;
        actor_role:=person.role;
    else
        actor_role:=public._learning_require_course(p_course,p_action not in ('topic_complete','submit'));
        select c.* into course from public.course_offerings c where c.id=p_course;
    end if;
    if p_action in ('topic_complete','submit') and actor_role<>'student' then
        raise exception using errcode='42501',message='Esta acción corresponde al alumno inscrito'; end if;
    target:=nullif(p_data->>'id','')::uuid;
    expected:=coalesce((p_data->>'revision')::integer,0);
    if expected<0 then raise exception using errcode='22023',message='Revisión inválida'; end if;
    if target is not null and p_action in ('announcement_save','module_save','topic_save','assignment_save','event_save') then
        target_table:=case p_action when 'announcement_save' then 'learning_announcements' when 'module_save' then 'learning_modules'
            when 'topic_save' then 'learning_topics' when 'assignment_save' then 'learning_assignments' else 'learning_events' end;
        execute pg_catalog.format('select revision from public.%I where id=$1 and course_id is not distinct from $2 for update',target_table)
            into current_revision using target,p_course;
        if current_revision is null then raise exception using errcode='42501',message='El elemento no pertenece a este espacio'; end if;
        if current_revision<>expected then raise exception using errcode='PT409',message='El elemento cambió; actualiza antes de guardar'; end if;
    end if;
    title_value:=btrim(coalesce(p_data->>'title',''));
    body_value:=coalesce(p_data->>'body',''); url_value:=btrim(coalesce(p_data->>'url',''));
    if p_action in ('announcement_save','module_save','topic_save','assignment_save','event_save') then
        if not public._catalog_text_has_content(title_value) or char_length(title_value)>200 then
            raise exception using errcode='22023',message='Escribe un título de hasta 200 caracteres'; end if;
    end if;
    if p_action in ('announcement_save','module_save','topic_save','assignment_save') then
        if p_data ? 'published' and jsonb_typeof(p_data->'published')<>'boolean' then raise exception using errcode='22023',message='Estado de publicación inválido'; end if;
        published_value:=coalesce((p_data->>'published')::boolean,false);
    end if;
    if p_action in ('topic_save','submit') then
        if char_length(url_value)>2048 or (url_value<>'' and url_value !~ '^https?://[^[:space:]]+$') then
            raise exception using errcode='22023',message='Usa un enlace http o https válido'; end if;
    end if;
    if p_action='syllabus_save' then
        if char_length(body_value)>40000 then raise exception using errcode='22023',message='El programa es demasiado largo'; end if;
        insert into public.learning_course_settings(course_id,syllabus) values(p_course,body_value)
        on conflict(course_id) do update set syllabus=excluded.syllabus,revision=public.learning_course_settings.revision+1,updated_at=now()
        returning course_id,revision into entity,saved_revision;
    elsif p_action='announcement_save' then
        if char_length(body_value)>20000 or (p_data ? 'pinned' and jsonb_typeof(p_data->'pinned')<>'boolean') then raise exception using errcode='22023',message='Anuncio inválido'; end if;
        if target is null then
            if (select count(*) from public.learning_announcements n where n.course_id is not distinct from p_course)>=200 then raise exception using errcode='22023',message='Se alcanzó el límite de anuncios de este espacio'; end if;
            insert into public.learning_announcements(course_id,author_id,title,body,pinned,published,published_at)
                values(p_course,person.id,title_value,body_value,coalesce((p_data->>'pinned')::boolean,false),published_value,case when published_value then now() else null end)
                returning id,revision into entity,saved_revision;
        else
            update public.learning_announcements n set title=title_value,body=body_value,pinned=coalesce((p_data->>'pinned')::boolean,false),published=published_value,
                published_at=case when published_value then coalesce(n.published_at,now()) else null end,revision=n.revision+1,updated_at=now()
                where n.id=target and n.course_id is not distinct from p_course and n.revision=expected returning id,revision into entity,saved_revision;
            if not found then raise exception using errcode='PT409',message='El anuncio cambió; actualiza antes de guardar'; end if;
        end if;
    elsif p_action='module_save' then
        if p_data ? 'position' and jsonb_typeof(p_data->'position')<>'number' then raise exception using errcode='22023',message='Orden inválido'; end if;
        position_value:=coalesce((p_data->>'position')::integer,0);
        if position_value not between 0 and 10000 then raise exception using errcode='22023',message='Orden inválido'; end if;
        if target is null then
            if (select count(*) from public.learning_modules m where m.course_id=p_course)>=50 then raise exception using errcode='22023',message='Se alcanzó el límite de unidades del curso'; end if;
            insert into public.learning_modules(course_id,title,position,published) values(p_course,title_value,position_value,published_value) returning id,revision into entity,saved_revision;
        else
            update public.learning_modules m set title=title_value,position=position_value,published=published_value,revision=m.revision+1
                where m.id=target and m.course_id=p_course and m.revision=expected returning id,revision into entity,saved_revision;
            if not found then raise exception using errcode='PT409',message='La unidad cambió; actualiza antes de guardar'; end if;
        end if;
    elsif p_action='topic_save' then
        if p_data ? 'position' and jsonb_typeof(p_data->'position')<>'number' then raise exception using errcode='22023',message='Orden inválido'; end if;
        parent:=(p_data->>'module_id')::uuid; position_value:=coalesce((p_data->>'position')::integer,0);
        perform m.id from public.learning_modules m where m.id=parent and m.course_id=p_course for share of m;
        if not found then raise exception using errcode='42501',message='La unidad no pertenece al curso'; end if;
        if char_length(body_value)>40000 or position_value not between 0 and 10000 then raise exception using errcode='22023',message='Contenido inválido'; end if;
        if target is null then
            if (select count(*) from public.learning_topics t where t.course_id=p_course)>=250 then raise exception using errcode='22023',message='Se alcanzó el límite de temas del curso'; end if;
            insert into public.learning_topics(course_id,module_id,title,body,url,position,published) values(p_course,parent,title_value,body_value,url_value,position_value,published_value) returning id,revision into entity,saved_revision;
        else
            update public.learning_topics t set module_id=parent,title=title_value,body=body_value,url=url_value,position=position_value,published=published_value,revision=t.revision+1
                where t.id=target and t.course_id=p_course and t.revision=expected returning id,revision into entity,saved_revision;
            if not found then raise exception using errcode='PT409',message='El tema cambió; actualiza antes de guardar'; end if;
        end if;
    elsif p_action='assignment_save' then
        body_value:=coalesce(p_data->>'instructions',''); due_value:=nullif(p_data->>'due_at','')::timestamptz;
        if char_length(body_value)>40000 or (due_value is not null and not isfinite(due_value)) or (p_data ? 'allow_late' and jsonb_typeof(p_data->'allow_late')<>'boolean') then raise exception using errcode='22023',message='Tarea inválida'; end if;
        allow_late_value:=coalesce((p_data->>'allow_late')::boolean,true);
        if target is null then
            if (select count(*) from public.learning_assignments a where a.course_id=p_course)>=100 then raise exception using errcode='22023',message='Se alcanzó el límite de tareas del curso'; end if;
            insert into public.learning_assignments(course_id,title,instructions,due_at,allow_late,published) values(p_course,title_value,body_value,due_value,allow_late_value,published_value) returning id,revision into entity,saved_revision;
        else
            update public.learning_assignments t set title=title_value,instructions=body_value,due_at=due_value,allow_late=allow_late_value,published=published_value,revision=t.revision+1,updated_at=now()
                where t.id=target and t.course_id=p_course and t.revision=expected returning id,revision into entity,saved_revision;
            if not found then raise exception using errcode='PT409',message='La tarea cambió; actualiza antes de guardar'; end if;
        end if;
    elsif p_action='event_save' then
        starts_value:=(p_data->>'starts_at')::timestamptz; ends_value:=nullif(p_data->>'ends_at','')::timestamptz;
        if starts_value is null or not isfinite(starts_value) or ends_value is not null and (not isfinite(ends_value) or ends_value<starts_value) or char_length(body_value)>12000 then raise exception using errcode='22023',message='Fechas o descripción del evento inválidas'; end if;
        if target is null then
            if (select count(*) from public.learning_events e where e.course_id is not distinct from p_course)>=200 then raise exception using errcode='22023',message='Se alcanzó el límite de eventos de este espacio'; end if;
            insert into public.learning_events(course_id,title,body,starts_at,ends_at,created_by) values(p_course,title_value,body_value,starts_value,ends_value,person.id) returning id,revision into entity,saved_revision;
        else
            update public.learning_events e set title=title_value,body=body_value,starts_at=starts_value,ends_at=ends_value,revision=e.revision+1
                where e.id=target and e.course_id is not distinct from p_course and e.revision=expected returning id,revision into entity,saved_revision;
            if not found then raise exception using errcode='PT409',message='El evento cambió; actualiza antes de guardar'; end if;
        end if;
    elsif p_action='topic_complete' then
        entity:=(p_data->>'topic_id')::uuid;
        perform t.id from public.learning_topics t join public.learning_modules m on m.id=t.module_id
            where t.id=entity and t.course_id=p_course and t.published and m.published for share of t,m;
        if not found then raise exception using errcode='42501',message='No tienes acceso a este tema'; end if;
        if jsonb_typeof(p_data->'completed') is distinct from 'boolean' then raise exception using errcode='22023',message='Progreso inválido'; end if;
        insert into public.learning_topic_progress(topic_id,student_id,completed,completed_at) values(entity,person.id,(p_data->>'completed')::boolean,case when (p_data->>'completed')::boolean then now() else null end)
            on conflict(topic_id,student_id) do update set completed=excluded.completed,completed_at=excluded.completed_at;
    elsif p_action='submit' then
        parent:=(p_data->>'assignment_id')::uuid;
        select a.* into task from public.learning_assignments a where a.id=parent and a.course_id=p_course and a.published for share of a;
        if not found then raise exception using errcode='42501',message='No tienes acceso a esta tarea'; end if;
        select e.id into enrollment from public.enrollments e where e.student_id=person.id and e.subject_id=course.subject_id and e.period_id=course.period_id and e.active for share of e;
        if not found then raise exception using errcode='42501',message='Tu inscripción no está activa'; end if;
        if task.due_at<clock_timestamp() and not task.allow_late then raise exception using errcode='22023',message='La fecha límite de entrega ya pasó'; end if;
        if char_length(body_value)>40000 or (not public._catalog_text_has_content(body_value) and url_value='' and not public._learning_has_submission_file(parent,enrollment)) then raise exception using errcode='22023',message='Escribe tu entrega, agrega un enlace o adjunta un archivo'; end if;
        select x.* into submission from public.learning_submissions x where x.assignment_id=parent and x.enrollment_id=enrollment for update of x;
        if found then
            insert into public.learning_submission_history(submission_id,body,url,submitted_at,late,revision) values(submission.id,submission.body,submission.url,submission.submitted_at,submission.late,submission.revision);
            update public.learning_submissions x set body=body_value,url=url_value,submitted_at=clock_timestamp(),late=coalesce(task.due_at<clock_timestamp(),false),revision=x.revision+1
                where x.id=submission.id returning id,revision into entity,saved_revision;
        else
            insert into public.learning_submissions(assignment_id,enrollment_id,body,url,late,submitted_at) values(parent,enrollment,body_value,url_value,coalesce(task.due_at<clock_timestamp(),false),clock_timestamp()) returning id,revision into entity,saved_revision;
        end if;
    else
        parent:=(p_data->>'assignment_id')::uuid; enrollment:=(p_data->>'enrollment_id')::uuid;
        perform a.id from public.learning_assignments a where a.id=parent and a.course_id=p_course for share of a;
        if not found then raise exception using errcode='42501',message='La tarea no pertenece al curso'; end if;
        perform e.id from public.enrollments e join public.profiles p on p.id=e.student_id
            where e.id=enrollment and e.subject_id=course.subject_id and e.period_id=course.period_id and e.active and p.active and p.role='student' for share of e,p;
        if not found then raise exception using errcode='42501',message='El alumno no tiene una inscripción activa en el curso'; end if;
        select g.* into grade from public.learning_grades g where g.assignment_id=parent and g.enrollment_id=enrollment for update of g;
        current_revision:=case when found then grade.revision else 0 end;
        if current_revision<>expected then raise exception using errcode='PT409',message='La calificación cambió; actualiza antes de guardar'; end if;
        if p_action='grade_save' then
            score_value:=(p_data->>'score')::numeric; body_value:=coalesce(p_data->>'feedback','');
            if score_value is null or score_value not between 0 and 100 or scale(score_value)>2 or char_length(body_value)>12000 then raise exception using errcode='22023',message='La nota debe estar entre 0 y 100, con hasta dos decimales'; end if;
            insert into public.learning_grades(assignment_id,enrollment_id,score,feedback,graded_by) values(parent,enrollment,score_value,body_value,person.id)
                on conflict(assignment_id,enrollment_id) do update set score=excluded.score,feedback=excluded.feedback,graded_by=excluded.graded_by,updated_at=now(),revision=public.learning_grades.revision+1
                returning id,revision into entity,saved_revision;
        elsif current_revision=0 then raise exception using errcode='22023',message='Guarda primero una calificación';
        elsif p_action='grade_publish' then
            update public.learning_grades g set published_score=g.score,published_feedback=g.feedback,published_at=now(),graded_by=person.id,revision=g.revision+1,updated_at=now() where g.id=grade.id returning id,revision into entity,saved_revision;
        else
            update public.learning_grades g set published_score=null,published_feedback=null,published_at=null,graded_by=person.id,revision=g.revision+1,updated_at=now() where g.id=grade.id returning id,revision into entity,saved_revision;
        end if;
    end if;
    insert into public.learning_audit(actor_id,course_id,action,entity_id,details) values(person.id,p_course,p_action,entity,jsonb_build_object('revision',saved_revision));
    return jsonb_build_object('id',entity,'saved',true,'revision',saved_revision);
exception
    when invalid_text_representation or datetime_field_overflow or invalid_datetime_format or numeric_value_out_of_range then
        raise exception using errcode='22023',message='Revisa los datos y las fechas del formulario';
end;
$$;
revoke all on function public.portal_learning_read(text,uuid,integer,integer),public.portal_learning_write(text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.portal_learning_read(text,uuid,integer,integer),public.portal_learning_write(text,uuid,jsonb) to authenticated;
commit;
