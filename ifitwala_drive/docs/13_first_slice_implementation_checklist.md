# First Slice Implementation Checklist

## Status

Proposed.

This checklist turns the browse-placement matrix into an execution sequence for the first concrete slice:

1. admissions applicant documents, health, applicant image, guardian image
2. student image
3. task submissions
4. organization and school media

It assumes the existing Phase 1 rule remains unchanged:

* all new governed writes go through Drive
* folders are navigation only
* canonical refs replace raw path thinking

---

## Checked Inputs

This checklist is derived from:

* [09_phase1_contract_matrix.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/09_phase1_contract_matrix.md)
* [11_storage_navigation_repair_proposal.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/11_storage_navigation_repair_proposal.md)
* [12_context_browse_placement_matrix.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/12_context_browse_placement_matrix.md)
* [services/uploads/finalize.py](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/uploads/finalize.py)
* [services/uploads/sessions.py](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/uploads/sessions.py)
* [services/integration/ifitwala_ed_admissions.py](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_admissions.py)
* [services/integration/ifitwala_ed_tasks.py](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_tasks.py)
* [services/integration/ifitwala_ed_media.py](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_media.py)

---

## 1. Foundation Work

- [ ] Add a real `Drive File` DocType.
- [ ] Add a real `Drive File Version` DocType.
- [ ] Define the minimal server-side creation service that finalization will call to create:
  * `Drive File`
  * initial `Drive File Version`
  * `Drive Binding` where the flow contract already supports it
- [ ] Update `finalize_upload_session_service(...)` so successful finalize no longer ends at raw `File` compatibility only.
- [ ] Make finalize return non-null:
  * `drive_file_id`
  * `drive_file_version_id`
  * `canonical_ref`
- [ ] Preserve compatibility `file_url` only as a derived value for old Ed surfaces.
- [ ] Add tests asserting that finalize produces a real Drive identity instead of `None`.

---

## 2. Folder Resolution Foundation

- [ ] Add one server-side folder resolver service.
- [ ] Make folder resolution deterministic from owner context, attached context, slot, and flow wrapper.
- [ ] For workflow-bound uploads, do not let the client choose arbitrary folders.
- [ ] If a caller supplies a folder, validate:
  * organization match
  * school match where required
  * owner-context compatibility
  * allowed folder kind for the flow
- [ ] Persist resolved browse placement on the Drive-side records needed for later retrieval.
- [ ] Implement system-managed root folders for:
  * Admissions
  * Student
  * Organization Media
- [ ] Do not make physical storage keys or folder names the governance truth.

---

## 3. Browse Retrieval Foundation

- [ ] Implement `list_context_files(...)` for at least the first slice owners.
- [ ] Implement `list_folder_items(...)` for the first system-managed folder roots.
- [ ] Ensure browse responses can show:
  * title
  * canonical ref
  * folder or path context
  * binding role
  * preview status
- [ ] Ensure sensitive visibility still resolves from the owning document, not from folder membership.

---

## 4. Admissions Slice

### 4.1 Placement Rules

- [ ] Applicant document items resolve into:
  * `Admissions / Applicant / <applicant> / Documents / Identity`
  * `Admissions / Applicant / <applicant> / Documents / Academic`
  * or another `Documents` child chosen from the authoritative admissions document-type classification
- [ ] Applicant health vaccination proofs resolve into:
  * `Admissions / Applicant / <applicant> / Documents / Health`
- [ ] Applicant image resolves into:
  * `Admissions / Applicant / <applicant> / Profile / Applicant Image`
- [ ] Guardian image resolves into:
  * `Admissions / Applicant / <applicant> / Profile / Guardian Images`

### 4.2 Service Work

- [ ] Extend admissions upload wrappers so they either:
  * resolve the folder explicitly before session creation
  * or pass enough authoritative context for the Drive resolver to do it
- [ ] Keep `Student Applicant` as the authoritative owner for applicant docs, health, applicant images, and guardian images.
- [ ] Do not create a separate governance model for profile images versus documents.
- [ ] Use the existing admissions authoritative validation again at finalize time.

### 4.3 Binding Work

- [ ] Create `Drive Binding` rows for admissions files where the browse/retrieval surface needs them.
- [ ] Keep applicant documents using `applicant_document`.
- [ ] For applicant and guardian images, use the currently available browse binding only if it is already locked; otherwise keep them retrievable by owner context until a more specific role is locked.

### 4.4 Tests

