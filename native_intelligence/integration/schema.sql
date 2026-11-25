-- Apply ONLY to a newly created, isolated Supabase project after explicit verification.
-- Do not execute against either existing production project.
begin;
create table public.rb_native_senders (
  recipient_id text not null, sender_id text not null,
  label text not null, verified_at timestamptz not null default now(),
  enabled boolean not null default true,
  primary key(recipient_id,sender_id)
);
create table public.rb_native_inbox (
  recipient_id text not null, message_id text not null, sender_id text not null,
  received_at timestamptz not null default now(),
  payload jsonb not null check(jsonb_typeof(payload)='object'),
  primary key(recipient_id,message_id),
  foreign key(recipient_id,sender_id) references public.rb_native_senders(recipient_id,sender_id)
);
create table public.rb_native_jobs (
  id bigint generated always as identity primary key,
  recipient_id text not null, message_id text not null,
  state text not null default 'queued' check(state in ('queued','processing','partial','needs_review','reviewed','retry','dead')),
  attempts integer not null default 0 check(attempts>=0),
  next_attempt_at timestamptz not null default now(),
  lease_until timestamptz, lease_token uuid, last_error text,
  created_at timestamptz not null default now(),
  unique(recipient_id,message_id),
  foreign key(recipient_id,message_id) references public.rb_native_inbox(recipient_id,message_id)
);
create index rb_native_jobs_ready on public.rb_native_jobs(next_attempt_at,id) where state in ('queued','retry','processing');
create table public.rb_native_knowledge (
  id bigint generated always as identity primary key,
  job_id bigint not null references public.rb_native_jobs(id),
  media_sha256 text not null check(media_sha256 ~ '^[a-f0-9]{64}$'),
  asset_index integer not null check(asset_index>=0),
  evidence jsonb not null, knowledge jsonb not null default '{}'::jsonb,
  quality_state text not null check(quality_state in ('partial','needs_review','reviewed')),
  source_url text, created_at timestamptz not null default now(),
  unique(job_id,asset_index,media_sha256)
);
alter table public.rb_native_senders enable row level security;
alter table public.rb_native_inbox enable row level security;
alter table public.rb_native_jobs enable row level security;
alter table public.rb_native_knowledge enable row level security;
revoke all on public.rb_native_senders,public.rb_native_inbox,public.rb_native_jobs,public.rb_native_knowledge from anon,authenticated;
grant select,insert,update on public.rb_native_senders,public.rb_native_inbox,public.rb_native_jobs,public.rb_native_knowledge to service_role;
grant usage,select on sequence public.rb_native_jobs_id_seq,public.rb_native_knowledge_id_seq to service_role;
-- Atomic idempotent enqueue, permission enforced in the database, not just at the webhook.
create function public.rb_native_enqueue(p_recipient text,p_sender text,p_mid text,p_payload jsonb)
returns text language plpgsql security invoker set search_path='' as $$
begin
 if not exists(select 1 from public.rb_native_senders where recipient_id=p_recipient and sender_id=p_sender and enabled) then
   return 'unapproved';
 end if;
 insert into public.rb_native_inbox(recipient_id,message_id,sender_id,payload)
 values(p_recipient,p_mid,p_sender,p_payload) on conflict do nothing;
 if not found then return 'duplicate'; end if;
 insert into public.rb_native_jobs(recipient_id,message_id) values(p_recipient,p_mid);
 return 'queued';
end;$$;
revoke all on function public.rb_native_enqueue(text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.rb_native_enqueue(text,text,text,jsonb) to service_role;
-- Worker leases prevent parallel claims. Exhausted jobs require operator reconciliation.
create function public.rb_native_claim(p_lease_seconds integer default 900)
returns setof public.rb_native_jobs language sql security invoker set search_path='' as $$
  update public.rb_native_jobs j
  set state='processing',attempts=attempts+1,lease_until=now()+make_interval(secs=>greatest(60,least(p_lease_seconds,3600))),lease_token=gen_random_uuid()
  where j.id=(select x.id from public.rb_native_jobs x
    where x.attempts<5 and x.next_attempt_at<=now() and
    (x.state in ('queued','retry') or (x.state='processing' and x.lease_until<now()))
    order by x.next_attempt_at,x.id for update skip locked limit 1)
  returning j.*;
$$;
revoke all on function public.rb_native_claim(integer) from public,anon,authenticated;
grant execute on function public.rb_native_claim(integer) to service_role;
commit;
