-- Aplicar una vez después de 20261023000000_formation_stages.sql.
-- No cambia notas finales, actividades ni criterios de cursos existentes.
begin;

alter table public.learning_assignments
    add column grading_category text check(grading_category in ('tasks','exams','projects','participation','practice')),
    add column requires_submission boolean not null default true;
create table public.learning_grading_schemes (
    course_id uuid primary key references public.course_offerings(id) on delete cascade,
    draft jsonb, published jsonb, revision integer not null default 1,
    updated_by uuid not null references public.profiles(id), updated_at timestamptz not null default now()
);
create table public.learning_grade_exemptions (
    assignment_id uuid references public.learning_assignments(id) on delete cascade,
    enrollment_id uuid references public.enrollments(id) on delete cascade,
    reason text not null check(char_length(btrim(reason)) between 5 and 1000),
    actor_id uuid not null references public.profiles(id),
    primary key(assignment_id,enrollment_id)
);
create table public.learning_final_calculations (
    enrollment_id uuid primary key references public.enrollments(id) on delete cascade,
    snapshot jsonb not null, reason text not null default '',
    actor_id uuid not null references public.profiles(id), created_at timestamptz not null default now()
);
alter table public.learning_grading_schemes enable row level security;
alter table public.learning_grade_exemptions enable row level security;
alter table public.learning_final_calculations enable row level security;
revoke all on public.learning_grading_schemes,public.learning_grade_exemptions,public.learning_final_calculations from public,anon,authenticated;

-- Devuelve problemas concretos; un borrador incompleto se puede guardar.
create function public._grading_validate(p_course uuid,p_schema jsonb)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare errors jsonb:='[]'; cat jsonb; it jsonb; total numeric:=0; amount numeric; n integer; code text; caption text;
begin
    if p_schema is null or jsonb_typeof(p_schema)<>'object'
       or jsonb_typeof(p_schema->'categories') is distinct from 'array'
       or jsonb_typeof(p_schema->'items') is distinct from 'array' then
        return jsonb_build_array('Configura las cuatro categorías y sus actividades.'); end if;
    if jsonb_array_length(p_schema->'categories')<>4 or jsonb_array_length(p_schema->'items')>100 then
        return jsonb_build_array('Se requieren cuatro categorías y hasta 100 actividades.'); end if;
    foreach code in array array['tasks','exams','projects','participation'] loop
        select count(*) into n from jsonb_array_elements(p_schema->'categories') x where x->>'code'=code;
        if n<>1 then return jsonb_build_array('Cada categoría debe aparecer una sola vez.'); end if;
    end loop;
    for cat in select * from jsonb_array_elements(p_schema->'categories') loop
        if jsonb_typeof(cat->'weight') is distinct from 'number' or cat->>'mode' not in ('equal','custom') or cat->>'mode' is null then
            return jsonb_build_array('Introduce porcentajes numéricos y una forma de reparto válida.'); end if;
        caption:=case cat->>'code' when 'tasks' then 'Tareas' when 'exams' then 'Exámenes' when 'projects' then 'Proyectos' else 'Participación' end;
        amount:=(cat->>'weight')::numeric;
        if amount<0 or amount>100 or amount<>round(amount,2) then return jsonb_build_array('Los porcentajes deben estar entre 0 y 100, con hasta dos decimales.'); end if;
        total:=total+amount;
        if amount>0 then
            select count(*) into n from jsonb_array_elements(p_schema->'items') x where x->>'category'=cat->>'code';
            if n=0 then errors:=errors||jsonb_build_array('Agrega actividades a la categoría '||caption||' o déjala en 0 %.'); end if;
            if cat->>'mode'='custom' and (select coalesce(sum((x->>'share')::numeric),0) from jsonb_array_elements(p_schema->'items') x where x->>'category'=cat->>'code')<>100 then
                errors:=errors||jsonb_build_array('El reparto personalizado de '||caption||' debe sumar 100 %.'); end if;
        end if;
    end loop;
    if total<>100 then errors:=errors||jsonb_build_array('Las cuatro categorías deben sumar 100 %.'); end if;
    if (select count(distinct x->>'id') from jsonb_array_elements(p_schema->'items') x)<>jsonb_array_length(p_schema->'items') then
        return errors||jsonb_build_array('Hay actividades duplicadas.'); end if;
    for it in select * from jsonb_array_elements(p_schema->'items') loop
        if it->>'category' is null or it->>'category' not in ('tasks','exams','projects','participation','practice')
           or not exists(select 1 from public.learning_assignments a where a.course_id=p_course and a.id=(it->>'id')::uuid) then
            return errors||jsonb_build_array('Selecciona una categoría para cada actividad de esta clase.'); end if;
        if jsonb_typeof(it->'share') is distinct from 'number' or (it->>'share')::numeric<=0
           or (it->>'share')::numeric>100 or (it->>'share')::numeric<>round((it->>'share')::numeric,2) then
            return errors||jsonb_build_array('El peso de cada actividad debe ser mayor que 0 y hasta 100.'); end if;
    end loop;
    if exists(select 1 from public.learning_assignments a where a.course_id=p_course and not exists(
        select 1 from jsonb_array_elements(p_schema->'items') x where x->>'id'=a.id::text)) then
        errors:=errors||jsonb_build_array('Clasifica todas las actividades; usa Práctica para las que no cuentan.'); end if;
    return errors;