- [ ] Add tests for document placement into `Documents / Identity`.
- [ ] Add tests for health placement into `Documents / Health`.
- [ ] Add tests for applicant-image placement into `Profile / Applicant Image`.
- [ ] Add tests for guardian-image placement into `Profile / Guardian Images`.
- [ ] Add tests that invalid cross-applicant folder placement fails closed.

---

## 5. Student Image Slice

### 5.1 Placement Rules

- [ ] Student image resolves into:
  * `Student / <student> / Profile / Student Image`

### 5.2 Service Work

- [ ] Keep `Student` as the authoritative owner.
- [ ] Keep the current student-image contract from `ifitwala_ed_media.py`.
- [ ] Ensure the resolver derives organization and school from the authoritative student context, not the client payload.

### 5.3 Binding Work

- [ ] Create or confirm a `Drive Binding` with role `student_image`.

### 5.4 Tests

- [ ] Add tests for correct student profile placement.
- [ ] Add tests that a student image cannot be placed under another student's folder tree.

---

## 6. Task Submission Slice

### 6.1 Placement Rules

- [ ] Task submission artifacts resolve into a projection path like:
  * `Student / <student> / Academic Year / <year> / Courses / <course> / Tasks / <task> / Submissions`
- [ ] Keep this as a browse projection.
- [ ] Do not change the authoritative owner away from `Task Submission`.

### 6.2 Service Work

- [ ] Preserve the authoritative task-submission contract already enforced in `ifitwala_ed_tasks.py`.
- [ ] Resolve course, task, and academic-year browse context from authoritative Ed data, not from client input.
- [ ] Re-check write authority on the owning `Task Submission` for both create-session and finalize.

### 6.3 Binding Work

- [ ] Create or confirm a `Drive Binding` with role `submission_artifact`.
- [ ] Ensure the same file is retrievable from:
  * submission context
  * task context
  * student academic projection
- [ ] Do this without duplicating the underlying blob.

### 6.4 Tests

- [ ] Extend existing task-submission tests to assert non-null Drive identity.
- [ ] Add tests for browse projection path resolution.
- [ ] Add tests that mismatched task, student, course, or year context is rejected if derived values no longer match the session.

---

## 7. Organization And School Media Slice

### 7.1 Placement Rules

- [ ] Organization logo resolves into:
  * `Organization Media / Organization / Logos`
- [ ] Organization reusable media resolves into:
  * `Organization Media / Organization / Public Media`
  * or another system-managed media branch defined by the authoritative media key
- [ ] School logo resolves into:
  * `Organization Media / Schools / <school> / Logos`
- [ ] School gallery or campus images resolve into:
  * `Organization Media / Schools / <school> / Campus Media`
  * or another system-managed school-media branch defined by the authoritative slot/media key

### 7.2 Service Work

- [ ] Preserve organization-owned governance even for school-scoped media.
- [ ] Keep reuse-first behavior on the media consumer side.
- [ ] Ensure media placement is derived from the authoritative organization-media slot builder logic, not guessed from filenames.

### 7.3 Binding Work

- [ ] Create or confirm `organization_media` bindings for media items that must appear in media libraries and consumer pickers.
- [ ] Keep consumer URL fields transitional only.

### 7.4 Tests

- [ ] Add tests for organization logo placement.
- [ ] Add tests for school logo placement.
- [ ] Add tests for school gallery or campus media placement.
- [ ] Add tests that cross-organization placement is rejected.

---

## 8. API And UI Follow-Through

- [ ] Update the finalize response contract for the first slice surfaces so clients receive a real Drive identity.
- [ ] Add enough browse payload for the UI to display context placement without path guessing.
- [ ] Keep current compatibility surfaces working while replacing raw attachment thinking underneath.
- [ ] Do not expose storage keys in UI payloads.

---

## 9. Verification Gates

- [ ] No new governed flow in the first slice creates `File` directly in business logic.
- [ ] No first-slice UI builds file paths from guessed storage locations.
- [ ] Every first-slice finalize path re-checks authoritative business context server-side.
- [ ] Every first-slice flow has at least one placement test and one negative validation test.
- [ ] Existing compatibility URL fields remain derived-only.
- [ ] One file can appear in multiple browse surfaces without duplicate truth.

---

## 10. Recommended Coding Order

1. implement `Drive File` and `Drive File Version`
2. update finalize to create real Drive identity
3. implement folder resolver and system-managed roots
4. wire admissions placement
5. wire student-image placement
6. wire task-submission projection placement
7. wire organization and school media placement
8. implement `list_context_files(...)`
9. implement `list_folder_items(...)`
10. add UI consumption and compatibility fallbacks

That sequence keeps the work on the shortest path to visible improvement in findability without weakening governance.
