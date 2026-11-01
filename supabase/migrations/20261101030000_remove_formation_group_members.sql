-- Corrección de asignaciones desde Etapas y semestres. Aplicar una vez después de group_batches.
-- Instalar no quita datos: solo crea la función que usa la confirmación del portal.
begin;
create function public.portal_formation_group_remove(p_kind text,p_period uuid,p_stage text,p_semester integer,
    p_ids uuid[],p_token text,p_confirmation text)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; ids uuid[]; target_group text; matched integer; person uuid; course uuid;
    previous public.student_formation_periods%rowtype; c public.course_offerings%rowtype;
    rev integer; result jsonb;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if upper(btrim(coalesce(p_confirmation,'')))<>'CONFIRMAR' then
        raise exception using errcode='22023',message='Escribe CONFIRMAR para quitar la asignación al grupo'; end if;
    if p_kind is null or p_kind not in ('students','classes') or p_semester is null or not exists(
        select 1 from public.formation_stages where code=p_stage and p_semester between 1 and semesters)
        or p_ids is null or coalesce(array_ndims(p_ids),0)<>1 or cardinality(p_ids) not between 1 and 500
        or array_position(p_ids,null) is not null or (p_kind='classes' and cardinality(p_ids)>100) then
        raise exception using errcode='22023',message='Selecciona seminaristas o materias de un curso válido'; end if;
    select array_agg(distinct x order by x) into ids from unnest(p_ids) x;
    perform id from public.academic_periods where id=p_period for share;
    if not found then raise exception using errcode='22023',message='Periodo no encontrado'; end if;
    perform id from public.profiles where active and role='student' order by id for share;
    perform id from public.course_offerings where period_id=p_period order by id for update;
    perform g.course_id from public.course_formation_groups g join public.course_offerings x on x.id=g.course_id
        where x.period_id=p_period order by g.course_id for update of g;
    perform student_id from public.student_formation_periods where period_id=p_period order by student_id for update;
    perform id from public.enrollments where period_id=p_period order by id for update;
    if p_token is null or p_token is distinct from (public._formation_group_snapshot(p_period)->>'token') then
        raise exception using errcode='PT409',message='El grupo o sus materias cambiaron. Cierra y actualiza antes de quitar registros.'; end if;
    target_group:=case when p_stage='introductorio' then 'CI' else ((p_semester+1)/2)::text||case when p_stage='filosofia' then 'F' else 'T' end end||'-'||p_semester;
    if p_kind='students' then
        select count(*) into matched from public.student_formation_periods f join public.profiles p on p.id=f.student_id
            where f.student_id=any(ids) and f.period_id=p_period and f.stage_code=p_stage and f.semester=p_semester
            and p.active and p.role='student';
        if matched<>cardinality(ids) then
            raise exception using errcode='22023',message='Un seminarista ya no pertenece a este curso y periodo. Actualiza.'; end if;
        foreach person in array ids loop
            select * into previous from public.student_formation_periods where student_id=person and period_id=p_period;
            -- Se retira únicamente la asignación formativa de este periodo, con auditoría del valor anterior.
            delete from public.student_formation_periods where student_id=person and period_id=p_period;
            insert into public.management_events(actor_id,action,entity_id,details) values(actor,'formation_removed',person,
                jsonb_build_object('period_id',p_period,'before_stage',previous.stage_code,'before_semester',previous.semester,
                    'before_revision',previous.revision,'before_group',target_group,'after',null,'source','formation_groups'));
        end loop;
    else
        select count(*) into matched from public.course_offerings x join public.course_formation_groups g on g.course_id=x.id
            where x.id=any(ids) and x.period_id=p_period and x.active and g.group_code=target_group;
        if matched<>cardinality(ids) then
            raise exception using errcode='22023',message='Una materia ya no pertenece a este curso y periodo. Actualiza.'; end if;
        foreach course in array ids loop
            select * into c from public.course_offerings where id=course;
            select revision into rev from public.course_formation_groups where course_id=course;
            -- Quitar la clasificación conserva la clase, sus docentes, entregas, inscripciones y notas.
            result:=public.portal_course_board_write(c.subject_id,p_period,c.id,null,rev);
            if result->>'saved' is distinct from 'true' then raise exception 'No se confirmó la corrección de la materia'; end if;
        end loop;
    end if;
    return jsonb_build_object('saved',true,'kind',p_kind,'removed',cardinality(ids),'period_id',p_period,'group_code',target_group);
end;
$$;
revoke all on function public.portal_formation_group_remove(text,uuid,text,integer,uuid[],text,text) from public,anon,authenticated;
grant execute on function public.portal_formation_group_remove(text,uuid,text,integer,uuid[],text,text) to authenticated;
notify pgrst,'reload schema';
commit;
