Here is **Practical Order #1**: the canonical design-lock note for **Option C**.
## Status

**LOCKED — working architecture decision**

This note defines the chosen transition architecture for **Ifitwala_drive** and its relationship to **Ifitwala_Ed** and **Ifitwala_Press**.

This note exists to stop drift between three bad outcomes:

* “Drive is only a storage proxy forever”
* “Drive fully replaces the old governance model immediately”
* “Each new file flow invents its own partial file architecture”

This decision is the canonical reference until explicitly reopened.

---

## 1. Decision

We are choosing **Option C: hybrid transition**.

This means:

* **Ifitwala_Ed** remains the workflow authority.
* **Ifitwala_drive** becomes the mandatory file execution boundary.
* New governed uploads, delivery, processing, and canonical references go through Drive.
* Existing governance guarantees from Ifitwala_Ed are preserved during transition.
* Drive grows over time from storage/delivery authority into a richer product-facing file domain and UX surface.

This is **not** a storage-only forever model.
This is **not** a full doctrinal replacement on day 1.

It is a staged transition.

---

## 2. Why this decision was chosen

Option C was chosen because it best balances:

* UX ambition
* governance safety
* migration realism
* cost-conscious early delivery
* future readiness

Your product goals explicitly require:

* **context first, Drive second**
* frictionless teacher/student workflows
* reusable resources
* folder navigation when needed
* strong safety/security
* no governance drift
* object-storage-ready architecture
* tight coupling to Ifitwala_Ed at all times.

A full immediate replacement is cleaner in theory but too easy to get wrong.
A storage-only forever model is safer short-term but under-delivers on the actual product direction.

---

## 3. Architectural split

### 3.1 Ifitwala_Ed owns

* academic workflows
* admissions workflows
* task/submission/business context
* portfolio, applicant, employee, referral, school, organization domain logic
* workflow visibility and base permission authority

### 3.2 Ifitwala_drive owns

* upload sessions
* storage abstraction
* canonical file references
* signed delivery / preview grants
* async file processing
* Drive folders and browse surface
* resource bindings
* file versions
* file-domain APIs
* file audit / erasure execution
* eventual richer Drive-native file UX and tooling

### 3.3 Ifitwala_Press owns later

* provisioning
* bucket bindings
* quotas
* environment policy
* worker topology
* tenant operations and cost monitoring.

---

## 4. Non-negotiable invariants that survive the transition

The following rules remain true throughout Option C.

### 4.1 One business-document owner

Every governed file has exactly one authoritative **business-document owner**.

Ownership is never:

* the uploader
* the creator
* the human employee
* the student user
* the guardian user

Uploader/creator are audit metadata only.
Subject is who the file is about.
Owner is the authoritative business document controlling lifecycle.

### 4.2 No orphan files

Every governed file must belong to one owner and one slot.
Free-floating files are invalid.

### 4.3 Slot semantics are law

Slots remain mandatory and control:

* replacement behavior
* versioning
* retention behavior
* deletion scope
* downstream workflow meaning

No slot means no valid governed upload.

### 4.4 File content is not the business record

Deleting files must not break:

* grades
* analytics
* applicant decisions
* structured academic/business records.

### 4.5 No raw path assumptions

No UI, service, or renderer may construct file URLs from guessed storage paths.
Only canonical Drive refs or canonical returned URLs are allowed.

### 4.6 No parallel ACL system in v1

The root permission rule remains:

> if you cannot see the owning document, you cannot see the file.

Drive may enforce action-level policy, but it does not introduce a detached permission universe in v1.

### 4.7 Folders are navigation, not governance truth

Folders support:

* browse UX
* reuse
* organization
* resource discovery

Folders do not replace:

* ownership
* subject
* slot
* retention
* organization/school governance.

---

## 5. Phase model for Option C

## Phase 1 — Drive as mandatory execution boundary

Drive takes over:

* upload sessions
* storage abstraction
* object storage writes
* canonical refs
* signed delivery
* async processing
* minimal folders
* bindings

Ifitwala_Ed continues to supply the governance contract and workflow semantics.

This phase is intentionally close to the “storage/delivery extraction” model, but it is **not** the final architecture.

## Phase 2 — Drive-native product surface

Drive adds:

* teacher resource library
* shared folders
* Drive browser
* search/filter
* reuse-first pickers
* template/workspace flows

At this stage, users begin to experience Drive as a real product surface, not only hidden infrastructure.

## Phase 3 — Selective domain promotion

Only after Phase 1 and 2 are proven, we may promote more governance and domain semantics into Drive-native objects where it reduces complexity **without weakening invariants**.

This phase may gradually reduce dependence on the older `File Classification` mental model, but only through explicit, documented transition.

---

## 6. What Phase 1 must not do

Phase 1 must **not**:

* become “storage-only forever”
* introduce a generic consumer Drive clone
* invent an external ACL/ReBAC system
* let folders become the legal/governance truth
* replace all governance objects and docs in one pass
* silently duplicate blobs when references/workspaces would do
* bypass Ifitwala_Ed workflow context.

---

## 7. Canonical API direction

Ifitwala_Ed must stop thinking in:

* raw `File`
* raw attachment path
* generic upload widget

and must start thinking in:

* Drive upload session
* Drive resource
* Drive submission artifact
* Drive binding
* Drive canonical ref / canonical returned URL.

The v1 API surface remains intentionally small:

* `create_upload_session(...)`
* `finalize_upload_session(...)`
* `abort_upload_session(...)`
* `create_and_classify_file(...)`
* `replace_drive_file_version(...)`
* `upload_task_resource(...)`
* `upload_task_submission_artifact(...)`
* `upload_applicant_document(...)`
* `upload_portfolio_evidence(...)`
* `upload_organization_media(...)`
* `list_folder_items(...)`
* `list_context_files(...)`
* `issue_download_grant(...)`
* `issue_preview_grant(...)`.

---

## 8. First flows to migrate

Only these flows are in scope first:

1. task resources
2. task submissions
3. applicant documents
4. organization media

These are highest-value, already specified, and strong tests of the architecture.

Portfolio/journal remains important, but it can follow immediately after those first four.

---

## 9. Storage and deployment intent

Early stage deployment remains:

* cost-conscious
* same tenant/site as Ifitwala_Ed
* same DB initially
* object storage ready from day 1
* container deployed alongside Ifitwala_Ed by Ifitwala_Press.

The architecture must preserve later separation of:

* runtime
* DB
* storage bucket
* workers

without changing business contracts.

---

## 10. Definition of done for Option C work

A change under Option C is only done if:

* it preserves file governance invariants
* it introduces no unclassified governed file path
* it uses Drive as the execution boundary
* it does not rely on storage-path guessing
* it does not weaken erasure safety
* it keeps Ifitwala_drive tightly coupled to Ifitwala_Ed context
* it improves UX or architecture without drifting into generic-drive noise
* it includes tests for the main invariant it touches.

---

## 11. Reopening this decision

This design-lock may only be reopened if one of the following is explicitly proposed in writing:

* full replacement of the remaining legacy governance model
* externalized permission model
* significant change in ownership/slot semantics
* cross-tenant or cross-context sharing requirements
* a decision to keep Drive as storage-only permanently

Until then, Option C is the active architecture.

---

## My blunt implementation note

Under this decision, the **next artifact is not another abstract debate**.

The next artifact is:

1. **canonical API contract**
2. then the first implementation slice:

   * `Drive Upload Session`
   * storage abstraction
   * signed delivery
   * `Drive Processing Job`
   * `Drive Folder`
   * `Drive Binding`
3. then the first four Ifitwala_Ed flow adapters

That is the practical path.

