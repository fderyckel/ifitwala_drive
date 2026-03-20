# Storage And Navigation Repair Proposal

## Status

Partially implemented.

The product frame that now governs follow-on implementation is [14_drive_north_star_v1.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/14_drive_north_star_v1.md).

This note addresses the current gap between:

* strong governed-upload discipline
* weak human-operable browse and retrieval behavior

The current implementation is preserving some important invariants, but it is not yet delivering an acceptable file-management model for users or operators.

It should be treated as a repair plan for Phase 1, not as a new architecture direction.

## Implemented Repair Slice

The following repair slice is now live in code:

* `/drive_workspace` loads a governed workspace home instead of requiring manual query parameters
* workspace home groups readable targets into `Reviewing`, `My Drive`, and readable root `Folders`
* if exactly one readable target exists, the workspace opens it automatically
* organization-level root browse now filters child folders and files by owning-document read permission
* employee profile-image uploads now create and use the deterministic tree `Employees / <employee> / Profile / Employee Image`

This means the note is no longer purely conceptual for navigation. The remaining work is expanding home providers and browse projections beyond the first implemented slice.

---

## 1. Problem Statement

Today, the app has three structural issues:

1. **Physical storage is opaque, but logical browse identity is missing.**
2. **Folders exist, but they are not yet authoritative for navigation placement.**
3. **Finalize still ends at raw `File` compatibility instead of a real Drive file identity.**

That combination creates the exact outcome you flagged:

* the storage tree looks messy
* the upload session does not carry enough browseable path intent
* users and staff cannot reliably find files by context
* the system still behaves more like a governed upload pipe than a real Drive product

The complaint is valid.

The current state is safe-ish for machine storage, but incomplete for real file operations.

---

## 2. What Is Wrong In The Current Code

### 2.1 Final object keys are deliberately opaque

`finalize.py` currently generates final storage keys like:

* `files/<hash-prefix>/<hash-prefix>/<sha256>.<ext>`

This is implemented in `_build_final_object_key(...)`.

That is acceptable as an internal storage strategy, but only if the system also has a strong logical file identity layer.

Right now it does not.

### 2.2 Upload session stores `folder`, but only as a weak optional reference

`create_upload_session_service(...)` stores a `folder` on `Drive Upload Session`, but the current validation only checks whether the folder exists.

It does not yet prove that the folder matches:

* owner doctype/name
* organization
* school
* allowed context
* allowed slot placement

So the folder field exists, but it is not yet a proper routing contract.

### 2.3 Finalize response still has no real Drive identity

`_completed_response(...)` still returns:

* `drive_file_id = None`
* `drive_file_version_id = None`
* `canonical_ref = None`

That means the system still finishes at a compatibility `File` object plus `file_url`, instead of a first-class Drive file artifact.

### 2.4 Browse contracts exist in docs, but not in the live execution path

The docs already lock:

* `Drive Folder`
* `Drive Binding`
* `list_folder_items(...)`
* `list_context_files(...)`
* `canonical_ref`

But the live flow does not yet complete those concepts end to end.

### 2.5 `Drive Binding` already assumes `Drive File`, but `Drive File` is not implemented

This is the biggest structural gap.

The codebase already contains a `Drive Binding` DocType that links to:

* `Drive File`
* `File`

But there is no implemented `Drive File` DocType yet.

So the product has:

* session metadata
* folder metadata
* binding metadata

without the main governed file identity that should sit in the middle.

---

## 3. Design Goal

The fix is not to make the raw disk tree itself become the product.

The fix is to explicitly separate three layers:

1. **Physical storage key**
2. **Canonical Drive identity**
3. **Logical browse path**

### 3.1 Physical storage key

This is for:

* local filesystem
* object storage
* moves between storage backends
* debugging
* lifecycle operations

It must remain backend-controlled and must never become UI truth.

### 3.2 Canonical Drive identity

This is the missing layer.

Every governed upload should finalize into:

* `Drive File`
* `Drive File Version`
* stable `canonical_ref`

This becomes the real product object.

### 3.3 Logical browse path

This is what users need in order to find things.

Examples:

* `Admissions / Applicant / APPL-02-2026-223 / Documents / ID Documents`
* `Admissions / Applicant / APPL-2026-03-001 / Health`
* `Organization Media / School / SCH-0001 / Logos`
* `Employees / EMP-0001 / Profile / Employee Image`

