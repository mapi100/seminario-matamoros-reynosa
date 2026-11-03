-- Archivos privados del expediente: hasta 10 PDF de 5 MiB por seminarista.
-- Aplicar una vez. Instalar no modifica expedientes ni buckets anteriores.
begin;
create table public.student_record_files (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.profiles(id) on delete restrict,
    kind text not null check(kind in ('bautismo','comunion','confirmacion','otros_sacramentos','preparatoria','titulo_universitario','otros_estudios','seguro_medico','otro')),
    name text not null check(char_length(name) between 1 and 160 and name ~* '\.pdf$' and name !~ '[[:cntrl:]]' and strpos(name,'/')=0 and strpos(name,chr(92))=0),
    size bigint not null check(size between 1 and 5242880),
    object_path text not null unique,
    state text not null default 'pending' check(state in ('pending','ready','deleting')),
    uploaded_by uuid not null references public.profiles(id) on delete restrict,
    created_at timestamptz not null default now(),
    check(object_path=student_id::text||'/'||id::text||'.pdf')
);
create index student_record_files_student_idx on public.student_record_files(student_id,created_at,id);
alter table public.student_record_files enable row level security;
revoke all on public.student_record_files from public,anon,authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('portal-personal','portal-personal',false,5242880,array['application/pdf']);

-- Storage solo recibe una proyección booleana; la autorización usa el rol real activo.
create function public._student_file_authorized(p_path text,p_action text)
returns boolean language plpgsql volatile security definer set search_path=''
as $$
declare parts text[]; target uuid; item uuid; f public.student_record_files%rowtype;
begin
    if p_path is null or char_length(p_path)>120 or p_action is null or p_action not in ('read','insert','delete') then return false; end if;
    parts:=string_to_array(p_path,'/');
    if cardinality(parts)<>2 or parts[2] !~ '^[0-9a-f-]{36}\.pdf$' then return false; end if;
    target:=parts[1]::uuid; item:=left(parts[2],36)::uuid;
    if p_path<>target::text||'/'||item::text||'.pdf' then return false; end if;
    perform public._student_record_target(target);
    select * into f from public.student_record_files where id=item and student_id=target and object_path=p_path for share;
    if not found then return false; end if;
    if p_action='read' then return true; end if;
    if p_action='insert' then return f.state='pending' and f.uploaded_by=auth.uid(); end if;
    return f.state='deleting';
exception when invalid_text_representation or insufficient_privilege or invalid_parameter_value then return false;
end;
$$;
revoke all on function public._student_file_authorized(text,text) from public,anon,authenticated;
grant execute on function public._student_file_authorized(text,text) to authenticated;
create policy "Personal files private read" on storage.objects for select to authenticated
    using(bucket_id='portal-personal' and public._student_file_authorized(name,'read'));
create policy "Personal files reserved upload" on storage.objects for insert to authenticated
    with check(bucket_id='portal-personal' and owner_id=auth.uid()::text and public._student_file_authorized(name,'insert'));
create policy "Personal files confirmed removal" on storage.objects for delete to authenticated
    using(bucket_id='portal-personal' and public._student_file_authorized(name,'delete'));
-- No UPDATE: no se permite sobrescribir documentos por Storage/upsert.
-- Guardas restrictivas: una política permisiva genérica preexistente no puede
-- abrir este bucket. Fuera de portal-personal no cambian el acceso existente.
create policy "Personal files restricted read" on storage.objects as restrictive for select to authenticated
    using(bucket_id is distinct from 'portal-personal' or case when auth.role()='authenticated'
        then public._student_file_authorized(name,'read') else false end);
create policy "Personal files restricted insert" on storage.objects as restrictive for insert to authenticated
    with check(bucket_id is distinct from 'portal-personal' or case when auth.role()='authenticated'
        then owner_id=auth.uid()::text and public._student_file_authorized(name,'insert') else false end);
create policy "Personal files never overwrite" on storage.objects as restrictive for update to authenticated
    using(bucket_id is distinct from 'portal-personal') with check(bucket_id is distinct from 'portal-personal');
create policy "Personal files restricted delete" on storage.objects as restrictive for delete to authenticated
    using(bucket_id is distinct from 'portal-personal' or case when auth.role()='authenticated'
        then public._student_file_authorized(name,'delete') else false end);

create policy "Personal files deny anonymous" on storage.objects as restrictive for all to anon
    using(bucket_id is distinct from 'portal-personal') with check(bucket_id is distinct from 'portal-personal');

create function public.portal_student_files(p_action text,p_student uuid default null,p_data jsonb default '{}'::jsonb)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare target uuid; actor uuid:=auth.uid(); f public.student_record_files%rowtype;
    obj storage.objects%rowtype; file_id uuid; file_name text; file_kind text; file_size bigint; rows jsonb;