exception when invalid_text_representation or numeric_value_out_of_range then
    return jsonb_build_array('Revisa los porcentajes y las actividades seleccionadas.');
end;
$$;

-- Único cálculo autoritativo. Primero se normaliza cada categoría después de
-- exenciones; luego se renormaliza solo el peso evaluado para el promedio actual.
create function public._grading_calculate(p_course uuid,p_enrollment uuid,p_drafts boolean default false)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare scheme jsonb; cat jsonb; it jsonb; a public.learning_assignments%rowtype; g public.learning_grades%rowtype;
    categories jsonb:='[]'; items jsonb:='[]'; reasons jsonb:='[]'; errors jsonb;
    denominator numeric; units numeric; weight numeric; value numeric; covered numeric:=0; earned numeric:=0;
    cat_covered numeric; cat_earned numeric; pending integer:=0; unpublished integer:=0; exempt boolean; result jsonb;
begin
    select published into scheme from public.learning_grading_schemes where course_id=p_course;
    if scheme is null then return jsonb_build_object('configured',false,'average',null,'coverage',0,'categories','[]'::jsonb,'items','[]'::jsonb,'ready',false,
        'token',md5(coalesce((select jsonb_agg(to_jsonb(gg) order by gg.id)::text from public.learning_grades gg join public.learning_assignments aa on aa.id=gg.assignment_id where aa.course_id=p_course and gg.enrollment_id=p_enrollment),'')
            ||coalesce((select jsonb_agg(to_jsonb(ee) order by ee.assignment_id)::text from public.learning_grade_exemptions ee where ee.enrollment_id=p_enrollment),'')),
        'reasons',jsonb_build_array('El profesor todavía no ha publicado los criterios de evaluación.')); end if;
    errors:=public._grading_validate(p_course,scheme);
    if jsonb_array_length(errors)>0 then reasons:=reasons||errors; end if;
    for cat in select * from jsonb_array_elements(scheme->'categories') loop
        cat_covered:=0; cat_earned:=0;
        select coalesce(sum(case when cat->>'mode'='equal' then 1 else (x->>'share')::numeric end),0)
            into denominator from jsonb_array_elements(scheme->'items') x
            where x->>'category'=cat->>'code' and not exists(select 1 from public.learning_grade_exemptions e
                where e.assignment_id=(x->>'id')::uuid and e.enrollment_id=p_enrollment);
        if (cat->>'weight')::numeric>0 and denominator=0 then reasons:=reasons||jsonb_build_array('Hay una categoría con peso sin actividades evaluables para este alumno.'); end if;
        for it in select * from jsonb_array_elements(scheme->'items') x where x->>'category'=cat->>'code' loop
            select * into a from public.learning_assignments where id=(it->>'id')::uuid and course_id=p_course;
            select * into g from public.learning_grades where assignment_id=a.id and enrollment_id=p_enrollment;
            exempt:=exists(select 1 from public.learning_grade_exemptions where assignment_id=a.id and enrollment_id=p_enrollment);
            units:=case when cat->>'mode'='equal' then 1 else (it->>'share')::numeric end;
            weight:=case when exempt or denominator=0 then 0 else (cat->>'weight')::numeric*units/denominator end;
            value:=case when a.published and not exempt then case when p_drafts then g.score else g.published_score end end;
            if weight>0 then
                if value is null then pending:=pending+1;
                else cat_covered:=cat_covered+weight; cat_earned:=cat_earned+value*weight; end if;
                if g.score is distinct from g.published_score or g.feedback is distinct from g.published_feedback then
                    if g.id is not null then unpublished:=unpublished+1; end if;
                end if;
            end if;
            items:=items||jsonb_build_array(jsonb_build_object('id',a.id,'category',cat->>'code','weight',round(weight,4),'exempt',exempt,'score',value));
        end loop;
        categories:=categories||jsonb_build_array(jsonb_build_object('code',cat->>'code','weight',(cat->>'weight')::numeric,
            'average',round(cat_earned/nullif(cat_covered,0),2),'coverage',round(cat_covered,4),'contribution',round(cat_earned/100,4)));
        covered:=covered+cat_covered; earned:=earned+cat_earned;
    end loop;
    if pending>0 then reasons:=reasons||jsonb_build_array(pending||' actividades sin calificación publicada o sin publicar.'); end if;
    if unpublished>0 then reasons:=reasons||jsonb_build_array(unpublished||' notas con cambios pendientes de publicación.'); end if;
    result:=jsonb_build_object('configured',true,'average',round(earned/nullif(covered,0),2),'coverage',round(covered,2),
        'categories',categories,'items',items,'pending',pending,'unpublished',unpublished,
        'ready',jsonb_array_length(reasons)=0 and abs(covered-100)<0.000001,'reasons',reasons);
    -- Incluye borradores para detectar también cambios privados entre revisión y publicación.
    return result||jsonb_build_object('token',md5(result::text||scheme::text||coalesce((select jsonb_agg(to_jsonb(gg) order by gg.id)::text
        from public.learning_grades gg join public.learning_assignments aa on aa.id=gg.assignment_id where aa.course_id=p_course and gg.enrollment_id=p_enrollment),'')
        ||coalesce((select jsonb_agg(to_jsonb(e) order by e.assignment_id)::text from public.learning_grade_exemptions e where e.enrollment_id=p_enrollment),'')
        ||coalesce((select to_jsonb(f)::text from public.enrollment_grades f where f.enrollment_id=p_enrollment),'')));
