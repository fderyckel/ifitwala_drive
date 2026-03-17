v# `ifitwala_drive_practical_order_3_drive_upload_session.md`

## Goal

Implement the first real Drive-backed execution slice:

* `Drive Upload Session` DocType
* upload-session service methods
* thin API methods
* one end-to-end flow: **task submission upload**
* no Drive browser yet
* no preview matrix yet
* no broad domain rewrite yet

This is the first proof that `ifitwala_drive` is the mandatory execution boundary.

---

## 1. Scope of this slice

### Included

* create upload session
* finalize upload session
* abort upload session
* storage abstraction hook for temporary upload target
* Drive-side validation of required governance intent
* Drive-side creation of governed file artifact by calling the authoritative creation path
* one first wrapper: `upload_task_submission_artifact`

### Explicitly not included

* Drive browser
* folder picker UI
* generalized search
* public sharing
* collaboration
* crypto-erase
* full preview/derivative pipeline
* migration of every upload surface

That stays aligned with the current implementation notes that explicitly forbid trying to do too much in the same PR and require hard, explicit failures over clever inference.

---

## 2. Required app files for this slice

Create these files first:

```text
ifitwala_drive/
  ifitwala_drive/
    api/
      uploads.py
      submissions.py

    services/
      uploads/
        __init__.py
        sessions.py
        finalize.py
        validation.py

      integration/
        __init__.py
        ifitwala_ed_tasks.py

      storage/
        __init__.py
        base.py
        gcs.py
        signed_urls.py

    drive/
      doctype/
        drive_upload_session/
          drive_upload_session.json
          drive_upload_session.py
          drive_upload_session.js
          test_drive_upload_session.py

    tests/
      test_task_submission_upload_flow.py
```

Keep `api/*` thin. Real logic belongs in `services/*`. That is already consistent with the architecture direction we locked.

---

## 3. First API methods to implement

## 3.1 `api/uploads.py`

Expose only:

* `create_upload_session`
* `finalize_upload_session`
* `abort_upload_session`

These methods should:

* validate top-level request shape
* delegate immediately to services
* return canonical response payloads only

They should **not**:

* contain business workflow logic
* create `File` directly
* guess governance defaults silently

---

## 3.2 `api/submissions.py`

Expose only:

* `upload_task_submission_artifact`

This wrapper should:

* accept task-submission-specific inputs
* derive the correct governed payload for `create_upload_session`
* keep Ifitwala_Ed from reconstructing raw governance payloads everywhere

This directly matches your goal that Ifitwala_Ed should think in Drive submission artifacts, not raw file machinery.

---

## 4. Service responsibilities

## 4.1 `services/uploads/validation.py`

This is where the hard fail-closed checks go.

It must validate at least:

* owner_doctype present
* owner_name present
* attached_doctype present
* attached_name present
* organization present
* school present where required
* primary_subject_type present
* primary_subject_id present
* data_class present
* purpose present
* retention_policy present
* slot present
* filename present

That preserves the current required classification discipline already locked in the dispatcher contract.

No slot → reject upload. That rule is explicitly non-negotiable in your task workflow notes.

## 4.2 `services/uploads/sessions.py`

Responsibilities:

* create `Drive Upload Session`
* generate opaque session key
* generate upload token if needed
* resolve storage backend
* request temporary upload target from storage layer
* return session response

This layer does **not** finalize the governed file.

## 4.3 `services/uploads/finalize.py`

Responsibilities:

* verify upload session exists and is valid
* verify session status allows finalize
* verify temporary object exists in storage
* update received size/hash if applicable
* call the authoritative governed creation path
* mark session completed
* return canonical Drive artifact info

This is the bridge from upload mechanics to governed file creation.

---

## 5. Critical architectural decision in this slice

For this first slice, **do not rewrite the governance core yet**.

Instead:

* `Drive Upload Session` lives in `ifitwala_drive`
* finalization may still call a compatibility creation path equivalent to current `create_and_classify_file(...)`
* that compatibility path can remain the safest place to preserve current invariants while the Drive layer takes over execution

