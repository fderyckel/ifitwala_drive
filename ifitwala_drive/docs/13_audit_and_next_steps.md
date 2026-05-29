# Docs Audit And Next Steps

Status: current working audit
Date: 2026-05-29

## Bottom line

The docs now describe one product: a governed institutional file domain tightly coupled to Ifitwala_Ed.

Legacy conversation material was removed. Duplicate product framing was consolidated. The remaining docs are ordered so a reader moves from product intent, to authority boundaries, to API/storage contracts, to operational and remaining-work notes.

## Docs cleanup completed

Removed:

- `00_discussions.md`
  Historical discussion dump. It mixed old `File Classification` assumptions, old naming/migration ideas, and useful principles. Keeping it in `/docs` made it too easy to treat retired thinking as current design.

Consolidated:

- `01_product_principles.md`
- `14_drive_north_star_v1.md`

Those now live as:

- `01_product_north_star.md`

Renamed into the active order:

1. `01_product_north_star.md`
2. `02_drive_authority_decision.md`
3. `03_system_architecture.md`
4. `04_security_runtime.md`
5. `05_ifitwala_ed_boundary.md`
6. `06_api_contracts.md`
7. `07_storage_adapter_contract.md`
8. `08_cross_portal_preview_contract.md`
9. `09_semantic_browse_plan.md`
10. `10_storage_settings_gcs_offload.md`
11. `11_public_file_cutover_contract.md`
12. `12_gcs_ops_runbook.md`
13. `13_audit_and_next_steps.md`

## What is left from the original plan

Keep the remaining work practical and user-facing:

1. Finish the five first workflows end to end:
   task resources, task submissions, applicant documents, portfolio/journal artefacts, and organization/school media.
2. Make reuse first-class for teacher resources and organization media:
   users should pick existing governed assets before uploading duplicates.
3. Complete semantic browse:
   no user-facing `DRF-*` IDs, human labels from Ed context, fewer empty folder hops, and tests for old folder records.
4. Finish public/private media posture:
   public organization media can use CDN/public delivery only when explicitly public; private governed files stay signed or app-controlled.
5. Keep legacy attachment offload boring:
   staged batches, verification before prune, clear operator runbook, and no fake governed `Drive File` rows for ungoverned old attachments.
6. Reduce wrapper clutter over time:
   keep ergonomic surface wrappers, but make sure all of them delegate to the same workflow-spec session/finalize/grant contracts.
7. Harden the operational loop:
   verify the hourly scheduler in production, alert on cleanup failures, and keep processing-job failure review visible to operators.

## Security suggestions

Prioritize these without adding a new permission universe:

1. Keep the upload/session rate limits tuned by user, site, and route; add equivalent pressure controls to grant-heavy read routes where needed.
2. Keep byte inspection synchronous before finalize; add async malware scanning later only as a second layer.
3. Make private reads short-lived by default; never put durable private bucket URLs into DTOs.
4. Keep portal grant routes Ed-owned for Ed-owned surfaces; Drive should issue already-authorized file actions.
5. Add audit for sensitive events:
   finalize, replace, grant issued, delete, erase, failed MIME validation, denied grant.
6. Alert on abuse signals:
   many abandoned sessions, repeated denied grants, MIME mismatch spikes, and temp-object growth.
7. Treat public media as an explicit workflow contract, not a convenience flag.

## Future-proofing suggestions

Keep the architecture flexible without making V1 heavy:

1. Preserve the provider-neutral storage adapter:
   `local`, `gcs`, and later `s3_compatible` should not leak into business logic.
2. Let Ifitwala_Press own tenant storage profiles, quotas, bucket bindings, and worker topology later.
3. Keep object keys opaque:
   governance truth belongs in Drive metadata, not path structure.
4. Keep derivatives version-bound:
   previews and thumbnails should track the current `Drive File Version` and be erased with the source.
5. Prefer logical bindings over blob duplication for shared resources and templates.
6. Keep queues semantic inside Drive, but normalize to runtime-valid Frappe queues at enqueue time.
7. Do not add broad sharing, desktop-sync metaphors, or a separate ACL system until a real Ifitwala_Ed workflow proves the need.

## Product standard

The next good milestone is not "more storage features".

It is:

- a teacher can reuse or upload a task resource without thinking about governance
- a student can submit and replace work without seeing file plumbing
- admissions can collect required documents without orphan files
- staff can see previews safely
- operators can move storage to GCS without breaking current users

Great integration here should feel quiet: fewer choices for normal users, stronger defaults underneath, and no hidden fallback that weakens governance.
