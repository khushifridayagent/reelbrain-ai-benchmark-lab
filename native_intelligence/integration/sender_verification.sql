-- Apply after schema.sql to the NEW isolated project only.
begin;
create table public.rb_native_sender_challenges (
 recipient_id text not null, slot smallint not null check(slot between 1 and 3),
 label text not null, code_sha256 text not null unique check(code_sha256 ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz not null, consumed_at timestamptz,
 primary key(recipient_id,slot)
);
alter table public.rb_native_sender_challenges enable row level security;
revoke all on public.rb_native_sender_challenges from anon,authenticated;
grant select,insert,update on public.rb_native_sender_challenges to service_role;
create function public.rb_native_verify_sender(p_recipient text,p_sender text,p_hash text)
returns text language plpgsql security invoker set search_path='' as $$
declare c public.rb_native_sender_challenges%rowtype;
begin
 select * into c from public.rb_native_sender_challenges
 where recipient_id=p_recipient and code_sha256=p_hash and consumed_at is null and expires_at>now()
 for update;
 if not found then return 'invalid'; end if;
 if exists(select 1 from public.rb_native_senders where recipient_id=p_recipient and sender_id=p_sender) then return 'already_registered'; end if;
 insert into public.rb_native_senders(recipient_id,sender_id,label) values(p_recipient,p_sender,c.label);
 update public.rb_native_sender_challenges set consumed_at=now() where recipient_id=c.recipient_id and slot=c.slot;
 return 'verified';
end;$$;
revoke all on function public.rb_native_verify_sender(text,text,text) from public,anon,authenticated;
grant execute on function public.rb_native_verify_sender(text,text,text) to service_role;
commit;