That is exactly the staged Option C behavior: Drive becomes the mandatory execution boundary first, without pretending the deepest semantics must all be redesigned in the same step.

---

## 6. First wrapper: task submission upload

Start with this one because it is the strongest test of the architecture.

Your notes are clear that task submission files are:

* evidence of work
* time-bound
* replaceable
* disposable
* not the grade
* not the academic decision

### Wrapper contract

`upload_task_submission_artifact(...)` should take:

* `task_submission`
* `student`
* `filename_original`
* `mime_type_hint`
* `expected_size_bytes`
* optional `secondary_subjects`

And derive server-side:

* owner_doctype = `Task Submission`
* owner_name = task submission id
* attached_doctype = `Task Submission`
* attached_name = task submission id
* primary_subject_type = `Student`
* primary_subject_id = student
* data_class = `assessment`
* purpose = `assessment_submission`
* retention_policy = configured task-submission policy
* slot = `submission`
* organization and school from task submission context

This keeps the wrapper workflow-aware and avoids repeating raw payload assembly all over Ifitwala_Ed.

---

## 7. Storage layer for this slice

## 7.1 `services/storage/base.py`

Define a minimal interface:

* `create_temporary_upload_target(...)`
* `temporary_object_exists(...)`
* `finalize_temporary_object(...)`
* `abort_temporary_object(...)`

## 7.2 `services/storage/gcs.py`

Implement the GCS-backed version.

For now, keep it simple:

* one temporary object key per session
* one signed PUT target or proxy upload target
* one final object key after finalization

## 7.3 `services/storage/signed_urls.py`

Responsible only for issuing short-lived signed targets/grants.

This keeps storage and access mechanics out of business logic.

---

## 8. Response shapes to lock now

## 8.1 `create_upload_session`

Must return:

* `upload_session_id`
* `session_key`
* `status`
* `expires_on`
* `upload_strategy`
* `upload_target`

## 8.2 `finalize_upload_session`

Must return:

* `drive_file_id` or compatibility file-governance identifier
* `drive_file_version_id` if available
* `file_id`
* `canonical_ref`
* `status`
* `preview_status`

## 8.3 `abort_upload_session`

Must return:

* `upload_session_id`
* `status`

Keep these stable from the start. That reduces churn for SPA integration.

---

## 9. First acceptance criteria

This first slice passes only if all of these are true:

### Upload/session behavior

* a valid task-submission upload session can be created
* an invalid payload hard-fails
* missing slot hard-fails
* expired session cannot finalize
* aborted session cannot finalize

### Governance preservation

* finalization still produces a governed file artifact with full metadata
* no direct `File.insert()` is added outside the authoritative creation path
* ownership remains business-document ownership
* file content remains disposable relative to grades/analytics

### Storage behavior

* no `/private` or `/public` path assumptions leak into UI/API responses
* only canonical refs or returned upload/download targets are exposed

### Tests

* one end-to-end test proves task-submission upload works
* one negative test proves missing slot is rejected
* one negative test proves invalid owner payload is rejected

These acceptance points are straight out of your current governance and workflow notes.

---

## 10. What not to do in this slice

Do not:

* add UI file browser
* add folder picker UI
* auto-classify legacy files
* add ACLs to raw `File`
* rewrite retention semantics
* build generalized Drive search
* try to support all upload surfaces at once

Those are explicitly forbidden or intentionally postponed in your notes.

---

## 11. Concrete implementation order inside this slice

Do the work in this order:

1. finalize `Drive Upload Session` DocType
2. implement `services/uploads/validation.py`
3. implement `services/storage/base.py` + `gcs.py` stub
4. implement `services/uploads/sessions.py`
5. implement `api/uploads.py`
6. implement `services/uploads/finalize.py`
7. implement `api/submissions.py` with `upload_task_submission_artifact(...)`
8. write `test_task_submission_upload_flow.py`
9. only then wire Ifitwala_Ed to call it

That order minimizes confusion and makes failures easier to isolate.

---
