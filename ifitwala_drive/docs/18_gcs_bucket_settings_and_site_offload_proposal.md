# GCS Bucket Settings and Site Attachment Offload Proposal

## Status

Proposed working design for the next storage slice.

## Bottom Line

- Add one operator-only Single DocType to manage the runtime storage profile for this site.
- Use that settings page to move new `ifitwala_drive` writes to Google Cloud Storage first.
- Treat existing `sites/<site>/public/files` and `sites/<site>/private/files` content as a separate background migration, not as an immediate side effect of saving settings.
- Do not treat the whole `sites/<site>` folder as Drive storage. Only attachment roots should be offloaded.

## Why This Fits The Current Code

The repo already has the important lower layers:

- `services/storage/base.py` already resolves a runtime storage profile with `backend_name`, `bucket_or_container`, `base_prefix`, `credential_source`, and URL fields.
- `services/storage/gcs.py` already supports direct GCS resumable uploads plus finalize/existence checks.
- `services/uploads/sessions.py` and `services/uploads/finalize.py` already make Drive the execution boundary for governed writes.
- `Drive File` already persists `storage_backend` and `storage_object_key`.
- `Drive Processing Job` already exists for async reconcile-style work.

So the missing piece is not "add GCS support". The missing piece is:

- a site-level operator control page
- a staged cutover model
- a safe legacy attachment offload path

## Recommendation

Build one Single DocType, but frame it as a site storage control plane, not just a credential form.

Recommended name:

- `Drive Storage Settings`

Recommended scope:

- site-level only
- `System Manager` only
- controls the active storage runtime for this site
- validates bucket access
- starts and monitors migration

Long term, `Ifitwala_Press` should still own environment storage profiles.
This settings page is the correct early-phase bridge, not the final multi-tenant control plane.

## Proposed Settings Page

The form should map closely to the existing runtime profile contract instead of inventing a second storage model.

### Core Runtime Fields

- `enabled`
- `backend_name`
  - `local`
  - `gcs`
- `storage_mode`
  - `local_only`
  - `gcs_for_new_writes`
  - `gcs_primary_with_local_fallback`
- `bucket_or_container`
- `base_prefix`
  - default shape: `sites/<site_name>`
- `credential_source`
  - `adc_or_workload_identity` recommended
  - `service_account_json` fallback

### Secret And Identity Fields

- `project_id` optional
- `service_account_json` encrypted and only shown when the fallback mode is selected

The production recommendation should remain:

- Workload Identity / ADC in production
- embedded JSON only for local dev or single-server fallback

### URL And Access Fields

- `object_url_base`
- `download_url_base`
- `preview_url_base`

Important:

- these bases are acceptable for public or proxy-backed access
- they are not enough by themselves for private governed file delivery

### Migration Control Fields

- `migrate_public_files`
- `migrate_private_files`
- `batch_size`
- `delete_local_after_verification`
  - default off
- `migration_status`
- `last_validation_on`
- `last_migration_on`
- `migration_summary_json`

### Form Actions

- `Test Connection`
- `Save And Enable For New Uploads`
- `Dry Run Existing Attachment Offload`
- `Start Offload`
- `Pause Offload`
- `Resume Offload`
- `Reconcile Missing Local Files`

## Runtime Resolution Proposal

Keep the existing config/env path, but extend it with settings lookup.

Recommended resolution order:

1. emergency env override
2. cached `Drive Storage Settings`
3. legacy `frappe.conf` / env profile
4. local default

This keeps the current code paths viable while allowing the Desk page to become the normal operator workflow.

## Critical Scope Correction

If the goal is "put our files in GCS instead of on the bench site", the correct storage scope is:

- `sites/<site>/public/files/**`
- `sites/<site>/private/files/**`
- including `private/files/ifitwala_drive/**`

The migration target is not:

- `site_config.json`
- backups
- logs
- locks
- assets
- temp files
- arbitrary files elsewhere under `sites/<site>`

Moving the whole site folder would mix application/runtime concerns into the Drive storage boundary and would be a bad architectural cut.

