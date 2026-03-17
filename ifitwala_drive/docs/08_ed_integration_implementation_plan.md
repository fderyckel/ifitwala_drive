# Ifitwala_Ed Integration Implementation Plan

## Purpose

This note defines the next implementation plan for **Ifitwala_drive under Option C** after the initial Phase 1 upload-session boundary was established.

It is grounded in the live `ifitwala_drive` docs and the current `ifitwala_ed` codebase. It is not a generic roadmap.

The governing rule remains:

* **Ifitwala_Ed stays the workflow authority**
* **Ifitwala_drive is the mandatory file execution boundary**
* **All governed file writes must cross the Drive boundary**

This plan is written to prevent drift back into raw `File`, raw attachment, or path-based behavior.

---

## Checked Sources

Drive docs checked:

* `ifitwala_drive/docs/04_coupling_with_ifiwala_ed.md`
* `ifitwala_drive/docs/05_optionC_design_lock.md`
* `ifitwala_drive/docs/06_api_contracts.md`
* `ifitwala_drive/docs/07_drive_upload_session.md`

Ifitwala_Ed docs and code checked:

* `ifitwala_ed/docs/files_and_policies/files_03_implementation.md`
* `ifitwala_ed/docs/files_and_policies/files_04_workflow_examples.md`
* `ifitwala_ed/docs/files_and_policies/files_05_organization_media_governance.md`
* `ifitwala_ed/utilities/governed_uploads.py`
* `ifitwala_ed/utilities/organization_media.py`
* `ifitwala_ed/admission/admissions_portal.py`
* `ifitwala_ed/setup/doctype/organization/organization.py`
* `ifitwala_ed/school_settings/doctype/school/school.py`
* `ifitwala_ed/school_site/doctype/program_website_profile/program_website_profile.js`
* `ifitwala_ed/assessment/doctype/task/task.json`
* `ifitwala_ed/assessment/doctype/task_submission/task_submission.js`
* `ifitwala_ed/assessment/task_submission_service.py`

---

## Validated Current State

### 1. The first four governed integration targets remain locked

The first four business flows remain:

1. `task resources`
2. `task submissions`
3. `applicant documents`
4. `organization media`

That order is already named in the Drive design lock and API contract notes.

### 2. The first execution slice should still be task submission

Even though the first four flows are listed in the order above, the safest first end-to-end execution slice remains **task submission upload** because:

* the evidence model is already explicit
* slot semantics are already locked as `submission`
* the current Ed code already has governed upload behavior to bridge from
* it proves session -> upload -> finalize -> governed creation -> binding without speculative schema work

### 3. Organization media is already real in Ifitwala_Ed

This is not a future concept. It already exists in Ed as governed media with:

* `Organization` as the canonical business-document owner
* optional `school` scope
* slot builders such as `organization_media__<media_key>`, `school_logo__<school>`, `organization_logo__<organization>`, and `school_gallery_image__<row_name>`
* reuse-first selection rules

### 4. Organization media consumers already span multiple Ed doctypes and surfaces

The plan must explicitly cover at least these consumers:

* `Organization`
* `School`
* `Program Website Profile`
* school-context website block props
* `Program` and website-facing program imagery surfaces that currently carry image fields

The important rule is unchanged: these consumers should **reuse organization media**, not invent a second governance model.

### 5. Task resources are the least normalized of the first four flows

Current Ed schema shows `Task.attachments` as a generic `Attached Document` table. Unlike task submissions, there is not yet a clearly normalized Drive-facing wrapper for task resource upload in the live code that was checked here.

That means:

* task resources remain a locked target
* but they require a mapping/refactor pass before they can become a clean Drive boundary flow

---

## Integration Inventory

This is the current working inventory for the first four flows.

