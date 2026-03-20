
* all new governed uploads go through Drive services,
* no file becomes meaningful without governance metadata,
* context first, Drive second,
* Ifitwala_Ed remains workflow authority,
* Ifitwala_drive remains file authority.

---

# `ifitwala_drive_canonical_api_contract_v1.md`

## Status

**LOCKED — v1 canonical API direction**

This contract defines the initial API surface between:

* **Ifitwala_Ed** as workflow/domain authority
* **Ifitwala_drive** as governed file authority

This is the contract Ifitwala_Ed should code against.
This is **not** a generic public API design.
It is a tight internal product boundary.

---

## 1. API design principles

### 1.1 Drive APIs are workflow-aware, not raw file endpoints

Ifitwala_Ed should not call low-level file mechanics directly.

Bad:

* generic upload file
* generic attach file
* raw path retrieval

Good:

* create upload session for task submission
* upload applicant document
* issue preview grant for organization media
* list files for lesson context

This matches your coupling note: Ifitwala_Ed should stop thinking in raw `File`, raw attachment path, and generic upload widgets, and start thinking in Drive resources, submission artifacts, media refs, upload sessions, and canonical refs.

### 1.2 Fail closed

If required governance context is missing, the API must reject the request.
No fallback to generic attach behavior.

### 1.3 Canonical references only

Consumers may receive:

* Drive file IDs
* canonical refs
* short-lived preview/download grants

Consumers must not construct storage paths.

### 1.4 Business-document owner is mandatory

Every create/finalize call must carry enough context to resolve one authoritative business-document owner.

Uploader is audit only.
Subject is not owner.

---

## 2. API surface overview

The v1 API is grouped into:

1. Upload/session APIs
2. File creation/version APIs
3. Domain wrapper APIs
4. Browse/search APIs
5. Access/grant APIs
6. Erasure APIs

---

# 3. Upload / session APIs

These APIs exist to make upload lifecycle explicit and resumable-ready.

## 3.1 `create_upload_session`

### Purpose

Create an upload session before any governed file is finalized.

### Called by

* task resource upload UI
* task submission UI
* applicant document upload UI
* organization media upload UI
* future lesson/portfolio flows

### Required request shape

```json
{
  "owner_doctype": "Task Submission",
  "owner_name": "TSUB-0001",
  "attached_doctype": "Task Submission",
  "attached_name": "TSUB-0001",
  "organization": "ORG-0001",
  "school": "SCH-0001",
  "folder": "optional-drive-folder-id",
  "primary_subject_type": "student",
  "primary_subject_id": "STU-0001",
  "data_class": "assessment",
  "purpose": "assessment_submission",
  "retention_policy": "until_school_exit_plus_6m",
  "slot": "submission",
  "secondary_subjects": [
    {
      "subject_type": "student",
      "subject_id": "STU-0002",
      "role": "co-owner"
    }
  ],
  "filename_original": "essay.docx",
  "mime_type_hint": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "expected_size_bytes": 543210,
  "is_private": 1,
  "upload_source": "SPA"
}
```

### Required behavior

* validates governance intent
* validates owner context
* validates slot presence
* creates `Drive Upload Session`
* returns upload session info + temporary upload target/grant

### Response shape

```json
{
  "upload_session_id": "DUS-0001",
  "session_key": "opaque-session-key",
  "status": "created",
  "expires_on": "2026-03-17 10:00:00",
  "upload_strategy": "signed_put",
  "upload_target": {
    "method": "PUT",
    "url": "short-lived-signed-url-or-proxy-endpoint",
    "headers": {}
  }
}
```

---

## 3.2 `finalize_upload_session`

### Purpose

Confirm upload completion and create the governed file record.

### Required request shape

```json
{
  "upload_session_id": "DUS-0001",
  "received_size_bytes": 543210,
  "content_hash": "sha256-optional-or-required-by-policy"
}
```

### Required behavior