end;
$$;

alter function public.portal_learning_read(text,uuid,integer,integer) rename to _learning_read_before_weights;
alter function public.portal_learning_write(text,uuid,jsonb) rename to _learning_write_before_weights;

create function public.portal_learning_read(p_resource text,p_course uuid default null,p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb;
begin
    result:=public._learning_read_before_weights(p_resource,p_course,p_offset,p_limit);
    if p_resource='course' then
        result:=jsonb_set(result,'{assignments}',(select coalesce(jsonb_agg(x||jsonb_build_object('grading_category',a.grading_category,'requires_submission',a.requires_submission)),'[]'::jsonb)
            from jsonb_array_elements(result->'assignments') x join public.learning_assignments a on a.id=(x->>'id')::uuid));
    end if;
    return result;
end;
$$;
create function public.portal_learning_write(p_action text,p_course uuid,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare result jsonb; category text;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    if p_action='submit' and exists(select 1 from public.learning_assignments where id=(p_data->>'assignment_id')::uuid and course_id=p_course and not requires_submission) then
        perform public._learning_require_course(p_course,false);
        raise exception using errcode='22023',message='Esta evaluación se registra directamente por el profesor; no requiere entrega.'; end if;
    result:=public._learning_write_before_weights(p_action,p_course,p_data);
    if p_action='assignment_save' then
        category:=p_data->>'grading_category';
        if p_data ? 'grading_category' and category is not null and category not in ('tasks','exams','projects','participation','practice') then
            raise exception using errcode='22023',message='Categoría inválida'; end if;
        if p_data ? 'requires_submission' and jsonb_typeof(p_data->'requires_submission')<>'boolean' then
            raise exception using errcode='22023',message='Indica si esta actividad requiere entrega'; end if;
        update public.learning_assignments set grading_category=case when p_data ? 'grading_category' then category else grading_category end,
            requires_submission=coalesce((p_data->>'requires_submission')::boolean,requires_submission) where id=(result->>'id')::uuid;
    end if;
    return result;
end;
$$;

create function public.portal_gradebook_read(p_course uuid,p_resource text default 'book',p_offset integer default 0,p_limit integer default 30)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare role_name text; scheme public.learning_grading_schemes%rowtype; result jsonb; rows jsonb; eid uuid; calculation jsonb;
begin
    perform pg_catalog.pg_advisory_xact_lock_shared(72643219);
    role_name:=public._learning_require_course(p_course,p_resource<>'own');
    if p_resource is null or p_resource not in ('book','own') or p_offset is null or p_offset<0 or p_offset>100000
        or p_limit is null or p_limit not between 1 and 100 then raise exception using errcode='22023',message='Consulta inválida'; end if;
    select * into scheme from public.learning_grading_schemes where course_id=p_course;
    if p_resource='own' then
        if role_name<>'student' then raise exception using errcode='42501',message='Consulta exclusiva del alumno'; end if;
        select e.id into eid from public.enrollments e join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
            where c.id=p_course and e.student_id=auth.uid() and e.active;
        calculation:=public._grading_calculate(p_course,eid)-array['token','ready','reasons','unpublished'];
        calculation:=jsonb_set(calculation,'{items}',(select coalesce(jsonb_agg(x),'[]'::jsonb) from jsonb_array_elements(calculation->'items') x
            join public.learning_assignments a on a.id=(x->>'id')::uuid where a.course_id=p_course and a.published));
        -- Nunca devuelve el borrador del esquema ni revela las notas privadas.
        return jsonb_build_object('summary',calculation,'categories',coalesce(scheme.published->'categories','[]'::jsonb),
            'assignments',(select coalesce(jsonb_agg(jsonb_build_object('id',a.id,'title',a.title,'requires_submission',a.requires_submission,
                'submitted',exists(select 1 from public.learning_submissions x where x.assignment_id=a.id and x.enrollment_id=eid),
                'score',g.published_score,'feedback',g.published_feedback,'exempt',x.assignment_id is not null,
                'category',(select i->>'category' from jsonb_array_elements(scheme.published->'items') i where i->>'id'=a.id::text))), '[]'::jsonb)
                from public.learning_assignments a left join public.learning_grades g on g.assignment_id=a.id and g.enrollment_id=eid
                left join public.learning_grade_exemptions x on x.assignment_id=a.id and x.enrollment_id=eid where a.course_id=p_course and a.published),
            'final_score',(select score from public.enrollment_grades where enrollment_id=eid and published));
    end if;
    result:=public._learning_read_before_weights('gradebook',p_course,p_offset,p_limit);
    select coalesce(jsonb_agg(x||jsonb_build_object('summary',public._grading_calculate(p_course,(x->>'enrollment_id')::uuid),
        'draft_summary',public._grading_calculate(p_course,(x->>'enrollment_id')::uuid,true),
        'exemptions',(select coalesce(jsonb_agg(jsonb_build_object('id',e.assignment_id,'reason',e.reason)),'[]'::jsonb) from public.learning_grade_exemptions e where e.enrollment_id=(x->>'enrollment_id')::uuid))), '[]'::jsonb)
        into rows from jsonb_array_elements(result->'students') x;
    return result||jsonb_build_object('students',rows,'revision',coalesce(scheme.revision,0),'draft',scheme.draft,'published',scheme.published,
        'errors',public._grading_validate(p_course,scheme.draft),
        'assignments',(select coalesce(jsonb_agg(jsonb_build_object('id',a.id,'title',a.title,'due_at',a.due_at,'published',a.published,
            'grading_category',a.grading_category,'requires_submission',a.requires_submission) order by a.created_at,a.id),'[]'::jsonb) from public.learning_assignments a where a.course_id=p_course));
end;
$$;

create function public.portal_gradebook_write(p_course uuid,p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path='' as $$
declare role_name text; scheme public.learning_grading_schemes%rowtype; errors jsonb; eid uuid; aid uuid; result jsonb;
    row_data jsonb; calculation jsonb; previous_score numeric; new_score numeric; reason text; current_revision integer;
    snapshot jsonb;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    role_name:=public._learning_require_course(p_course,true);
    if p_data is null or jsonb_typeof(p_data)<>'object' then raise exception using errcode='22023',message='Datos inválidos'; end if;
    reason:=btrim(coalesce(p_data->>'reason',''));
    if char_length(reason)>1000 then raise exception using errcode='22023',message='El motivo es demasiado largo'; end if;
    select * into scheme from public.learning_grading_schemes where course_id=p_course for update;
    if p_action in ('scheme_save','scheme_publish') then
        if (p_data->>'revision')::integer is distinct from coalesce(scheme.revision,0) then
            raise exception using errcode='PT409',message='Los criterios cambiaron. Actualiza el libro antes de continuar.'; end if;
        if jsonb_typeof(p_data->'schema') is distinct from 'object' or octet_length((p_data->'schema')::text)>60000 then
            raise exception using errcode='22023',message='Configuración inválida'; end if;
        errors:=public._grading_validate(p_course,p_data->'schema');
        if p_action='scheme_publish' then
            if jsonb_array_length(errors)>0 then raise exception using errcode='22023',message='Completa la configuración: '||(errors->>0); end if;
            if scheme.draft is distinct from p_data->'schema' then raise exception using errcode='PT409',message='Primero guarda y revisa este borrador.'; end if;
            if p_data->>'confirmed' is distinct from 'true' then raise exception using errcode='22023',message='Confirma la publicación de los criterios.'; end if;
            if scheme.published is not null and scheme.published is distinct from scheme.draft and char_length(reason)<10 then
                raise exception using errcode='22023',message='Explica el cambio de criterios con al menos 10 caracteres.'; end if;
        end if;
        insert into public.learning_grading_schemes(course_id,draft,published,revision,updated_by)
            values(p_course,p_data->'schema',case when p_action='scheme_publish' then p_data->'schema' end,1,auth.uid())
        on conflict(course_id) do update set draft=excluded.draft,
            published=case when p_action='scheme_publish' then excluded.published else public.learning_grading_schemes.published end,
            revision=public.learning_grading_schemes.revision+1,updated_by=auth.uid(),updated_at=now();
        result:=jsonb_build_object('saved',true,'id',p_course,'errors',errors);
    elsif p_action='assessments_save' then
        if jsonb_typeof(p_data->'items') is distinct from 'array' or jsonb_array_length(p_data->'items') not between 1 and 300 then
            raise exception using errcode='22023',message='Guarda entre 1 y 300 cambios por operación.'; end if;
        if (select count(distinct (x->>'enrollment_id',x->>'assignment_id')) from jsonb_array_elements(p_data->'items') x)<>jsonb_array_length(p_data->'items') then
            raise exception using errcode='22023',message='Hay evaluaciones duplicadas.'; end if;
        -- Se revisan TODOS los tokens antes de escribir. Todo el lote se confirma
        -- en una transacción; nunca queda guardada una mitad de la cuadrícula.
        for row_data in select * from jsonb_array_elements(p_data->'items') loop
            eid:=(row_data->>'enrollment_id')::uuid;
            calculation:=public._grading_calculate(p_course,eid);
            if row_data->>'token' is distinct from calculation->>'token' then
                raise exception using errcode='PT409',message='El libro cambió; actualiza antes de guardar el lote.'; end if;
        end loop;
        for row_data in select * from jsonb_array_elements(p_data->'items') loop
            calculation:=public._grading_calculate(p_course,(row_data->>'enrollment_id')::uuid);
            result:=public.portal_gradebook_write(p_course,'assessment_save',row_data||jsonb_build_object('token',calculation->'token','exempt',false,'publish',p_data->'publish'));
        end loop;
        result:=jsonb_build_object('saved',true,'id',p_course);
    elsif p_action in ('assessment_save','assessment_unpublish') then
        eid:=(p_data->>'enrollment_id')::uuid; aid:=(p_data->>'assignment_id')::uuid;
        perform e.id from public.enrollments e join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
            join public.profiles p on p.id=e.student_id where e.id=eid and c.id=p_course and e.active and p.active and p.role='student' for update of e;
        if not found or not exists(select 1 from public.learning_assignments where id=aid and course_id=p_course) then
            raise exception using errcode='42501',message='La evaluación no pertenece a este alumno y clase'; end if;
        calculation:=public._grading_calculate(p_course,eid);
        if p_data->>'token' is distinct from calculation->>'token' then
            raise exception using errcode='PT409',message='Las notas cambiaron; actualiza antes de guardar.'; end if;
        if p_action='assessment_unpublish' then
            result:=public.portal_learning_write('grade_unpublish',p_course,p_data);
        elsif p_data->>'exempt'='true' then
            if char_length(reason)<5 then raise exception using errcode='22023',message='Escribe el motivo de la exención.'; end if;
            insert into public.learning_grade_exemptions values(aid,eid,reason,auth.uid())
                on conflict(assignment_id,enrollment_id) do update set reason=excluded.reason,actor_id=excluded.actor_id;
        else
            delete from public.learning_grade_exemptions where assignment_id=aid and enrollment_id=eid;
            result:=public.portal_learning_write('grade_save',p_course,p_data);
            if p_data->>'publish'='true' then
                result:=public.portal_learning_write('grade_publish',p_course,p_data||jsonb_build_object('revision',result->'revision')); end if;
        end if;
        result:=jsonb_build_object('saved',true,'id',aid);
    elsif p_action='final_publish' then
        if p_data->>'confirmed' is distinct from 'true' or jsonb_typeof(p_data->'students') is distinct from 'array'
            or jsonb_array_length(p_data->'students') not between 1 and 100 then raise exception using errcode='22023',message='Selecciona alumnos y confirma las notas finales.'; end if;
        if (select count(distinct x->>'id') from jsonb_array_elements(p_data->'students') x)<>jsonb_array_length(p_data->'students') then
            raise exception using errcode='22023',message='Hay alumnos duplicados.'; end if;
        for row_data in select * from jsonb_array_elements(p_data->'students') loop
            eid:=(row_data->>'id')::uuid;
            perform e.id from public.enrollments e join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
                join public.profiles p on p.id=e.student_id where e.id=eid and c.id=p_course and e.active and p.active and p.role='student' for update of e;
            if not found then raise exception using errcode='42501',message='Alumno fuera de esta clase'; end if;
            calculation:=public._grading_calculate(p_course,eid);
            if row_data->>'token' is distinct from calculation->>'token' then raise exception using errcode='PT409',message='El cálculo cambió; vuelve a revisar las notas finales.'; end if;
            if not coalesce((calculation->>'ready')::boolean,false) then raise exception using errcode='22023',message='Hay evaluaciones o criterios pendientes. Resuélvelos antes de publicar finales.'; end if;
            new_score:=coalesce((row_data->>'override')::numeric,(calculation->>'average')::numeric);
            select score into previous_score from public.enrollment_grades where enrollment_id=eid and published;
            if new_score is null or new_score not between 0 and 100 or new_score<>round(new_score,2) then raise exception using errcode='22023',message='La nota final debe estar entre 0 y 100 con dos decimales.'; end if;
            if (new_score<>(calculation->>'average')::numeric or previous_score is not null and previous_score<>new_score) and char_length(reason)<10 then
                raise exception using errcode='22023',message='Explica el ajuste o corrección de la nota final con al menos 10 caracteres.'; end if;
            select coalesce(revision,0) into current_revision from public.enrollment_grade_drafts where enrollment_id=eid for update;
            current_revision:=coalesce(current_revision,0)+1;
            snapshot:=jsonb_build_object('calculation',calculation,'schema',scheme.published,'score',new_score,
                'activities',(select jsonb_agg(jsonb_build_object('id',a.id,'title',a.title) order by a.id) from public.learning_assignments a where a.course_id=p_course));
            insert into public.learning_final_calculations values(eid,snapshot,reason,auth.uid(),now()) on conflict(enrollment_id) do update
                set snapshot=excluded.snapshot,reason=excluded.reason,actor_id=excluded.actor_id,created_at=excluded.created_at;
            insert into public.enrollment_grades(enrollment_id,score,published) values(eid,new_score,true) on conflict(enrollment_id) do update set score=excluded.score,published=true;
            insert into public.enrollment_grade_drafts(enrollment_id,score,revision,needs_publication,updated_by) values(eid,new_score,current_revision,false,auth.uid())
                on conflict(enrollment_id) do update set score=excluded.score,revision=excluded.revision,needs_publication=false,updated_by=excluded.updated_by,updated_at=now();
            insert into public.enrollment_grade_events(enrollment_id,actor_id,assignment_id,action,old_published_score,score,revision)
                values(eid,auth.uid(),p_course,'publish',previous_score,new_score,current_revision);
            insert into public.learning_audit(actor_id,course_id,action,entity_id,details) values(auth.uid(),p_course,'weighted_final_publish',eid,
                jsonb_build_object('before',previous_score,'after',snapshot,'reason',reason));
        end loop;
        result:=jsonb_build_object('saved',true,'id',p_course);
    else raise exception using errcode='22023',message='Acción inválida'; end if;
    if p_action<>'final_publish' then
        insert into public.learning_audit(actor_id,course_id,action,entity_id,details) values(auth.uid(),p_course,p_action,
            coalesce(aid,p_course),p_data-'token'); end if;
    return result;
exception when invalid_text_representation or numeric_value_out_of_range then raise exception using errcode='22023',message='Revisa las calificaciones, porcentajes y actividades.';
end;
$$;

-- El editor antiguo sigue disponible para cursos sin ponderaciones. Con esquema
-- publicado, las finales pasan por la revisión del libro y el historial de cálculo.
alter function public.publish_teaching_grade(uuid,uuid,integer) rename to _publish_grade_before_weights;
alter function public.save_teaching_grade(uuid,uuid,numeric,integer) rename to _save_grade_before_weights;
create function public.save_teaching_grade(p_assignment_id uuid,p_enrollment_id uuid,p_score numeric,p_expected_revision integer)
returns table(enrollment_id uuid,published_score numeric,draft_score numeric,revision integer,has_unpublished_changes boolean)
language plpgsql volatile security definer set search_path='' as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._lock_teaching_grade(p_assignment_id,p_enrollment_id);
    if exists(select 1 from public.enrollments e join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
        join public.learning_grading_schemes s on s.course_id=c.id where e.id=p_enrollment_id and s.published is not null) then
        raise exception using errcode='22023',message='Usa Calificaciones del curso para revisar el cálculo ponderado de la nota final.'; end if;
    return query select * from public._save_grade_before_weights(p_assignment_id,p_enrollment_id,p_score,p_expected_revision);
end;
$$;
create function public.publish_teaching_grade(p_assignment_id uuid,p_enrollment_id uuid,p_expected_revision integer)
returns table(enrollment_id uuid,published_score numeric,draft_score numeric,revision integer,has_unpublished_changes boolean)
language plpgsql volatile security definer set search_path='' as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform public._lock_teaching_grade(p_assignment_id,p_enrollment_id);
    if exists(select 1 from public.enrollments e join public.course_offerings c on c.subject_id=e.subject_id and c.period_id=e.period_id
        join public.learning_grading_schemes s on s.course_id=c.id where e.id=p_enrollment_id and s.published is not null) then
        raise exception using errcode='22023',message='Publica la nota final desde Calificaciones del curso para revisar su cálculo.'; end if;
    return query select * from public._publish_grade_before_weights(p_assignment_id,p_enrollment_id,p_expected_revision);
end;
$$;

revoke all on function public._grading_validate(uuid,jsonb),public._grading_calculate(uuid,uuid,boolean),
    public._learning_read_before_weights(text,uuid,integer,integer),public._learning_write_before_weights(text,uuid,jsonb),
    public._publish_grade_before_weights(uuid,uuid,integer),public._save_grade_before_weights(uuid,uuid,numeric,integer),public.portal_learning_read(text,uuid,integer,integer),
    public.portal_learning_write(text,uuid,jsonb),public.portal_gradebook_read(uuid,text,integer,integer),public.portal_gradebook_write(uuid,text,jsonb),
    public.publish_teaching_grade(uuid,uuid,integer),public.save_teaching_grade(uuid,uuid,numeric,integer) from public,anon,authenticated;
grant execute on function public.portal_learning_read(text,uuid,integer,integer),public.portal_learning_write(text,uuid,jsonb),
    public.portal_gradebook_read(uuid,text,integer,integer),public.portal_gradebook_write(uuid,text,jsonb),public.publish_teaching_grade(uuid,uuid,integer),public.save_teaching_grade(uuid,uuid,numeric,integer) to authenticated;
commit;
