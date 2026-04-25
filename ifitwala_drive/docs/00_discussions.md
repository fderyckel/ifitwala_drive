# Historical Discussions

Status: Historical, non-authoritative stub
Last reviewed: 2026-04-25
Code refs: None
Test refs: None

## Bottom Line

This file previously contained long-form working discussion notes from earlier Drive design phases. Those notes mixed product framing, migration ideas, obsolete dispatcher terminology, and retired classification assumptions.

They are no longer active implementation guidance.

## Active References

Use the current docs index and active contract set instead:

- `README.md`
- `14_drive_north_star_v1.md`
- `01_product_principles.md`
- `02_system_architecture.md`
- `03_security_concurrency.md`
- `04_coupling_with_ifiwala_ed.md`
- `05_optionC_design_lock.md`
- `06_api_contracts.md`
- `21_cross_portal_governed_attachment_preview_contract.md`

## Current Contract Reminder

- Drive is the governed file execution and metadata authority.
- Ed owns workflow meaning, tenant scope, and surface authorization.
- Folders are UX/navigation only, never legal or governance truth.
- Browser and SPA contracts must not expose raw private storage paths.
- The long-term Ed/Drive boundary is `workflow_id + workflow_payload`.
- Wrapper-specific APIs are transitional facades, not a second place to author workflow semantics.

## Historical Content Policy

If old discussion content is needed for archaeology, recover it from git history. Do not restore it into this active docs folder as canonical guidance.
