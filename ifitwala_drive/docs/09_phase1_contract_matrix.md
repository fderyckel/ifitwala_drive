# Phase 1 Contract Matrix

This matrix locks the first four governed integrations against the live `ifitwala_ed` codebase before broader Phase 1 cutover work continues.

Checked live sources:

* `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/assessment/task_submission_service.py`
* `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/assessment/doctype/task_submission/task_submission.json`
* `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/utilities/governed_uploads.py`
* `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/admission/admissions_portal.py`
* `/Users/francois.de/Documents/ifitwala_ed/ifitwala_ed/utilities/organization_media.py`

## Task Submission

| Field | Locked value |
| --- | --- |
| Ed entry point | `ifitwala_drive.api.submissions.upload_task_submission_artifact` |
| Owner doctype/name | `Task Submission` / `task_submission.name` |
| Attached doctype/name | `Task Submission` / `task_submission.name` |
| Primary subject | `Student` / `Task Submission.student` |
| Slot | `submission` |
| Data class | `assessment` |
| Purpose | `assessment_submission` |
| Retention policy | `until_school_exit_plus_6m` |
| Organization | derived from `School.organization` |
| School | `Task Submission.school` |
| Binding role target | `submission_artifact` |
| Current Ed canonical persistence | transitional `Task Submission.attachments` row using `Attached Document.file` |
| Transitional display field | same `attachments.file` URL |
| Create-session permission check | `Task Submission.check_permission("write")` |
| Finalize permission check | re-check `Task Submission.check_permission("write")` |
| Idempotency stance | not yet locked in Drive; required before SPA/Desk shared client rollout |
| Replace/version semantics | versioned slot, later refinement through Drive identity/binding completion |

Notes:

* Live `ifitwala_ed` code still contains drift in the legacy path: `data_class = academic` and `retention_policy = until_program_end_plus_1y`.
* Drive Phase 1 uses the doc-locked contract above and rejects mismatched task-submission context.

## Task Resource

| Field | Locked value |
| --- | --- |
| Current Ed surface | `Task.attachments` child table |
| Owner doctype/name | `Task` / `task.name` |
| Attached doctype/name | compatibility slice: `Task` / `task.name` |
| Primary subject | compatibility slice: `Organization` / `Task.default_course.school.organization` |
| Slot | compatibility slice: `supporting_material__<attached_document_row_name>` |
| Binding role target | `task_resource` |
| Current Ed canonical persistence | Drive-owned file plus `Task.attachments` display row |
| Plan status | compatibility cut shipped; dedicated task-resource schema still pending |

Notes:

* `Task.attachments` is still a generic `Attached Document` table in live Ed.
* The current implementation treats that table as compatibility metadata only; governance truth stays in Drive.
* The long-term target is still a dedicated Task-resource schema that can persist canonical Drive refs directly.

## Applicant Document

| Field | Locked value |
| --- | --- |
| Ed entry point | `ifitwala_ed.admission.admissions_portal.upload_applicant_document` |
| Owner doctype/name | `Student Applicant` / `Applicant Document.student_applicant` |
| Attached doctype/name | `Applicant Document Item` / `Applicant Document Item.name` |
| Primary subject | `Student Applicant` / `Applicant Document.student_applicant` |
| Slot | deterministic `slot_spec['slot'] + '_' + scrub(item_key)` |
| Data class | derived from `get_applicant_document_slot_spec(...)` |
| Purpose | derived from `get_applicant_document_slot_spec(...)` |
| Retention policy | derived from `get_applicant_document_slot_spec(...)` |
| Organization | `Student Applicant.organization` |
| School | `Student Applicant.school` |
| Binding role target | `applicant_document` |
| Current Ed canonical persistence | `Applicant Document Item` attachment plus `File Classification` |
| Transitional display field | returned `file_url` only |
| Create-session permission check | applicant-document authority, to be wrapped in Drive |
| Finalize permission check | applicant-document authority, to be wrapped in Drive |
| Idempotency stance | existing `client_request_id` cache/lock behavior must be preserved |
| Replace/version semantics | item-scoped replace with review reset semantics |

## Organization Media

| Field | Locked value |
| --- | --- |
| Ed entry points | `upload_organization_logo`, `upload_school_logo`, `upload_school_gallery_image`, `upload_organization_media_asset` |
| Owner doctype/name | `Organization` / `organization.name` |
| Attached doctype/name | `Organization` / `organization.name` |
| Primary subject | `Organization` / `organization.name` |
| Slot | `organization_media__<media_key>`, `school_logo__<school>`, `organization_logo__<organization>`, `school_gallery_image__<row_name>` |
| Data class | `ORGANIZATION_MEDIA_DATA_CLASS` |
| Purpose | `ORGANIZATION_MEDIA_PURPOSE` |
| Retention policy | `ORGANIZATION_MEDIA_RETENTION_POLICY` |
| Organization | authoritative owner `Organization.name` |
| School | optional scope only |
| Binding role target | `organization_media` |
| Current Ed canonical persistence | governed file plus compatibility URL fields on consumers |
| Transitional display field | consumer URL fields such as `organization_logo`, `school_logo`, `school_image`, `hero_image` |
| Create-session permission check | `Organization` or `School` write authority |
| Finalize permission check | same governing owner/scope authority |
| Idempotency stance | not yet explicit in Drive; consumer selection is reuse-first |
| Replace/version semantics | slot-scoped replacement |

## Employee Image

| Field | Locked value |
| --- | --- |
| Ed entry point | `ifitwala_ed.utilities.governed_uploads.upload_employee_image` |
| Owner doctype/name | `Employee` / `employee.name` |
| Attached doctype/name | `Employee` / `employee.name` |
| Primary subject | `Employee` / `employee.name` |
| Slot | `profile_image` |
| Data class | `identity_image` |
| Purpose | `employee_profile_display` |
| Retention policy | `employment_duration_plus_grace` |
| Organization | `Employee.organization` |
| School | `Employee.school` |
| Binding role target | `employee_image` |
| Current Ed canonical persistence | `Employee.employee_image` URL field |
| Transitional display field | `employee_image` |
| Create-session permission check | `Employee.check_permission("write")` |
| Finalize permission check | re-check `Employee.check_permission("write")` |
| Replace/version semantics | slot-scoped replacement |

## Student Image

| Field | Locked value |
| --- | --- |
| Ed entry point | `ifitwala_ed.utilities.governed_uploads.upload_student_image` |
| Owner doctype/name | `Student` / `student.name` |
| Attached doctype/name | `Student` / `student.name` |
| Primary subject | `Student` / `student.name` |
| Slot | `profile_image` |
| Data class | `identity_image` |
| Purpose | `student_profile_display` |
| Retention policy | `until_school_exit_plus_6m` |
| Organization | derived from `Student.anchor_school -> School.organization` |
| School | `Student.anchor_school` |
| Binding role target | `student_image` |
| Current Ed canonical persistence | `Student.student_image` URL field |
| Transitional display field | `student_image` |
| Create-session permission check | `Student.check_permission("write")` |
| Finalize permission check | re-check `Student.check_permission("write")` |
| Replace/version semantics | slot-scoped replacement |
