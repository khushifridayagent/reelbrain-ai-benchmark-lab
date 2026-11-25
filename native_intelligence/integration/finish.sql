-- Lease-bound evidence commit: apply after schema.sql to a NEW project.
begin;
create function public.rb_native_finish(
 p_job bigint,p_lease uuid,p_state text,p_assets jsonb,p_error text default null
) returns boolean language plpgsql security invoker set search_path='' as $$
declare j public.rb_native_jobs%rowtype; a jsonb;
begin
 if p_state not in ('partial','needs_review','retry','dead') then
   raise exception 'invalid_worker_state';
 end if;
 if jsonb_typeof(p_assets) <> 'array' then raise exception 'assets_not_array';end if;
 select * into j from public.rb_native_jobs
 where id=p_job and state='processing' and lease_token=p_lease and lease_until>now()
 for update;
 if not found then return false;end if;
 if p_state='needs_review' and jsonb_array_length(p_assets)=0 then raise exception 'missing_evidence';end if;
 for a in select value from jsonb_array_elements(p_assets) loop
   if a->>'quality_state' not in ('partial','needs_review') then raise exception 'unreviewed_asset';end if;
   insert into public.rb_native_knowledge(job_id,media_sha256,asset_index,evidence,knowledge,quality_state,source_url)
   values(p_job,a->>'media_sha256',(a->>'asset_index')::integer,a->'evidence',coalesce(a->'knowledge','{}'::jsonb),a->>'quality_state',a->>'source_url')
   on conflict(job_id,asset_index,media_sha256) do update
   set evidence=excluded.evidence,knowledge=excluded.knowledge,quality_state=excluded.quality_state;
 end loop;
 update public.rb_native_jobs set state=case when p_state='retry' and attempts>=5 then 'dead' else p_state end,
 lease_token=null,lease_until=null,last_error=left(p_error,200),next_attempt_at=now()+make_interval(secs=>least(3600,60*attempts*attempts))
 where id=p_job;
 return true;
end;$$;
revoke all on function public.rb_native_finish(bigint,uuid,text,jsonb,text) from public,anon,authenticated;
grant execute on function public.rb_native_finish(bigint,uuid,text,jsonb,text) to service_role;
commit;
