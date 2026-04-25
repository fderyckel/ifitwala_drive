# Ifitwala Drive Docs

Status: Canonical index
Last reset: 2026-04-25

This folder keeps the active reference set for Drive product direction, architecture, coupling, security/concurrency, and API contracts.

## Active Read Order

1. `14_drive_north_star_v1.md`
   working product frame: context-first Drive, not a generic cloud drive
2. `01_product_principles.md`
   compact current product principles
3. `02_system_architecture.md`
   locked target system model
4. `03_security_concurrency.md`
   locked runtime posture
5. `04_coupling_with_ifiwala_ed.md`
   narrow Ed/Drive boundary contract
6. `06_api_contracts.md`
   canonical API direction
7. `05_optionC_design_lock.md`
   migration and compatibility decision note

## Companion Docs

- `16_object_storage_adapter_contract.md`
- `17_semantic_browse_proposal.md`
- `19_public_file_cutover_contract.md`
- `20_gcs_ops_runbook.md`
- `21_cross_portal_governed_attachment_preview_contract.md`

Companion docs must not weaken the authority of the active read order.

## Non-Authoritative / Historical

- `00_discussions.md`
  historical stub only; do not use for implementation guidance
- `audit.md`
  point-in-time audit note; verify against current canonical docs before relying on it
- `18_gcs_bucket_settings_and_site_offload_proposal.md`
  proposal material unless promoted by a current canonical contract

## Current Rules

- Drive owns governed upload sessions, storage identity, file/version/binding records, derivatives, grants, access events, and erasure execution.
- Ifitwala Ed owns workflow meaning, tenant scope, permissions, surface visibility, and post-finalize business mutation.
- New governed upload work uses `workflow_id + workflow_payload`.
- Wrappers are transitional facades over canonical session/finalize/grant behavior.
- `File Classification` is retired and must not return as runtime authority.
- Folders are UX/navigation only, never permission, ownership, retention, or erasure truth.
- Browser and SPA contracts must not expose raw private storage paths.
