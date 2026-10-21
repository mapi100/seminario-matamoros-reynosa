-- Funciones exclusivamente para la Edge Function; nunca ejecutables por el navegador.
begin;
create table public.portal_invitations (
    id uuid primary key,
    actor_id uuid not null references public.profiles(id) on delete restrict,
    email text not null,
    full_name text not null,
    role text not null check(role in('student','professor','control_escolar')),
    state text not null check(state in('claimed','sent','failed','uncertain')),
    user_id uuid references auth.users(id) on delete restrict,
    created_at timestamptz not null default clock_timestamp()
);
create unique index portal_invitations_email_unique on public.portal_invitations(lower(email)) where state in('claimed','sent','uncertain');
alter table public.portal_invitations enable row level security;
revoke all on public.portal_invitations from public,anon,authenticated;

create function public.portal_prepare_invite(p_actor uuid,p_request_id uuid,p_email text,p_name text,p_role text)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare request public.portal_invitations%rowtype; normalized_email text:=lower(btrim(p_email)); normalized_name text:=btrim(p_name);
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform id from public.profiles where id=p_actor and active and role='control_escolar' for share;
    if not found then raise exception using errcode='42501',message='Acceso denegado'; end if;
    if p_request_id is null or not public._catalog_text_has_content(normalized_name) or char_length(normalized_name)>160 or normalized_name ~ '[[:cntrl:]]'
       or normalized_email is null or char_length(normalized_email)>254 or normalized_email !~ '^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}$'
       or p_role is null or p_role not in('student','professor','control_escolar') then raise exception using errcode='22023',message='Invitación inválida'; end if;
    select * into request from public.portal_invitations where id=p_request_id for update;
    if found then
        if request.actor_id<>p_actor or request.email<>normalized_email or request.full_name<>normalized_name or request.role<>p_role then
            raise exception using errcode='PT409',message='Solicitud diferente'; end if;
        return jsonb_build_object('state',case when request.state='sent' then 'sent' else 'busy' end);
    end if;
    if exists(select 1 from auth.users u where lower(u.email)=normalized_email) then raise exception using errcode='PT409',message='La cuenta ya existe'; end if;
    if (select count(*) from public.portal_invitations where actor_id=p_actor and created_at>now()-interval '10 minutes')>=20 then
        raise exception using errcode='PT429',message='Espera antes de enviar más invitaciones'; end if;
    insert into public.portal_invitations(id,actor_id,email,full_name,role,state) values(p_request_id,p_actor,normalized_email,normalized_name,p_role,'claimed');
    return jsonb_build_object('state','claimed');
exception when unique_violation then raise exception using errcode='PT409',message='Ya existe una invitación para ese correo';
end;
$$;

create function public.portal_finish_invite(p_actor uuid,p_request_id uuid,p_user_id uuid)
returns jsonb language plpgsql volatile security definer set search_path=''
as $$
declare request public.portal_invitations%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(72643219);
    perform id from public.profiles where id=p_actor and active and role='control_escolar' for share;
    if not found then raise exception using errcode='42501',message='Acceso denegado'; end if;
    select * into request from public.portal_invitations where id=p_request_id and actor_id=p_actor for update;
    if not found or request.state<>'claimed' then raise exception using errcode='PT409',message='Invitación no disponible'; end if;
    perform id from auth.users where id=p_user_id and lower(email)=request.email for share;
    if not found then raise exception using errcode='22023',message='Identidad inválida'; end if;
    insert into public.profiles(id,full_name,role,active) values(p_user_id,request.full_name,request.role,true);
    update public.portal_invitations set state='sent',user_id=p_user_id where id=request.id;
    insert into public.management_events(actor_id,action,entity_id,details) values(p_actor,'person_invited',p_user_id,jsonb_build_object('email',request.email,'role',request.role));
    return jsonb_build_object('sent',true);
end;
$$;

create function public.portal_fail_invite(p_actor uuid,p_request_id uuid,p_state text)
returns void language plpgsql volatile security definer set search_path=''
as $$
begin
    if p_state not in('failed','uncertain') or p_state is null then raise exception using errcode='22023',message='Estado inválido'; end if;
    update public.portal_invitations set state=p_state where id=p_request_id and actor_id=p_actor and state='claimed';
end;
$$;
revoke all on function public.portal_prepare_invite(uuid,uuid,text,text,text),public.portal_finish_invite(uuid,uuid,uuid),public.portal_fail_invite(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.portal_prepare_invite(uuid,uuid,text,text,text),public.portal_finish_invite(uuid,uuid,uuid),public.portal_fail_invite(uuid,uuid,text) to service_role;
commit;
