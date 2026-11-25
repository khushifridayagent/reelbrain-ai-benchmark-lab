# Native intelligence — isolated implementation status

This module is a separate experimental pipeline. Never deploy or migrate against the original ReelBrain or GTA VI project.

## Verified
- Native frame scanning uses full color byte equality, not approximate visual hashing, to reuse OCR.
- OCR retains original text and zoomed regional evidence; no automatic URL correction.
- Hybrid runner calls Gemini 3.5 Flash-Lite, Groq Whisper Turbo, and optionally targeted Qwen.
- The 90-frame synthetic integration test recovered the exact URL from frame 13 at 433.3333 ms, and all three API calls succeeded.
- The report is always pending semantic review, even when processing succeeded.

## Configuration for an independent deployment
1. Provision an eligible NEW Supabase project. Never pause or modify either existing project.
2. Apply schema.sql, sender_verification.sql, finish.sql in this order; verify RLS, privileges and the project reference.
3. Deploy a separate Meta app/receiver where possible, with new webhook callback; no changes to existing Meta callbacks.
4. For the webhook set RB_NATIVE_PROJECT_REF, META_APP_SECRET, META_WEBHOOK_VERIFY_TOKEN, META_IG_ACCOUNT_ID in the NEW project. Built-in Supabase service credentials must point to that project. For Instagram Login, authorize instagram_business_basic and instagram_business_manage_messages; keep the access token in the new project's secrets. No publishing permission required.
5. Generate three cryptographically random one-time challenge strings, store only their SHA-256 hashes with slot/label and expiry. Send each challenge from its intended sender to the new receiver. Confirm the resulting sender IDs and revoke any unexpected sender.
6. Production worker connection, media retrieval from authorized Meta attachments, persistent checkpoint/restart, bounded concurrency, rate limiting, storage retention, semantic validation and actual DM end-to-end tests still require integration. Do not enable schedules yet.

## Storage policy (proposed)
Original media and decoded frames are temporary during processing. Retain exact textual evidence, source identifiers, timestamps, verification state and selective original-resolution crops. Full reports can be compressed and retained selectively; never silently discard unresolved evidence. Set an object budget and backpressure before exceeding the quota. Keep private DM data out of this public test repo and public logs. A full all-native-frame real-media runtime and report-size benchmark is still required.

No production database writes or live Meta callback deployment were performed.
