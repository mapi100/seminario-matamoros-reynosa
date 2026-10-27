-- NUEVO: revisar dependencias y respaldo antes de aplicar. No ejecutado en producción.
-- Contrato de notas existente: 0–100. No divide ni modifica calificaciones.
begin;

alter table public.kardex_institution add column prefect_name text;

-- Criterio institucional confirmado: 7.0/10. Las emisiones históricas no cambian.
update public.kardex_programs set pass_mark=70,display_scale='10',revision=revision+1
where pass_mark is distinct from 70 or display_scale<>'10';
alter table public.kardex_programs alter column display_scale set default '10';
alter table public.kardex_programs alter column pass_mark set default 70;
alter function public.portal_kardex_write(text,jsonb) rename to _kardex_write_before_report_cards;
create function public.portal_kardex_write(p_action text,p_data jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; prefect text;
begin
    perform public._require_control_catalog_access();
    if p_action='program_save' then p_data:=p_data||jsonb_build_object('pass_mark',70,'display_scale','10'); end if;
    if p_action='institution_save' and p_data ? 'prefect_name' then prefect:=public._kardex_text(p_data->>'prefect_name',160); end if;
    result:=public._kardex_write_before_report_cards(p_action,p_data);
    if p_action='institution_save' and p_data ? 'prefect_name' then update public.kardex_institution set prefect_name=prefect where id; end if;
    return result;
end;
$$;
alter function public._kardex_record(uuid,uuid) rename to _kardex_record_before_report_cards;
create function public._kardex_record(p_student uuid,p_program uuid default null)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb;
begin
    result:=jsonb_set(public._kardex_record_before_report_cards(p_student,p_program)-'token','{method,display_scale}','"10"');
    result:=jsonb_set(result,'{method,decimals}','1');
    return result||jsonb_build_object('token',md5(result::text));
end;
$$;

create sequence public.report_card_folio_seq;
create table public.report_card_issues (
    id uuid primary key,
    student_id uuid not null references public.profiles(id) on delete restrict,
    -- Sin FK al periodo: la copia sobrevive al borrado explícito de una clase/periodo.
    period_id uuid not null,
    issued_by uuid not null references public.profiles(id) on delete restrict,
    folio text not null unique,
    request_hash text not null,
    snapshot jsonb not null check(jsonb_typeof(snapshot)='object'),
    issued_at timestamptz not null default now()
);
create index report_card_student_idx on public.report_card_issues(student_id,issued_at desc,id);
alter table public.report_card_issues enable row level security;
revoke all on public.report_card_issues,public.report_card_folio_seq from public,anon,authenticated;

create function public._report_card_preview(p_student uuid,p_period uuid,p_options jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare record jsonb; formation jsonb; period public.academic_periods%rowtype;
    rows jsonb; result jsonb; reasons jsonb:='[]'; cycle text; rector text; prefect text;
    start_year integer; item jsonb;
begin
    if p_options is null or jsonb_typeof(p_options)<>'object' then raise exception using errcode='22023',message='Opciones inválidas'; end if;
    select * into period from public.academic_periods where id=p_period;
    if not found then raise exception using errcode='22023',message='Selecciona un periodo académico válido'; end if;
    record:=public._kardex_record(p_student,null);
    select f into formation from jsonb_array_elements(record->'formation_history') f where (f->>'period_id')::uuid=p_period;
    start_year:=extract(year from period.starts_on)::integer-case when extract(month from period.starts_on)<8 then 1 else 0 end;
    cycle:=public._kardex_text(coalesce(p_options->>'cycle',start_year::text||'-'||(start_year+1)::text),9);
    if cycle is null or cycle !~ '^[0-9]{4}-[0-9]{4}$' or right(cycle,4)::integer<>left(cycle,4)::integer+1 then
        raise exception using errcode='22023',message='El ciclo debe contener dos años consecutivos: 2025-2026'; end if;
    rector:=public._kardex_text(coalesce(p_options->>'rector_name',record->'institution'->>'rector_name'),160);
    prefect:=public._kardex_text(coalesce(p_options->>'prefect_name',record->'institution'->>'prefect_name'),160);
    select coalesce(jsonb_agg(jsonb_build_object('enrollment_id',r->'enrollment_id','code',r->'code','name',r->'name',
        'source_score',r->'score','score',round((r->>'score')::numeric/10,1)) order by r->>'code',r->>'enrollment_id'),'[]')
    into rows from jsonb_array_elements(record->'rows') r where (r->>'period_id')::uuid=p_period;
    if jsonb_array_length(rows)=0 then reasons:=reasons||jsonb_build_array('No hay materias inscritas en este periodo.'); end if;
    if record->'student'->>'student_number' is null then reasons:=reasons||jsonb_build_array('Registra la matrícula del alumno en Datos del alumno.'); end if;
    if formation is null then reasons:=reasons||jsonb_build_array('Asigna la etapa y el semestre del alumno para este periodo.'); end if;
    if rector is null or prefect is null then reasons:=reasons||jsonb_build_array('Completa los nombres del Rector y del Prefecto de Estudios.'); end if;
    for item in select * from jsonb_array_elements(rows) loop
        if item->>'score' is null then reasons:=reasons||jsonb_build_array('Falta publicar la calificación final de '||(item->>'name')||'.');
        elsif (item->>'source_score')::numeric<70 and (item->>'score')::numeric>=7 then
            reasons:=reasons||jsonb_build_array('Revisa la calificación final de '||(item->>'name')||': su redondeo cruza la mínima aprobatoria.');
        end if;
    end loop;
    result:=jsonb_build_object('version',1,'scale',10,'decimals',1,'pass_mark',7,
        'institution',jsonb_build_object('name','SEMINARIO DE MATAMOROS-REYNOSA'),
        'student',jsonb_build_object('id',record->'student'->'id','full_name',record->'student'->'full_name','student_number',record->'student'->'student_number'),
        'period',jsonb_build_object('id',period.id,'name',period.name,'starts_on',period.starts_on,'ends_on',period.ends_on),
        'formation',formation,'cycle',cycle,'rector_name',rector,'prefect_name',prefect,'rows',rows,
        'ready',jsonb_array_length(reasons)=0,'reasons',reasons);
    -- Incluye el token del expediente: una modificación concurrente obliga a revisar.
    return result||jsonb_build_object('token',md5(result::text||(record->>'token')));
end;
$$;

create function public.portal_report_card_read(p_resource text,p_student uuid default null,p_period uuid default null,
    p_options jsonb default '{}',p_issue uuid default null,p_offset integer default 0)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare result jsonb; more boolean;
begin
    perform public._require_control_catalog_access();
    if p_resource='preview' then return public._report_card_preview(p_student,p_period,p_options);
    elsif p_resource='issues' then
        if p_student is null or p_offset is null or p_offset<0 or p_offset>100000 then raise exception using errcode='22023',message='Consulta inválida'; end if;
        select coalesce(jsonb_agg(to_jsonb(i) order by i.issued_at desc,i.id),'[]') into result from
            (select id,folio,issued_at,snapshot->'period'->>'name' as period_name from public.report_card_issues
             where student_id=p_student order by issued_at desc,id offset p_offset limit 30) i;
        select exists(select 1 from public.report_card_issues where student_id=p_student offset p_offset+30) into more;
        return jsonb_build_object('items',result,'has_more',more);
    elsif p_resource='issue' then
        select to_jsonb(i)-'request_hash'-'issued_by' into result from public.report_card_issues i where id=p_issue;
        if result is null then raise exception using errcode='22023',message='Boleta no encontrada'; end if;
        return result;
    end if;
    raise exception using errcode='22023',message='Consulta de boleta inválida';
end;
$$;

create function public.portal_report_card_issue(p_student uuid,p_period uuid,p_options jsonb,p_token text,p_request_id uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare actor uuid; preview jsonb; fingerprint text; existing public.report_card_issues%rowtype; folio_value text; n text;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    actor:=public._require_control_catalog_access();
    if p_request_id is null then raise exception using errcode='22023',message='Solicitud inválida'; end if;
    fingerprint:=md5(jsonb_build_object('student',p_student,'period',p_period,'options',p_options,'token',p_token)::text);
    select * into existing from public.report_card_issues where id=p_request_id;
    if found then
        if existing.issued_by<>actor or existing.request_hash<>fingerprint then raise exception using errcode='PT409',message='Esta solicitud ya fue utilizada para otro documento'; end if;
        return jsonb_build_object('saved',true,'id',existing.id,'folio',existing.folio);
    end if;
    perform e.id from public.enrollments e where e.student_id=p_student order by e.id for share;
    preview:=public._report_card_preview(p_student,p_period,p_options);
    if p_token is distinct from preview->>'token' then raise exception using errcode='PT409',message='Los datos cambiaron. Actualiza y revisa la vista previa antes de emitir.'; end if;
    if not (preview->>'ready')::boolean then raise exception using errcode='22023',message='Completa los requisitos indicados en la boleta antes de emitir.'; end if;
    n:=nextval('public.report_card_folio_seq')::text;
    folio_value:='BOL-'||to_char(current_date,'YYYY')||'-'||lpad(n,greatest(6,length(n)),'0');
    insert into public.report_card_issues(id,student_id,period_id,issued_by,folio,request_hash,snapshot)
        values(p_request_id,p_student,p_period,actor,folio_value,fingerprint,preview);
    insert into public.management_events(actor_id,action,entity_id,details)
        values(actor,'report_card_issue',p_request_id,jsonb_build_object('folio',folio_value));
    return jsonb_build_object('saved',true,'id',p_request_id,'folio',folio_value);
end;
$$;
revoke all on function public._kardex_write_before_report_cards(text,jsonb),public._kardex_record_before_report_cards(uuid,uuid),
    public._kardex_record(uuid,uuid),public._report_card_preview(uuid,uuid,jsonb),public.portal_kardex_write(text,jsonb),
    public.portal_report_card_read(text,uuid,uuid,jsonb,uuid,integer),public.portal_report_card_issue(uuid,uuid,jsonb,text,uuid)
    from public,anon,authenticated;
grant execute on function public.portal_kardex_write(text,jsonb),public.portal_report_card_read(text,uuid,uuid,jsonb,uuid,integer),
    public.portal_report_card_issue(uuid,uuid,jsonb,text,uuid) to authenticated;
commit;
