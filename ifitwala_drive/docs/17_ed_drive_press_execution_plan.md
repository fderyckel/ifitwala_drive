# Ed, Drive, And Press Execution Plan

## Bottom Line

Execute this in order:

1. lock provider-neutral storage and the Press runtime profile boundary
2. harden upload session idempotency and finalize concurrency
3. move workflow-specific Drive contract logic into Ed
4. shrink Drive into storage/access/read-model responsibilities
5. ship a Google Drive-style folder/file navigator using Ifitwala_Ed tokens and interaction patterns

Do not start the true Drive UI before the storage and concurrency foundations are stable.

---

## 1. Outcome To Reach

At the end of this plan:

- `File` + `File Classification` remain the only governance truth
- Drive upload/finalize is safe under retries and concurrency
- Drive supports `local`, `gcs`, and `s3_compatible`
- Ifitwala_Press controls the tenant environment storage profile
- the Drive UI is one real folder/file browser, not a context-home launcher
- Ed deep-links into the same Drive tree rather than a separate browse mode

---

## 2. Sequencing Rule

This work should be done in five phases.

The order matters because:

- concurrency and storage mistakes become expensive once the UI depends on them
- the Drive browser should sit on stable path/index contracts
- Press should define the runtime storage profile before Drive depends on it

---

## 3. Phase 1: Storage Portability And Press Contract

### Goal

Make storage provider-neutral and Press-operated before further file-platform expansion.

### `ifitwala_drive`

Primary files:

- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/storage/base.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/storage/gcs.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/storage/local.py`

Work:

- evolve `StorageBackend` into a stable object-storage contract
- add `s3_compatible` backend support
- remove GCS-specific assumptions from non-storage code
- ensure finalize semantics do not assume rename/move support
- ensure signed upload/download generation lives fully behind the adapter

### `ifitwala_press`

Primary files/services:

- `Tenant Environment` storage/provider modeling
- `/Users/francois.de/Documents/ifitwala_press/ifitwala_press/services/founder_runtime_service.py`
- `/Users/francois.de/Documents/ifitwala_press/ifitwala_press/services/environment_lifecycle_service.py`

Work:

- define the resolved runtime storage profile published to tenant runtimes
- wire provider selection, bucket/container binding, quota, region/endpoint, and credential source into environment provisioning/runtime config
- keep this as environment configuration, not a synchronous application dependency

### Deliverable

- Drive can boot against a resolved storage profile without caring whether the provider is `gcs` or `s3_compatible`

---

## 4. Phase 2: Upload Session Idempotency And Concurrency Hardening

### Goal

Make upload-session creation and finalize safe under high concurrency and retries.

### `ifitwala_drive`

Primary files:

- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/uploads/sessions.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/uploads/finalize.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/uploads/validation.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/concurrency.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ifitwala_drive/doctype/drive_upload_session/drive_upload_session.py`

Work:

- add request-level idempotency for session creation
- make finalize replay-safe for the same upload session
- shorten lock scope so network-bound storage work is not done under a broad application lock when avoidable
- ensure terminal and in-progress session states support safe re-entry
- rely on unique constraints for session keys, canonical refs, and any required binding uniqueness

### `ifitwala_ed`

Primary files:

- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/docs/high_concurrency_contract.md`
- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/utilities/governed_uploads.py`
- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/admission/admissions_portal.py`

Work:

- make callers pass idempotency tokens where retries are realistic
- ensure Desk and SPA upload initiators share the same retry-safe contract

### Deliverable

- duplicate submits and retry storms do not create duplicate governed files

---

## 5. Phase 3: Move Workflow Contracts Back Into Ed

### Goal

Stop carrying workflow semantics in both repos.

### `ifitwala_ed`

Primary areas:

- new `ifitwala_ed.integrations.drive` contract registry
- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/utilities/file_dispatcher.py`
- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/utilities/governed_uploads.py`
- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/admission/admissions_portal.py`
- organization media helpers
- task upload helpers

Work:

- centralize workflow-specific Drive upload contract building in Ed
- centralize post-finalize business mutations in Ed
- keep `file_dispatcher.create_and_classify_file(...)` as the authoritative governed writer
- migrate remaining legacy exceptions such as applicant desk image upload onto the same bridge or explicitly quarantine them