## Operating Model

### 1. New Governed Uploads

Once `storage_mode = gcs_for_new_writes`:

- `create_upload_session` issues GCS upload targets
- `finalize_upload_session` writes the final blob to GCS
- `Drive File.storage_backend` becomes `gcs`
- `Drive File.storage_object_key` remains the canonical storage locator

This is the first cutover and should happen before legacy migration.

### 2. Existing Governed Drive Files

For existing `Drive File` rows with `storage_backend = local`:

- enqueue background reconcile work
- copy the local blob to GCS
- verify size and hash
- update `Drive File.storage_backend`
- update `Drive File.storage_object_key` if the destination key changes
- only change `File.file_url` after the read path is confirmed

This preserves governance and does not invent new metadata.

### 3. Legacy Frappe `File` Attachments Outside Drive Governance

These should not be turned into fake governed Drive files.

Instead:

- offload their blob bytes to GCS
- preserve the existing `File` row
- track migration state separately from Drive governance
- keep the read path compatible for old consumers

That respects the rule that no file becomes meaningful governance state without real classification metadata.

## Legacy Offload Flow

Recommended sequence:

1. Save settings and validate bucket access.
2. Enable `gcs_for_new_writes`.
3. Keep legacy attachments readable from local storage.
4. Run background offload in batches.
5. Verify counts, size, and checksums.
6. Flip to `gcs_primary_with_local_fallback`.
7. After a stability window, optionally prune local blobs.

This should be idempotent:

- if the target object already exists and matches size/hash, mark the item completed
- retries must not duplicate logical records
- local deletion must never happen before verification

## Async Job Model

Use the existing `Drive Processing Job` with `job_type = reconcile` for per-file or per-batch migration work.

Each job should capture:

- `file`
- optional `drive_file`
- source path
- destination object key
- size
- checksum
- verification result
- cleanup eligibility

Queue recommendation:

- dry run on `drive_default`
- bulk offload on `drive_heavy`

## Read Compatibility Requirement

This proposal only makes sense if old file URLs keep working during migration.

That means we need one of these before final cutover:

- a compatibility read layer that serves `/files/...` and `/private/files/...` from GCS when the local blob is gone
- or a canonical proxy route that legacy `File.file_url` values are migrated onto

What we should not do:

- point private governed files directly at raw bucket URLs
- require callers to guess bucket paths
- rewrite every upstream consumer individually

## Public And Private Topology

A single bucket can work initially, but the design should still separate public and private behavior.

Recommended posture:

- private files remain default
- public organization/school media can use a public prefix or separate public bucket
- `object_url_base` is most useful for public media or proxy/CDN domains
- private downloads/previews should use signed grants or an app-controlled proxy

Before full private cutover, `gcs.py` should grow a real private-read grant path instead of relying only on configured base URLs.

## What Not To Do

- do not auto-migrate all existing files when the settings document is merely saved
- do not move the whole `sites/<site>` folder
- do not create fake `Drive File` rows for legacy attachments with no governance metadata
- do not bypass Drive upload sessions for new governed flows
- do not delete verified local blobs until remote reads are proven
- do not expose raw GCS paths to UI code or business code

## Minimal Delivery Plan

### Slice 1

- add `Drive Storage Settings`
- add cached runtime resolution from the Single DocType
- add `Test Connection`

### Slice 2

- use settings-driven GCS for new governed uploads
- keep legacy attachments local

### Slice 3

- add dry run reporting for existing `File` rows under `public/files` and `private/files`
- add reconcile jobs for governed and legacy attachment offload

### Slice 4

- add compatibility reads for migrated legacy files
- add optional cleanup/prune of local blobs after verification

## Decision Summary

The right proposal is:

- one Single DocType page for site storage settings
- immediate GCS cutover for new Drive-managed uploads
- separate, explicit, background offload for existing attachment roots
- strict separation between governed Drive files and legacy non-governed Frappe attachments

That gets you to the original goal of "bucket-backed site files" without breaking the current Drive architecture or inventing unsafe fallback behavior.