| Flow | Current Ed surface | Current state | Drive readiness | Plan status |
| --- | --- | --- | --- | --- |
| Task submission | `Task Submission` form, submission service | Governed upload already exists in Ed | Can wrap now | First execution slice |
| Task resource | `Task.attachments` and related task delivery surfaces | Generic attachment schema still visible | Needs refactor first | Second integration target |
| Applicant document | `admissions_portal.upload_applicant_document` | Governed and slot-aware in Ed | Can wrap now | Third integration target |
| Organization media | `Organization`, `School`, website pickers, `Program Website Profile.hero_image` | Governed and reuse-first in Ed | Can wrap now | Fourth integration target |

---

## Locked Execution Invariants

These rules are now locked for implementation:

1. **Drive-only new writes** apply to the first four governed flows.
2. **Canonical source of truth in Ed** must be a Drive identifier/reference or an explicitly documented governed binding, never a raw path.
3. **Finalize is server-authoritative**. The client may upload bytes, but the client must not define governance truth.
4. **Legacy rows remain compatibility-readable** during transition, but they are not the target write model.
5. **Missing slot, invalid owner, invalid scope, invalid session state, or invalid binding must fail closed.**
6. **No consumer surface may construct storage URLs manually.**
7. **Every finalize/bind path must emit structured logs.**

---

## Pre-Implementation Contract Locks

These items must be locked before coding each flow, otherwise implementation drift is likely.

### 1. Canonical persistence contract in Ed

For each of the first four flows, implementation must explicitly define:

* which Ed field or binding stores the canonical Drive identifier/reference
* which legacy fields remain derived-only or transitional-only
* whether any existing `file_url` field remains a compatibility read field only

Locked rule:

* raw `file_url` must never become the source of truth in Ed for governed integrations

This mapping must be written before each flow is wired.

### 2. Legacy coexistence policy

The migration policy for the first four flows is:

* **compatibility reads for legacy rows**
* **Drive-only new writes**
* **selective backfill later**

Do not attempt a full legacy migration before the first four flows are proven end to end.

### 3. Finalization authority

Preferred model:

1. client uploads bytes to the Drive session target
2. a server-side Ed action requests finalization from Drive
3. Drive re-verifies session state, classification, owner, slot, and integration context server-side

Allowed fallback during transition:

* a direct Drive finalize API may exist, but it must still be treated as server-authoritative and must not trust frontend-supplied governance truth

### 4. Observability requirement

Each finalize/bind flow must emit structured events for at least:

* upload session created
* upload session finalized
* governed creation succeeded
* governed creation failed
* binding created
* binding updated
* owner mismatch rejected
* slot mismatch rejected
* invalid scope rejected

---

## Canonical Plan

## Phase 1.1 — Lock the Ed -> Drive integration contract

### Goal

Make Ifitwala_Ed stop thinking in raw `File`, generic attachment widgets, or guessed `file_url` semantics for new governed work.

### Actions

* Create one explicit mapping document per target flow:
  * current Ed entry point
  * target Drive wrapper
  * required metadata contract
  * blocking schema mismatch, if any
* Treat the current Drive upload-session APIs as the only allowed entry for new governed upload work:
  * `create_upload_session`
  * `finalize_upload_session`
  * `abort_upload_session`
  * `upload_task_submission_artifact`
* Keep `api/*` thin in Drive and keep real rules inside `services/*`
* Add a lint/test guard in both repos where possible to catch new direct governed `File.insert()` patterns in business logic

### Acceptance criteria

* every one of the first four flows has an identified Ed entry point
* every one has a target Drive wrapper or an explicitly named refactor blocker
* no new governed path is allowed to bypass the Drive boundary
* each flow has an explicit canonical persistence mapping before implementation starts

---

## Phase 1.2 — First execution slice: task submission upload

### Goal

Replace the task submission governed upload path in Ed with a Drive-backed execution path while preserving Ed as workflow authority.

### Ed surfaces to target first

* `ifitwala_ed/assessment/doctype/task_submission/task_submission.js`
* `ifitwala_ed/assessment/task_submission_service.py`
* the existing governed wrapper in `ifitwala_ed/utilities/governed_uploads.py`

### Drive contract

The Drive side should remain centered on:

* `upload_task_submission_artifact`
* `create_upload_session`
* `finalize_upload_session`

### Required behavior