### `ifitwala_drive`

Primary areas:

- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_tasks.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_admissions.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_media.py`

Work:

- reduce these modules from workflow-authoritative logic to thin compatibility wrappers
- move toward one generic upload-session/finalize contract bridge

### Deliverable

- Ed owns business meaning
- Drive owns file-platform mechanics

---

## 6. Phase 4: Shrink Drive Persistent Metadata To A Read Model

### Goal

Remove Drive as a shadow governance database.

### `ifitwala_drive`

Primary files:

- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/files/creation.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/files/access.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/folders/browse.py`
- `Drive File` DocType definition
- `Drive Binding` DocType definition

Work:

- shrink `Drive File` to storage/access/index metadata
- derive governance fields by join from `File` and `File Classification`
- defer `Drive File Version` unless real replace-version behavior is being implemented
- keep `Drive Binding` only where non-owning reuse or cross-context browse is actually needed
- preserve compatibility for callers during migration

### `ifitwala_ed`

Primary files:

- `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/assessment/doctype/task/task.py`
- any code that currently assumes every governed file must have a primary `Drive Binding`

Work:

- narrow validation dependencies so bindings are only required where the product truly needs reusable contextual references

### Deliverable

- one governance truth
- one storage/access/read-model layer

---

## 7. Phase 5: True Drive Browser

### Goal

Ship one real folder/file workspace with Google Drive-style navigation and Ifitwala_Ed visual language.

### `ifitwala_drive`

Primary files:

- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/folders/browse.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/folders/resolution.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/api/folders.py`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/apps/workspace/App.vue`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/features/workspace/api.ts`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/features/workspace/types.ts`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/styles/tokens.css`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/styles/layout.css`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/styles/components.css`
- `/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/ui-spa/src/styles/app.css`

Work:

- replace workspace-home-first behavior with a real tree/list shell
- build deterministic path-based browse APIs
- support root tree, folder expansion, breadcrumbs, dense file list, selection, preview, and download
- use Ifitwala_Ed token families and typography rather than a separate Drive-only visual identity
- remove marketing-style hero/KPI emphasis from the working browse surface

### `ifitwala_ed`

Primary areas:

- task, applicant, employee, student, and media surfaces that currently deep-link into context-specific Drive modes

Work:

- update “Open in Drive” actions to deep-link into the shared folder tree
- keep context-first entry points while using one consistent Drive shell

### Target UX

Interaction model:

- Google Drive-like folder/file navigation
- left tree rail
- top toolbar
- breadcrumbs
- dense file table/list
- row actions

Visual model:

- Ifitwala_Ed typography
- Ifitwala_Ed color tokens
- restrained surfaces
- subtle gradients only in the background

### Deliverable

- users browse governed files like a real drive
- governance truth still stays outside folders

---

## 8. Acceptance Criteria

This plan is only complete when all of these are true:

- new governed writes still only finalize through the authoritative Ed writer
- session creation and finalize are retry-safe
- Drive can run on `gcs` and `s3_compatible` without higher-level code changes
- Drive never needs synchronous Press calls on hot paths
- the main Drive UI is a folder/file navigator, not a card launcher
- Ed deep-links land inside the same Drive tree
- permissions are inherited from owning records, not folder membership

---

## 9. Test Gates

### `ifitwala_drive`

- storage backend contract tests for `local`, `gcs`, and `s3_compatible`
- finalize replay/idempotency tests
- lock-scope and duplicate-submit tests
- browse read-model tests
- UI tests for folder navigation and deep-link opening

### `ifitwala_ed`

- contract-building tests per workflow
- retry-safe upload initiation tests
- validation tests for any remaining binding-dependent surfaces

### `ifitwala_press`

- resolved environment storage profile tests
- environment/provider configuration tests
- quota/profile publication tests

---

## 10. Recommended Immediate Build Order

If work starts now, the order should be:

1. storage adapter contract and `s3_compatible` backend scaffold
2. Press runtime storage-profile publication
3. upload-session idempotency hardening
4. contract-registry migration into Ed
5. Drive read-model simplification
6. real Drive navigator UI

That keeps the platform safe under concurrency before the browse surface becomes more ambitious.