begin
    if p_action is null or p_action not in ('list','reserve','complete','remove','release') or p_data is null or jsonb_typeof(p_data)<>'object' then
        raise exception using errcode='22023',message='Solicitud de archivos inválida'; end if;
    if p_action<>'list' then perform pg_catalog.pg_advisory_xact_lock(72643219); end if;
    target:=public._student_record_target(p_student);
    if p_action='list' then
        if p_data<>'{}'::jsonb then raise exception using errcode='22023',message='Consulta de archivos inválida'; end if;
        select coalesce(jsonb_agg(to_jsonb(x) order by x.created_at,x.id),'[]'::jsonb) into rows from public.student_record_files x where student_id=target;
        return jsonb_build_object('student_id',target,'items',rows,'max_files',10,'max_size',5242880);
    elsif p_action='reserve' then
        if (p_data-'name'-'size'-'kind')<>'{}'::jsonb or jsonb_typeof(p_data->'name') is distinct from 'string'
            or jsonb_typeof(p_data->'kind') is distinct from 'string' or jsonb_typeof(p_data->'size') is distinct from 'number'
            or (p_data->>'size') !~ '^[0-9]{1,7}$' then raise exception using errcode='22023',message='Selecciona un PDF válido de hasta 5 MB'; end if;
        file_name:=btrim(p_data->>'name'); file_kind:=p_data->>'kind'; file_size:=(p_data->>'size')::bigint;
        if file_size not between 1 and 5242880 or char_length(file_name) not between 1 and 160 or file_name !~* '\.pdf$'
            or file_name ~ '[[:cntrl:]]' or strpos(file_name,'/')>0 or strpos(file_name,chr(92))>0
            or file_kind not in ('bautismo','comunion','confirmacion','otros_sacramentos','preparatoria','titulo_universitario','otros_estudios','seguro_medico','otro') then
            raise exception using errcode='22023',message='Selecciona el tipo de documento y un PDF de hasta 5 MB'; end if;
        -- Las reservas incompletas también ocupan un lugar: el límite es autoritativo y cubre concurrencia.
        if (select count(*) from public.student_record_files where student_id=target)>=10 then
            raise exception using errcode='22023',message='Ya hay 10 archivos o cargas pendientes. Quita uno o limpia una carga incompleta.'; end if;
        file_id:=gen_random_uuid();
        insert into public.student_record_files(id,student_id,kind,name,size,object_path,uploaded_by)
            values(file_id,target,file_kind,file_name,file_size,target::text||'/'||file_id::text||'.pdf',actor) returning * into f;
        return jsonb_build_object('saved',true,'item',to_jsonb(f));
    end if;
    if (p_data-'id')<>'{}'::jsonb or jsonb_typeof(p_data->'id') is distinct from 'string' then
        raise exception using errcode='22023',message='Selecciona un archivo del expediente'; end if;
    file_id:=(p_data->>'id')::uuid;
    select * into f from public.student_record_files where id=file_id and student_id=target for update;
    if not found then
        if p_action in ('remove','release') then return jsonb_build_object('saved',true,'removed',true,'id',file_id); end if;
        raise exception using errcode='22023',message='Archivo no encontrado en este expediente';
    end if;
    if p_action='complete' then
        if f.state='deleting' then raise exception using errcode='PT409',message='La carga se está retirando. Actualiza los archivos.'; end if;
        if f.uploaded_by<>actor then raise exception using errcode='42501',message='Solo quien inició la carga puede confirmarla'; end if;
        select * into obj from storage.objects where bucket_id='portal-personal' and name=f.object_path;
        if not found or obj.owner_id is distinct from f.uploaded_by::text or obj.metadata->>'mimetype' is distinct from 'application/pdf'
            or coalesce(obj.metadata->>'size','') !~ '^[0-9]{1,7}$' then
            raise exception using errcode='22023',message='El PDF todavía no está almacenado correctamente. Actualiza o limpia la carga.'; end if;
        if (obj.metadata->>'size')::bigint<>f.size then raise exception using errcode='22023',message='El tamaño almacenado no coincide con el PDF'; end if;
        if f.state<>'ready' then
            update public.student_record_files set state='ready' where id=f.id returning * into f;
            insert into public.management_events(actor_id,action,entity_id,details) values(actor,'student_file_uploaded',target,
                jsonb_build_object('file_id',f.id,'kind',f.kind));
        end if;
        return jsonb_build_object('saved',true,'item',to_jsonb(f));
    elsif p_action='remove' then
        update public.student_record_files set state='deleting' where id=f.id returning * into f;
        return jsonb_build_object('saved',true,'item',to_jsonb(f));
    end if;
    if f.state<>'deleting' or exists(select 1 from storage.objects where bucket_id='portal-personal' and name=f.object_path) then
        raise exception using errcode='PT409',message='Primero confirma la eliminación del archivo almacenado. Actualiza antes de repetir.'; end if;
    delete from public.student_record_files where id=f.id;
    insert into public.management_events(actor_id,action,entity_id,details) values(actor,'student_file_removed',target,
        jsonb_build_object('file_id',f.id,'kind',f.kind));
    return jsonb_build_object('saved',true,'removed',true,'id',f.id);
exception when invalid_text_representation or numeric_value_out_of_range or check_violation then
    raise exception using errcode='22023',message='Revisa el tipo de documento, el nombre y el tamaño del PDF';
end;
$$;
revoke all on function public.portal_student_files(text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.portal_student_files(text,uuid,jsonb) to authenticated;
notify pgrst,'reload schema';
commit;
