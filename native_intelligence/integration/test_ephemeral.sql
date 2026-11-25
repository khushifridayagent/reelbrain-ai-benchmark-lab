-- Ephemeral test only, never production data.
\set ON_ERROR_STOP on
set role service_role;
insert into public.rb_native_sender_challenges(recipient_id,slot,label,code_sha256,expires_at)
values ('receiver',1,'test sender',repeat('a',64),now()+interval '5 minutes');
do $$
declare a text; j public.rb_native_jobs%rowtype; ok boolean;
begin
 a:=public.rb_native_enqueue('receiver','unknown','m0','{}');
 if a<>'unapproved' then raise exception 'allowlist failed';end if;
 a:=public.rb_native_verify_sender('receiver','sender',repeat('b',64));
 if a<>'invalid' then raise exception 'bad challenge accepted';end if;
 a:=public.rb_native_verify_sender('receiver','sender',repeat('a',64));
 if a<>'verified' then raise exception 'verification failed';end if;
 a:=public.rb_native_verify_sender('receiver','another',repeat('a',64));
 if a<>'invalid' then raise exception 'challenge replay accepted';end if;
 a:=public.rb_native_enqueue('receiver','sender','m1','{"attachments":[]}');
 if a<>'queued' then raise exception 'enqueue failed';end if;
 a:=public.rb_native_enqueue('receiver','sender','m1','{}');
 if a<>'duplicate' then raise exception 'duplicate enqueue';end if;
 select * into j from public.rb_native_claim(600);
 if not found or j.attempts<>1 or j.state<>'processing' then raise exception 'claim failed';end if;
 if exists(select 1 from public.rb_native_claim(600)) then raise exception 'duplicate lease';end if;
 ok:=public.rb_native_finish(j.id,gen_random_uuid(),'partial','[]');
 if ok then raise exception 'stale worker accepted';end if;
 ok:=public.rb_native_finish(j.id,j.lease_token,'needs_review',jsonb_build_array(jsonb_build_object('media_sha256',repeat('c',64),'asset_index',0,'evidence',jsonb_build_object('frames',1),'quality_state','needs_review')));
 if not ok then raise exception 'finish failed';end if;
 if (select count(*) from public.rb_native_knowledge where job_id=j.id)<>1 then raise exception 'evidence missing';end if;
 if (select state from public.rb_native_jobs where id=j.id)<>'needs_review' then raise exception 'wrong state';end if;
end;$$;
reset role;
do $$begin
 if has_table_privilege('anon','public.rb_native_inbox','SELECT') then raise exception 'anon can read inbox';end if;
 if has_function_privilege('authenticated','public.rb_native_enqueue(text,text,text,jsonb)','EXECUTE') then raise exception 'authenticated can enqueue';end if;
end;$$;
select 'NATIVE_DB_TEST_PASS' as result;