This path must be stored and queryable in Drive metadata, not inferred from the storage object key.

---

## 4. Proposed Model

## 4.1 Implement `Drive File`

Finalize must create a first-class `Drive File` row.

Minimum required fields:

* `file`
* `attached_doctype`
* `attached_name`
* `owner_doctype`
* `owner_name`
* `organization`
* `school`
* `primary_subject_type`
* `primary_subject_id`
* `data_class`
* `purpose`
* `retention_policy`
* `slot`
* `folder`
* `status`
* `preview_status`
* `canonical_ref`
* `current_version`
* `current_version_no`
* `content_hash`
* `is_private`
* `storage_backend`
* `storage_object_key`
* `display_name`
* `display_path`
* `context_path`

Important:

* `folder` remains browse/navigation metadata
* `owner_*`, `slot`, and classification remain governance truth
* `storage_object_key` remains storage truth

## 4.2 Implement `Drive File Version`

Every finalize creates version `1`.

Every governed replacement creates a new immutable version row.

Minimum required fields:

* `drive_file`
* `version_no`
* `file`
* `storage_object_key`
* `size_bytes`
* `mime_type`
* `content_hash`
* `version_reason`
* `is_current`

This keeps slot semantics and replacement behavior explicit.

## 4.3 Make `Drive Binding` real

Finalize or wrapper-specific post-finalize logic should create a `Drive Binding` for contextual UX.

Examples:

* task submission upload -> `submission_artifact`
* applicant document -> `applicant_document`
* organization logo -> `organization_media`

This gives the product two clean retrieval modes:

* context-first retrieval
* folder browse retrieval

---

## 5. Folder Strategy

## 5.1 Introduce system-managed context roots

For the required V1 contexts, Drive should create deterministic system-managed roots.

Examples:

* `Admissions`
* `Admissions/Applicant`
* `Organization Media`
* `Task Resources`
* `Task Submissions`
* `Portfolio`

These are `Drive Folder` rows, not filesystem directories.

## 5.2 Resolve folder placement server-side

Do not require the client to invent folder routing.

Drive should resolve folder placement from:

* owner doctype/name
* attached doctype/name
* slot
* purpose
* flow wrapper

Examples:

* applicant passport item -> `Admissions/Applicant/<applicant>/Documents/ID Documents`
* applicant transcript item -> `Admissions/Applicant/<applicant>/Documents/Transcript`
* applicant vaccination proof -> `Admissions/Applicant/<applicant>/Health`
* applicant profile image -> `Admissions/Applicant/<applicant>`

The UI may supply a folder in reusable resource surfaces, but workflow-bound uploads should normally be placed by Drive automatically.

## 5.3 Add stronger folder validation

If a folder is supplied, Drive must validate:

* folder organization matches session organization
* folder school scope matches session school when applicable
* folder owner contract is compatible with the upload owner
* folder kind is allowed for the wrapper
* system-managed folders cannot be bypassed for locked workflows

For applicant uploads, a folder under another applicant must hard-fail.

---

## 6. Storage Key Strategy

## 6.1 Keep storage backend authority

No UI or business code may use storage keys as truth.

That remains locked.

## 6.2 Replace the current flat opaque final-key layout with a structured opaque layout

The current fully hashed layout is too weak for operations.

Recommended final key pattern:

```text
files/private/org/<organization>/<owner_doctype_slug>/<owner_name>/<slot>/v<version>/<opaque_hash>.<ext>
```

Examples:

```text
files/private/org/ORG-0001/student_applicant/APPL-2026-03-001/profile_image/v1/8a...c4.jpg
files/private/org/ORG-0001/student_applicant/APPL-02-2026-223/identity_passport_passport_copy/v1/d2...99.png
files/private/org/ORG-0001/task_submission/TSUB-0001/submission/v2/4b...fe.docx
```

This keeps:

* no path guessing for consumers
* backend independence
* object-storage readiness

while making storage:

* debuggable
* supportable
* lifecycle-friendly

## 6.3 Improve temporary object layout

Recommended temporary key pattern:

```text
tmp/sessions/<yyyy>/<mm>/<dd>/<session_key>/<safe_filename>
```