* verifies session is valid and not expired
* verifies upload receipt
* creates authoritative governed file record
* creates initial version
* queues heavy async work if needed
* returns canonical Drive artifact info

### Response shape

```json
{
  "drive_file_id": "DF-0001",
  "drive_file_version_id": "DFV-0001",
  "file_id": "FILE-0001",
  "canonical_ref": "drv:ORG-0001:DF-0001",
  "status": "active",
  "preview_status": "pending"
}
```

---

## 3.3 `abort_upload_session`

### Purpose

Cancel a session that will not be used.

### Request

```json
{
  "upload_session_id": "DUS-0001"
}
```

### Response

```json
{
  "upload_session_id": "DUS-0001",
  "status": "aborted"
}
```

---

# 4. File creation / version APIs

These are the authoritative file-domain entrypoints.

## 4.1 `create_and_classify_file`

### Purpose

Single authoritative creation path for governed file creation.

This is the Drive-era continuation of the dispatcher-only rule from the current Ifitwala_Ed architecture.

### Called by

Usually internal service code after upload finalization, but may also be used by trusted server-side workflows.

### Required request shape

```json
{
  "file_artifact": {
    "file_id": "FILE-0001",
    "filename_original": "essay.docx",
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "size_bytes": 543210,
    "content_hash": "sha256..."
  },
  "governance": {
    "owner_doctype": "Task Submission",
    "owner_name": "TSUB-0001",
    "attached_doctype": "Task Submission",
    "attached_name": "TSUB-0001",
    "organization": "ORG-0001",
    "school": "SCH-0001",
    "primary_subject_type": "student",
    "primary_subject_id": "STU-0001",
    "data_class": "assessment",
    "purpose": "assessment_submission",
    "retention_policy": "until_school_exit_plus_6m",
    "slot": "submission",
    "is_private": 1,
    "upload_source": "SPA"
  },
  "secondary_subjects": [],
  "folder": "optional-drive-folder-id"
}
```

### Response

```json
{
  "drive_file_id": "DF-0001",
  "drive_file_version_id": "DFV-0001",
  "canonical_ref": "drv:ORG-0001:DF-0001",
  "status": "active"
}
```

---

## 4.2 `replace_drive_file_version`

### Purpose

Replace the current version of a governed file in a version-safe way.

### Request

```json
{
  "drive_file_id": "DF-0001",
  "new_file_artifact": {
    "file_id": "FILE-0002",
    "filename_original": "essay_v2.docx",
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "size_bytes": 545000,
    "content_hash": "sha256..."
  },
  "reason": "replace"
}
```

### Required behavior

* validates actor can replace for this owner/slot/context
* increments version
* marks old current version non-current
* preserves same governed file identity

### Response

```json
{
  "drive_file_id": "DF-0001",
  "drive_file_version_id": "DFV-0002",
  "current_version_no": 2,
  "status": "active"
}
```

---

# 5. Domain wrapper APIs

These exist so Ifitwala_Ed does not have to reconstruct governance payloads everywhere.

They are thin workflow-aware wrappers around the canonical Drive services.

## 5.1 `upload_task_resource`

### Purpose

Upload or register a resource attached to a Task.

### Required request shape

```json
{
  "task": "TASK-0001",
  "row_name": "optional-existing-attached-document-row",
  "filename_original": "worksheet.pdf",
  "mime_type_hint": "application/pdf",
  "expected_size_bytes": 123456
}
```

### Governance implied by wrapper

* owner_doctype = `Task`
* owner_name = task id
* attached_doctype/name = `Task` / task id in the compatibility slice
* primary_subject = owning organization derived from `Task.default_course -> Course.school -> School.organization`
* slot = `supporting_material__<row_name>`
* purpose/data_class/retention derived server-side

### Response

Upload session metadata including the authoritative `row_name` / slot for the compatibility attachment row.

---

## 5.2 `upload_task_submission_artifact`

### Purpose

Upload a student submission artifact.

This must preserve the locked task submission semantics:

* file is evidence of work
* not the grade
* slot is mandatory
* primary subject is student
* deletion must not break grades/analytics.

### Required request shape

```json
{
  "task_submission": "TSUB-0001",
  "student": "STU-0001",
  "slot": "submission",
  "filename_original": "essay.docx",
  "mime_type_hint": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "expected_size_bytes": 543210
}
```

### Response

Upload session or finalized Drive file artifact depending on flow stage.

---

## 5.3 `upload_applicant_document`

### Purpose

Upload an admissions document.

Must preserve the locked ownership rule:

* owner is `Student Applicant`
* never Student
* never Guardian.

### Request

```json
{
  "student_applicant": "APP-0001",
  "slot": "identity_passport",
  "filename_original": "passport.pdf",
  "mime_type_hint": "application/pdf",
  "expected_size_bytes": 222222
}
```

### Response

Upload session or finalized Drive file artifact.

---

## 5.4 `upload_portfolio_evidence`

### Purpose

Upload portfolio/journal artifact.

### Request

```json
{
  "portfolio_entry": "PORT-0001",
  "student": "STU-0001",
  "slot": "portfolio_artefact",
  "filename_original": "reflection.jpg",
  "mime_type_hint": "image/jpeg",
  "expected_size_bytes": 111111
}
```

---

## 5.5 `upload_organization_media`

### Purpose

Upload organization/school reusable media.

Must preserve:

* organization-owned media
* school optional
* reuse-first behavior
* no side media governance system.

### Request

```json
{
  "organization": "ORG-0001",
  "school": "SCH-0001",
  "slot": "organization_media__homepage_hero",
  "filename_original": "hero.jpg",
  "mime_type_hint": "image/jpeg",
  "expected_size_bytes": 333333
}
```

---

# 6. Browse / search APIs

These power the secondary Drive surface and reuse flows.

## 6.1 `list_folder_items`

### Purpose

List folders/files within a Drive folder.

### Request

```json
{
  "folder": "FOLDER-0001",
  "include_folders": 1,
  "include_files": 1,
  "limit": 50,
  "offset": 0
}
```

### Response

```json
{
  "folder": {
    "id": "FOLDER-0001",
    "title": "Course Resources",
    "path_cache": "org-0001/course-resources",
    "context_path": "Organization / Course Resources",
    "breadcrumbs": [
      {
        "id": "FOLDER-ROOT",
        "title": "Organization",
        "path_cache": "org-0001"
      },
      {
        "id": "FOLDER-0001",
        "title": "Course Resources",
        "path_cache": "org-0001/course-resources"
      }
    ]
  },
  "items": [
    {
      "item_type": "folder",
      "id": "FOLDER-0002",
      "title": "Week 1",
      "path_cache": "org-0001/course-resources/week-1",
      "context_path": "Organization / Course Resources / Week 1"
    },
    {
      "item_type": "file",
      "id": "DF-0001",
      "title": "worksheet.pdf",
      "binding_role": "task_resource",
      "preview_status": "ready",
      "canonical_ref": "drv:ORG-0001:DF-0001",
      "folder_path": "org-0001/course-resources",
      "context_path": "Organization / Course Resources",
      "can_preview": true,
      "can_download": true
    }
  ]
}
```

---

## 6.2 `list_context_files`

### Purpose

List governed file artifacts bound to a given business context.

This is the main context-first retrieval API.

### Request

```json
{
  "doctype": "Task Submission",
  "name": "TSUB-0001",
  "binding_role": "submission_artifact"
}
```

### Response

