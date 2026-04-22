# Ifitwala Drive Docs

Status: Canonical index
Last reset: 2026-04-19

This folder keeps the active reference set for Drive architecture, coupling, security/concurrency, and API contracts.

Read in this order for governed file architecture work:

1. `01_product_principles.md`
2. `02_system_architecture.md`
3. `03_security_concurrency.md`
4. `04_coupling_with_ifiwala_ed.md`
5. `05_optionC_design_lock.md`
6. `06_api_contracts.md`

How to read the reset:

- `02_system_architecture.md` is the locked target system model
- `03_security_concurrency.md` is the locked runtime posture
- `04_coupling_with_ifiwala_ed.md` is the narrow Ed/Drive boundary contract
- `05_optionC_design_lock.md` is the phase and migration decision note
- `06_api_contracts.md` is the canonical API direction

Companion docs:

- `16_object_storage_adapter_contract.md`
- `19_public_file_cutover_contract.md`
- `20_gcs_ops_runbook.md`
- `21_cross_portal_governed_attachment_preview_contract.md`

Companion docs must not weaken the authority of `02` through `06`.