This gives cleaner cleanup, inspection, and future TTL sweeps.

## 6.4 Do not use display folder names as storage folder names

Storage keys should stay stable and safe.

Logical browse names can be human-readable.
Storage prefixes should be deterministic and machine-oriented.

That avoids coupling rename behavior to object moves.

---

## 7. API Contract Changes

## 7.1 `create_upload_session`

The response should include resolved browse placement when available:

* `folder`
* `folder_path`
* `context_path`

Example:

```json
{
  "upload_session_id": "DUS-0001",
  "session_key": "opaque-session-key",
  "status": "created",
  "folder": "DRF-0008",
  "folder_path": "admissions/applicant/appl-2026-03-001/health",
  "context_path": "Admissions / Applicant / APPL-2026-03-001 / Health",
  "upload_strategy": "proxy_post",
  "upload_target": {}
}
```

The session should also persist the resolved values so finalization is deterministic.

## 7.2 `finalize_upload_session`

The response must stop returning a `None` Drive identity.

It should return:

* `drive_file_id`
* `drive_file_version_id`
* `canonical_ref`
* `folder`
* `folder_path`
* `context_path`
* `display_name`

`file_url` may remain as a transitional compatibility value, but not as the source of truth.

## 7.3 Implement browse APIs for real

The following documented APIs should be implemented and made the standard retrieval path:

* `list_folder_items(...)`
* `list_context_files(...)`

That is how users find files.
Not by inspecting `private/files`.

---

## 8. Admissions Example

The user-facing tree you showed is valid as a **logical browse tree**.

It should not be the filesystem truth, but it should absolutely exist in Drive metadata and APIs.

For applicant uploads, the proposal is:

### Logical browse tree

```text
Admissions
  Applicant
    APPL-2026-03-001
      Documents
        Identity
        Academic
        Health
      Profile
        Applicant Image
        Guardian Images
```

Recommended interpretation:

* `Health` belongs under `Documents`, not as a separate top-level branch
* applicant profile images and guardian images are better treated as profile/identity media, not mixed into document buckets

This keeps the browse tree understandable without weakening the underlying owner and slot rules.

### Canonical records

Each file under that tree has:

* one `Drive File`
* one current `Drive File Version`
* one business owner: `Student Applicant`
* one slot
* one binding role where applicable

### Physical storage

The physical object key stays backend-controlled and opaque-at-leaf.

This gives the product all three of these at once:

* governance
* browseability
* backend independence

---

## 8.1 Student Academic Evidence Views

Admissions is only one branch.

The same repair pattern should extend into student academic and co-curricular evidence.

The important rule is:

* the browse tree may be student-centric
* the authoritative owner must still remain the business document that controls lifecycle

So a task submission artifact may appear under a student view, but still be owned by `Task Submission`.

Recommended logical views:

```text
Student
  <student>
    Profile
      Student Image
    Academic Year
      <academic-year>
        Courses
          <course>
            Tasks
              <task>
                Resources
                Submissions
                Feedback
            Journal
            Reflections
        Reflections
        Activities
          Certificates
```

This should be understood as a **retrieval projection**, not as folder truth for governance.

### How this should map

* `Student Image` should appear in the student profile branch and use the existing `student_image` binding role
* task resources should appear under the course/task branch, but remain owned by the task-side business record
* task submissions should appear under student, course, and task views through bindings, while ownership stays on `Task Submission`
* portfolio or journal artifacts should appear in student-year-course views, but remain owned by their portfolio/journal entry record
* activity certificates should appear under student-year-activity views, but ownership should stay on the authoritative activity/certificate record once that contract is locked

This means one physical file may be reachable from:

* student view
* course view
* task view
* portfolio view

without duplicating the blob.

That is exactly why `Drive File` plus `Drive Binding` is necessary.

---

## 8.2 Other Human-Semantic Structures To Support

The same principle should apply beyond admissions and student evidence.

These should be treated as **human browse structures**, not as governance truth.

### Teacher working views

```text
Teacher
  <teacher>
    My Resources
    Shared Course Resources
    Reusable Templates
    Recent Uploads
```

Use this for:

* reusable lesson assets
* worksheets
* rubrics
* slide decks
* handouts

### Course and lesson views