```json
{
  "context": {
    "doctype": "Task Submission",
    "name": "TSUB-0001"
  },
  "folders": [],
  "files": [
    {
      "id": "DF-0001",
      "drive_file_id": "DF-0001",
      "canonical_ref": "drv:ORG-0001:DF-0001",
      "slot": "submission",
      "title": "essay.docx",
      "current_version_no": 2,
      "preview_status": "pending",
      "folder_path": "student/task-0001/submissions",
      "context_path": "Student / TASK-0001 / Submissions",
      "attached_to": {
        "doctype": "Task Submission",
        "name": "TSUB-0001"
      },
      "can_preview": false,
      "can_download": true
    }
  ],
  "items": [
    {
      "id": "DF-0001",
      "drive_file_id": "DF-0001",
      "canonical_ref": "drv:ORG-0001:DF-0001",
      "slot": "submission",
      "title": "essay.docx",
      "current_version_no": 2,
      "preview_status": "pending",
      "folder_path": "student/task-0001/submissions",
      "context_path": "Student / TASK-0001 / Submissions",
      "attached_to": {
        "doctype": "Task Submission",
        "name": "TSUB-0001"
      },
      "can_preview": false,
      "can_download": true,
      "item_type": "file"
    }
  ]
}
```

`folders` and `items` are additive browse projections.
`files` remains the binding-centric file list for compatibility with existing consumers.
Folder-structured contexts such as `Employee`, `Student Applicant`, or `Task` may populate `folders` and include folder rows in `items`.

---

## 6.3 `search_drive_files`

### Purpose

Search files across an authorized Drive surface.

This should stay narrow in v1.
Not a full enterprise search engine.

### Request

```json
{
  "query": "worksheet",
  "folder": "optional-folder-id",
  "binding_role": "task_resource",
  "limit": 25
}
```

---

# 7. Access / grant APIs

## 7.1 `issue_download_grant`

### Purpose

Return a short-lived download grant for a Drive file.

### Request

```json
{
  "drive_file_id": "DF-0001"
}
```

### Response

```json
{
  "grant_type": "signed_url or private_url",
  "url": "short-lived-download-url",
  "expires_on": "2026-03-17 10:10:00"
}
```

Must enforce:

* user can see owning doc
* user can download in this context
* file is `active`

---

## 7.2 `issue_preview_grant`

### Purpose

Return a short-lived preview grant.

### Request

```json
{
  "drive_file_id": "DF-0001"
}
```

### Response

```json
{
  "grant_type": "signed_url or private_url",
  "url": "short-lived-preview-url",
  "expires_on": "2026-03-17 10:10:00",
  "preview_status": "ready"
}
```

Must enforce:

* user can see owning doc
* file is `active`
* `preview_status` is `ready`

---

# 8. Erasure APIs

These can stay admin/system-facing in v1.

## 8.1 `create_drive_erasure_request`

### Purpose

Create a file-domain erasure request by subject/scope.

### Request

```json
{
  "data_subject_type": "student",
  "data_subject_id": "STU-0001",
  "scope": "files_only",
  "request_reason": "GDPR request"
}
```

---

## 8.2 `execute_drive_erasure_request`

### Purpose

Execute erasure once approved.

### Response should include:

* deleted count
* blocked count
* slots touched
* final status

This must preserve the minimal-audit/no-content-remnant posture already locked in your GDPR notes.

---

# 9. What Ifitwala_Ed stores after calling Drive

Ifitwala_Ed should primarily store:

* `drive_file_id`
* `drive_file_version_id` where useful
* `canonical_ref`
* binding-level metadata if needed

It should **not** depend on:

* raw storage paths
* `/public` or `/private` paths
* bucket keys
* generic attachment URL guessing.

---

# 10. What is intentionally postponed

Not in the first contract:

* generalized external guest links
* collaborative docs
* public sharing engine
* deep permission graph system
* advanced search/indexing
* massive preview matrix
* all domains at once

The first target remains:

* task resources
* task submissions
* applicant documents
* organization media
* basic folders/browse.

---

# 11. Implementation note

The `api/*` modules should stay thin and delegate to services:

* `api/uploads.py`
* `api/resources.py`
* `api/submissions.py`
* `api/admissions.py`
* `api/media.py`
* `api/access.py`
* `api/folders.py`

while the real logic lives in:

* `services/uploads/`
* `services/files/`
* `services/governance/`
* `services/storage/`
* `services/access/`
* `services/integration/`