1. Ed asks Drive to create a task-submission upload session.
2. Client uploads blob content to the temporary storage target returned by Drive.
3. A server-side Ed action requests finalization from Drive.
4. Drive calls the authoritative governed creation path as the compatibility bridge.
5. Ed stores returned Drive identifiers and canonical refs, not guessed storage paths.
6. Drive creates or confirms a `Drive Binding` with a submission-artifact role.

### Acceptance criteria

* no direct business-logic `File.insert()` path
* no raw path construction in Ed or Drive
* slot remains `submission`
* owner remains the authoritative business document
* deletion of submission files must not break grade or outcome truth
* replacement/versioning path stays possible later

---

## Phase 1.3 — Task resources integration

### Goal

Move task resource uploads off generic attachment behavior and into the Drive boundary.

### Current reality

The live Ed schema still exposes `Task.attachments` as a generic `Attached Document` table. This means task resources should be treated as the first refactor-heavy flow, not a wrapper-only flow.

### Required schema decision before coding

Do not begin this phase until the canonical Task-side representation of a resource is explicitly locked.

Allowed options to evaluate:

* a new Task resource child table with Drive refs/metadata
* a dedicated Task resource DocType
* a narrowly defined compatibility wrapper around the existing attachment shape

Locked constraint:

* do not let `Attached Document` remain the long-term governance truth by accident

### Implementation approach

* audit all current teacher-facing resource upload entry points around `Task` and task-delivery creation
* introduce a Drive wrapper for governed task resources
* replace generic file attachment behavior on both Desk and SPA/overlay resource upload surfaces in the same slice
* store Drive refs / canonical refs in Ed instead of treating the attachment table as governance truth

### Important rule

Do not use this phase to invent a full Drive browser.

The v1 objective is:

* correct governance
* clean binding
* future reuse

not full browsing/search UX.

### Acceptance criteria

* task resources no longer enter via raw attachment behavior
* Ed stores canonical Drive references
* slots are explicit and stable
* this flow is ready for later reuse-first UX
* the Task-side canonical persistence model is explicit before rollout

---

## Phase 1.4 — Applicant documents integration

### Goal

Shift admissions upload execution into Drive while preserving the existing admissions governance rules from Ed.

### Ed surfaces to target

* `ifitwala_ed/admission/admissions_portal.py`
* applicant document creation/update logic
* applicant review synchronization that currently follows upload

### Rollout order

Cut this flow over in this order:

1. admissions portal
2. Desk admissions surfaces

### Locked governance rules

* admissions files are owned by **Student Applicant**
* they are not owned by `Student`
* they are not owned by `Guardian`
* slot must be derived deterministically from the applicant document contract

### Additional invariants to lock before implementation

Implementation must explicitly define:

* whether one applicant may keep multiple files within the same admissions slot
* whether replacement preserves version history
* whether review/approval points to a slot, a bound file, or a bound file version
* what happens when a reviewed required document is replaced

### Implementation approach

* keep Ed responsible for applicant workflow decisions
* make Drive responsible for upload session, finalization, storage seam, canonical refs, and binding
* preserve the authoritative applicant-document slot mapping already locked in Ed docs

### Acceptance criteria

* no uploader-based ownership leakage
* missing or unmapped slot fails closed
* applicant review workflow still works after upload finalization
* no direct legacy Desk attachment path becomes canonical
* replacement/review behavior is explicitly defined, not inferred

---

## Phase 1.5 — Organization media integration

### Goal

Make Drive the execution boundary for organization media while preserving Ed’s existing organization-media governance model.

### Canonical ownership rule

The business-document owner remains `Organization`.

This does not change for:

* `School` logo
* `School` gallery image
* `Program Website Profile.hero_image`
* website block imagery
* program/website-facing reusable media

School context remains an optional classification scope, not a second governance system.

### Ed surfaces to target

Upload/manage surfaces already present in Ed:

* `Organization`
* `School`
* `ifitwala_ed.utilities.governed_uploads.upload_organization_logo`
* `ifitwala_ed.utilities.governed_uploads.upload_school_logo`
* `ifitwala_ed.utilities.governed_uploads.upload_school_gallery_image`
* `ifitwala_ed.utilities.governed_uploads.upload_organization_media_asset`

Reuse/selection surfaces already present in Ed:

* school-context website block props
* `Program Website Profile.hero_image`
* any program or website surface currently relying on organization media URLs

### Implementation approach

* keep the owner and classification semantics from `ifitwala_ed.utilities.organization_media`
* move blob-session execution into Drive
* keep reuse-first picker semantics
* ensure rendering continues to use canonical refs / canonical returned URLs only

### Selection and read contract

This phase must define the read side, not only uploads.

For organization media consumers, implementation must explicitly define:

* how media is queried
* which scope filters apply
* whether the consumer stores a Drive ref, governed media binding, canonical URL, or another documented governed reference
* whether rendering reads through a resolver/helper service

Locked rule:

* upload governance alone is not sufficient; consumer read behavior must also be canonical and path-safe

### Additional requirement for program and website imagery

Program and website surfaces should consume **organization media** as reusable governed assets.

Default assumption for implementation:

* `Program` image surfaces should not create a separate Program-owned governance model
* first establish the Drive media contract and selection contract cleanly
* only then consider upgrading Program image fields to explicit Drive refs in a later refinement

### Rollout order

Cut this flow over in this order:

1. `Organization` and `School` upload/manage surfaces
2. school-site block props
3. other website/program organization-media consumers such as `Program Website Profile.hero_image`

### Acceptance criteria

* no raw URL-only media value becomes canonical
* organization media remains reusable across the allowed org/school scope
* `Organization` stays the owner
* UI keeps reuse-first behavior

---

## Phase 1.6 — Stabilization and invariant hardening

### Goal

Stop after the first four flows and harden the boundary before expanding the product surface.

### Checks

* every integrated governed flow uses the Drive boundary only
* sessions cannot finalize after abort or expiry
* missing slot fails closed
* invalid owner fails closed
* no UI constructs guessed URLs
* canonical refs survive storage abstraction changes
* permissions still root in owning-document visibility
* async processing remains outside hot upload paths

### Test expansion

Drive-side:

* task resource upload/session tests
* applicant document upload/finalize tests
* organization media upload/session tests
* no-direct-`File.insert()` regression tests

Ed-side:

* wrapper tests proving Ed calls Drive rather than writing governed files directly
* form/API tests for the first four flows

---

## Phase 2 — Secondary Drive UX

Only after the first four governed flows are stable.

Then add:

* teacher resource library
* context-first listings
* reuse flows
* light search/filter
* folders as navigation only

Do not make folders or browse state the governance truth.

---

## Implementation Order

Recommended execution order:

1. lock the Ed -> Drive mapping contract for the first four flows
2. lock canonical persistence fields/bindings in Ed for each flow before coding starts
3. fully integrate task submission upload
4. lock the Task resource target schema
5. refactor and integrate task resources
6. integrate applicant documents
7. integrate organization media upload/manage surfaces
8. integrate organization media consumer surfaces
9. run a stabilization pass
10. only then build broader Drive browsing/reuse UX

This preserves the locked first-four target list while still using **task submission** as the safest first execution slice.

---

## What Not To Do Now

Do not:

* build a generic Drive browser first
* migrate every upload surface at once
* invent a parallel ACL system
* let folders become governance truth
* store raw bucket or disk paths in Ed
* create a separate governance system for program or website imagery
* bypass the existing authoritative governed creation path with a new unsafe `File.insert()` flow

---

## Confirmed Product Decisions

These decisions are now locked for this implementation plan:

1. **Task resources** must cut over both Desk `Task.attachments` and the task-creation overlay / SPA upload surface in the same slice.
2. **Applicant documents** cut over portal first, then Desk.
3. **Program image fields** remain organization-media consumers for now; establish the Drive media contract first, then consider explicit Drive refs later.
4. **Organization media** should cut over `Organization` and `School` first, then school-site block props immediately after those core upload/manage surfaces.