```text
Course
  <course>
    Resources
    Lessons
      <lesson>
        Resources
        Activities
```

Use this for:

* course-level shared materials
* lesson resources
* lesson activity resources

### Assessment and feedback views

```text
Assessment
  <assessment-or-task>
    Resources
    Submissions
    Feedback
    Rubric Evidence
```

Use this for:

* assessment instructions
* exemplar resources
* student submissions
* teacher feedback attachments
* rubric evidence

### Portfolio and journal views

```text
Portfolio
  <student>
    <year>
      Journal
      Reflections
      Evidence
      Showcase
```

Use this for:

* journal entries
* reflection artefacts
* long-term evidence
* selected showcase items

### Activities and enrichment views

```text
Activities
  <student>
    <year>
      <activity>
        Evidence
        Certificates
        Media
```

Use this for:

* participation evidence
* awards
* certificates
* activity photos and media when governed

### Organization and school media views

```text
Organization Media
  Organization
    Logos
    Brand Assets
    Public Media
  Schools
    <school>
      Logos
      Campus Media
      Website Media
```

Use this for:

* logos
* gallery images
* website-facing media
* reusable institutional assets

### Staff and operations views

```text
Staff
  <employee>
    Profile
    Documents
      Identity
      HR
      Compliance
```

Use this for:

* employee images
* governed staff documents
* operational compliance evidence

### Cross-cutting work views

```text
Workspaces
  Recent
  Shared With Me
  Needs Review
  Reusable
  Archived
```

These are not owner trees.

They are convenience surfaces built from Drive metadata, bindings, and workflow state.

### Design rule across all of them

Where a file should appear is determined by:

* owner
* binding role
* slot
* context record
* organization and school scope

not by the storage object key.

This lets one governed file appear in the right places for humans without creating duplicate truth.

---

## 9. Migration Strategy

## 9.1 New writes first

Do not attempt a full historical migration first.

Phase the repair like this:

1. implement `Drive File` and `Drive File Version`
2. update finalize to create them
3. add server-side folder resolution
4. return real canonical refs
5. implement `list_context_files(...)`
6. implement `list_folder_items(...)`
7. route new applicant/task/media writes through the new identity model

## 9.2 Compatibility reads for old rows

Existing rows can remain readable by:

* legacy `File`
* existing `file_url`
* older attachment fields

But old rows should gradually receive:

* inferred `Drive File`
* inferred folder placement
* inferred bindings

through targeted backfill jobs.

## 9.3 Do not rewrite all physical old paths immediately

Backfilling metadata is the first win.

Physical storage-key rewrites should happen only:

* for new writes
* or through an explicit background migration later

That keeps rollout safe.

---

## 10. Non-Negotiables Preserved

This proposal does **not** weaken the locked architecture rules.

It preserves:

* all governed writes go through Drive
* no unclassified governed file path
* one authoritative business-document owner
* one slot per governed file
* folders as navigation only
* no raw path guessing
* object-storage readiness

What changes is this:

Drive becomes a usable governed file product, not only a disciplined upload pipe.

---

## 11. Recommended Implementation Order

## Phase A: identity repair

* add `Drive File`
* add `Drive File Version`
* update finalize to create them
* return real `canonical_ref`
* update tests to assert non-null Drive identities

## Phase B: placement repair

* add folder resolver service
* add stronger folder validation
* persist `folder`, `folder_path`, and `context_path` on session and file
* create system-managed context roots for admissions, submissions, and media

## Phase C: retrieval repair

* implement `list_context_files(...)`
* implement `list_folder_items(...)`
* wire admissions/task/media surfaces to these APIs
* keep `file_url` as compatibility-only where required

## Phase D: storage repair

* switch new writes to structured opaque storage keys
* keep old keys readable
* optionally backfill or relocate in background later

---

## 12. Decision

The right fix is:

* **not** “go back to raw human filesystem paths as product truth”
* **not** “keep fully opaque blob storage and tell users to search metadata later”

The right fix is:

* structured backend-controlled object keys
* real Drive file identities
* deterministic system-managed folder placement
* context-first retrieval APIs
* human-readable logical browse paths

That gives you the clean tree users expect without violating the governance rules in this repo.

The concrete per-surface follow-up lives in [12_context_browse_placement_matrix.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/12_context_browse_placement_matrix.md).
