# GCS Ops Runbook

## Bottom Line

- The app code is ready to store new Drive writes and migrated legacy attachments in GCS through `Drive Storage Settings`.
- Start with **one bucket plus clear prefixes**, keep **private reads signed/app-controlled**, and only use **direct public object/CDN URLs** for files that are intentionally public.
- Stale copied old `/files/...` links are still a deployment concern, not an app-code concern. Preserve them only if the web tier forwards **missing** public-file requests into Frappe.

## Recommended Starting Topology

Recommended now:

- one GCS bucket for this site/runtime profile
- one `base_prefix` per site, normally `sites/<site_name>`
- keep public and private objects separated by key prefix, not by separate buckets yet
- use canonical Drive URLs for active file consumers
- let public media use direct object/CDN URLs only when `object_url_base` or another public URL base is configured
- keep private governed reads on signed URLs or app/proxy-controlled URLs

Current object-key shapes already fit that:

- `sites/<site>/tmp/**`
- `sites/<site>/files/**`
- `sites/<site>/private/files/**`
- `sites/<site>/legacy/public/files/**`
- `sites/<site>/legacy/private/files/**`

Separate public/private buckets are still a valid later move, but they are not required for first production cutover.

## Auth Modes

### Production

Prefer:

- `credential_source = adc_or_workload_identity`

This matches the actual adapter behavior in `services/storage/gcs.py`:

- `storage.Client(project=project_id or None)` is used when the credential source is ADC / workload identity
- no service-account file path is read in that mode

### Local Dev Or Single-Server Fallback

Use:

- `credential_source = service_account_file`
- `service_account_file_path = /mounted/path/to/service-account.json`

This is the only mode where the app reads `service_account_file_path`.

## IAM Scope Required By Current Code

The current GCS adapter performs these storage operations:

- create resumable upload sessions
- upload final objects
- check object existence / metadata
- download head bytes for MIME inspection
- copy temp objects into final keys
- delete temp or source objects after finalize / abort
- generate signed read URLs when signed-url mode is active

So the workload identity or service account must be able to:

- create objects
- read object metadata and object bytes
- delete objects
- copy objects within the bucket
- generate signed read URLs when using signed-url mode

Practical guidance:

- grant bucket-level object read/write/delete capability for the Drive bucket
- if you keep `signing_mode = gcs_signed_url` or `signed_url`, verify the runtime credentials can actually sign V4 URLs in your environment

Operational caveat:

- the code defaults to signed read URLs unless one of the configured URL-base modes is used
- if workload identity in your environment cannot satisfy URL signing, do not leave that to chance in production testing
- in that case, switch to configured URL bases or a proxy-backed read path instead of assuming signed-url mode will work

## Drive Storage Settings Values

Minimal production shape:

- `enabled = 1`
- `backend_name = gcs`
- `storage_mode = gcs_for_new_writes` or `gcs_primary_with_local_fallback`
- `bucket_or_container = <bucket-name>`
- `base_prefix = sites/<site_name>`
- `credential_source = adc_or_workload_identity`
- `project_id = <gcp-project-id>` when the runtime does not already infer it cleanly

Public/private URL behavior:

- leave URL-base fields empty if you want private reads to default to signed URLs
- set `object_url_base` for public-media direct URLs or CDN URLs
- set `download_url_base` / `preview_url_base` only when you have an explicit proxy/CDN/read gateway design

Signing behavior:

- signed reads are the default when no URL bases are configured
- configured URL bases disable signed-read generation for those paths

## Suggested Rollout

1. Save `Drive Storage Settings` with GCS enabled and test the connection.
2. Start with `storage_mode = gcs_for_new_writes`.
3. Verify new governed writes land in GCS and private download/preview grants still work.
4. Run `Dry Run Attachment Offload`.
5. Queue offload jobs in batches.
6. Only enable local prune after verification is acceptable for your environment.
7. For public legacy attachments, confirm canonical rewritten URLs work before pruning local files.

## Worker Queue Topology

Preferred production setup is to define dedicated Drive workers for:

- `drive_short`
- `drive_default`
- `drive_heavy`

That preserves separation between file processing and normal ERP jobs.

Current runtime safeguard:

- `Drive Processing Job.queue_name` still stores those `drive_*` semantic classes
- if the site does not define matching custom worker queues, Drive falls back when enqueuing to Frappe's built-in `short` / `default` / `long` queues

So missing custom worker topology should no longer break governed uploads, but dedicated Drive queues remain the preferred production posture.

Recommended verification after deploy:

1. If you expect dedicated Drive workers, confirm the site runtime really exposes `drive_short`, `drive_default`, and `drive_heavy`.
2. If you do not provision them, verify the fallback path is acceptable for current load and isolation needs.
3. Run one governed upload that reaches preview/derivative scheduling and confirm the request does not fail with `Queue should be one of short, default, long`.

## Local Dev Fallback

For local development:

- mount a service-account JSON file on the box or container
- point `service_account_file_path` at that mounted path
- keep `storage_mode = gcs_for_new_writes` if you want to exercise the real adapter
- otherwise keep `storage_mode = local_only`

Do not store long-lived service-account JSON inline in site config or source-controlled files.

## Public `/files/...` Compatibility

Active `File.file_url` consumers are already covered once public legacy attachments are rewritten onto canonical remote/proxy URLs before prune.

What is still optional:

- preserving stale copied old raw `/files/...` links that hit nginx/Caddy directly before Python sees them

If that compatibility matters:

- the web tier must serve local files normally when they still exist
- but on **missing** public-file paths, it must pass the request into Frappe so the app can redirect to the canonical public URL

Do not proxy all `/files/...` traffic through Python by default.
Only misses should route through the app.

The detailed routing contract remains in:

- `11_public_file_cutover_contract.md`

## Topology Decision Notes

Current recommendation:

- one bucket now
- public/private separated by prefix now
- CDN domain optional now, valuable later
- direct object/CDN URLs only for deliberately public media
- private governed files should keep short-lived, server-authorized access

That gives the lowest-friction first deployment without forcing an early two-bucket ops split.
