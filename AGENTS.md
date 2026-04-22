# AGENTS.md — Ifitwala_drive

You are working on **Ifitwala_drive**, a production-grade governed file platform tightly coupled to **Ifitwala_Ed**.

This app is **not** a generic Drive clone.
It is **not** a loose attachment helper.
It is **not** an infra/orchestration product.
It is a **governed institutional file domain** built to serve Ifitwala_Ed with high integrity, low-friction UX, and future-ready storage architecture.

If anything in implementation conflicts with this file, **this file wins**.

---

## 1. Core Mission

Ifitwala_drive exists to make file workflows in Ifitwala_Ed:

- frictionless for teachers, students, admissions, and staff
- governed from day 1
- storage-backend independent
- secure against naive and adversarial misuse
- cost-conscious early
- scalable later

Its job is to own:

- upload sessions
- workflow-spec governed finalize
- slot enforcement
- version lineage
- canonical references
- authoritative Drive metadata
- storage abstraction
- preview / derivative state
- file audit / erasure state

Ifitwala_Ed continues to own:

- academic workflows
- admissions workflows
- business meaning of records
- task / submission / applicant / portfolio / employee / school context

Ifitwala_Press later owns:

- provisioning
- bucket bindings
- quotas
- worker topology
- tenant operations

---

## 2. Non-Negotiable Architecture Rules

### 2.1 All governed file writes go through the Drive boundary

There must be **no direct business-logic `File.insert()` path** for governed flows.

Any new governed upload must go through an authoritative Drive service or wrapper equivalent to:

- `create_upload_session(...)`
- `ingest_upload_session_content(...)`
- `finalize_upload_session(...)`
- `replace_drive_file_version(...)`

Drive owns the governed finalize transaction end-to-end. Compatibility `File` rows may still exist for Frappe-native surfaces, but they are projections, not the governance authority.

### 2.2 No file becomes meaningful without governance metadata

A file must not be finalized without governance metadata.

Minimum required governance includes:

- attached_doctype
- attached_name
- primary_subject_type
- primary_subject_id
- data_class
- purpose
- retention_policy
- slot
- organization
- school where required
- workflow id / contract version / workflow payload

This is locked in the current Drive metadata and workflow-spec contract, not in `File Classification`.

### 2.3 No orphan files

Every governed file must be anchored to one owning business document and one slot.
Free-floating files are architecturally invalid.

### 2.4 Slot semantics are law

Slots are not labels.
Slots control:

- replacement behavior
- versioning
- deletion scope
- retention behavior
- downstream workflow meaning

Examples already locked:
- `submission`
- `feedback`
- `rubric_evidence`
- `identity_passport`
- `portfolio_artefact`
- `organization_media__<media_key>`

### 2.5 File content is not the business record

Files may be deleted or erased without breaking:

- grades
- analytics
- applicant decisions
- structured academic history

This separation is already a core architecture rule and must never be violated.

### 2.6 No raw path assumptions

UI code, business code, and renderers must never build file URLs by guessing storage paths.

Only canonical references or canonical returned URLs may be used. This must remain true even if storage later moves fully to object storage.

### 2.7 Context first, Drive second

Ifitwala_drive must support browsing, folders, and search.

But primary UX is contextual:
- task resource
- task submission
- applicant document
- portfolio evidence
- organization media
- employee image

Do not force users into deep folder browsing for common actions.

### 2.8 Reuse before re-upload

For reusable assets, especially organization/school media and teacher resources, the first UX path should be reuse/selection, not blind re-upload. This reuse-first rule is already locked for organization media and should generalize to Drive browsing.

---

## 3. Product Boundaries

### 3.1 What Ifitwala_drive IS

- governed file platform
- storage abstraction boundary
- upload/session boundary
- file metadata authority
- file version authority
- drive/browser surface for resources and managed assets

### 3.2 What Ifitwala_drive is NOT

- not a replacement for academic workflows
- not a grading engine
- not a document authoring suite by default
- not a generic cross-tenant shared drive
- not an infra orchestration plane
- not a parallel permission universe detached from Ifitwala_Ed

### 3.3 Permission model

The root rule remains:

> if you cannot see the owning document, you cannot see the file. :contentReference[oaicite:6]{index=6}

Layer split:

- Frappe / Ifitwala_Ed permissions decide who can see the owning record
- Drive action policy decides upload / replace / delete / download / preview rules
- UI decides what controls to show

Do not invent an external ACL system unless proven necessary later.

---

## 4. Engineering Rules

### 4.1 Do not invent schemas
Never invent:
- fieldnames
- DocTypes
- slot names
- purposes
- retention policies
- API payloads
- permission semantics

Work from authoritative files and docs.

When touching governed uploads, file links, attachment DTOs, preview/open/download routes, thumbnails, or derivative behavior, read in this order:

1. `ifitwala_drive/docs/05_optionC_design_lock.md`
2. `ifitwala_drive/docs/04_coupling_with_ifiwala_ed.md`
3. `ifitwala_drive/docs/06_api_contracts.md`
4. `../ifitwala_ed/ifitwala_ed/docs/files_and_policies/files_03_implementation.md`
5. `../ifitwala_ed/ifitwala_ed/docs/files_and_policies/files_07_education_file_semantics_and_cross_app_contract.md`
6. `../ifitwala_ed/ifitwala_ed/docs/files_and_policies/files_08_cross_portal_governed_attachment_preview_contract.md`

Those files define the live boundary:

- Drive is the sole governed-file execution and metadata authority.
- Ed owns workflow meaning and surface authorization.
- Vue/API contracts must expose server-owned `open_url` / `preview_url` / `thumbnail_url` style DTOs or surface-specific equivalents, not raw storage topology.

When the Drive change affects admissions uploads, applicant images, applicant documents, or reviewer-facing applicant evidence, also read:

- `../ifitwala_ed/ifitwala_ed/docs/admission/05_admission_portal.md`
- `../ifitwala_ed/ifitwala_ed/docs/admission/10_ifitwala_drive_portal_uploads.md`

### 4.2 Preserve current governance intent
If refactoring from Ifitwala_Ed into Ifitwala_drive, preserve:
- workflow-spec boundary discipline
- Drive metadata authority
- erasure posture
- canonical URL discipline
- ownership rules for tasks, admissions, portfolio, organization media

### 4.3 Legacy tolerance
The system may tolerate compatibility `File` projections and migrated historical records temporarily, but no new governed flow may rely on `File Classification`, raw storage paths, or undocumented upload payload shapes.

### 4.4 Async by default for heavy work
Never block hot user flows on:
- preview generation
- derivatives
- scans
- indexing
- reconciliation

### 4.4.1 Queue runtime contract

Drive may keep semantic queue classes such as `drive_short`, `drive_default`, and `drive_heavy` on its own job records, but every `frappe.enqueue(...)` call must resolve to a queue that is valid for the active site runtime.

Rules:

- if matching custom Drive workers are part of the documented runtime topology, enqueue onto them
- otherwise normalize at the enqueue boundary to runtime-valid standard queues instead of sending semantic labels directly into Frappe
- a governed upload/finalize success path must not fail only because deferred preview or derivative work selected an undeployed queue label
- any new async path must document its queue ownership and add regression coverage for enqueue-time queue resolution

### 4.5 Fail closed
If a file cannot be proven governed, routable, and policy-valid, stop. Do not silently fall back to generic attach behavior.

### 4.6 Documentation and downstream coordination are part of the change
Whenever code changes, update the relevant docs to reflect:
- the technical behavior that changed
- the design or architecture choice behind it
- any new API, schema, lifecycle, or operator expectation

If a change affects how **Ifitwala_Ed** uploads, stores, resolves, previews, downloads, or otherwise delivers files, that downstream contract change must be made explicit in the docs and **Ifitwala_Ed must be informed**. Treat this as part of the implementation, not optional follow-up.

---

## 5. Required Initial Use Cases

V1 must explicitly support:

1. Task resources
2. Task submission artifacts
3. Applicant documents
4. Portfolio / journal artifacts
5. Organization / school governed media

These are already the clearest existing governed workflows in your notes.

---

## 6. Security Posture

Assume:

- students will probe URLs
- users will retry uploads badly
- staff will overshare by mistake
- public media and private media will get confused if design is weak

Therefore:

- private-by-default storage
- short-lived access grants
- no path guessing
- no long-lived public links for governed private files
- server-side authorization on every sensitive action
- audit minimal but real
- erasure logic must be deterministic and irreversible

The erasure contract is already strict: no content remnants, no recoverable versions, minimal audit only.

---

## 7. Storage and Deployment Intent

Early stage:
- cost-conscious
- same tenant/site as Ifitwala_Ed
- same DB initially
- object storage ready from day 1
- container deployed alongside Ifitwala_Ed by Ifitwala_Press

Future:
- storage may move independently
- workers may separate
- bucket policy and quotas may be managed by Press
- canonical reference contract must survive this unchanged

---

## 8. Forbidden Moves

Never:

- bypass Drive services to create governed files
- use raw sidebar Attach for governed flows
- infer classification from hooks
- encode local disk paths into UI logic
- tie file deletion to grade deletion
- make admissions files owned by Guardian or Student
- create a second governance system for organization media
- treat folders as the legal/governance truth
- silently duplicate blobs at scale when a logical workspace/reference model would do

Admissions ownership and organization-media governance are already explicitly locked in the existing notes.

---

## 9. Definition of Done

A change is only done if:

- it preserves the file governance contract
- it introduces no unclassified governed file path
- it does not depend on storage-path guessing
- it has server-side validation
- it does not weaken erasure safety
- it includes tests for the main invariant it touches
- it keeps Ifitwala_drive tightly coupled to Ifitwala_Ed context while preserving Drive as the file authority

---

## 10. Product Standard

The product standard is not “does it upload”.
The product standard is:

- low friction for normal users
- no governance drift
- no unsafe fallback
- strong future compatibility with object storage and tenant ops
- clear educational workflow fit
