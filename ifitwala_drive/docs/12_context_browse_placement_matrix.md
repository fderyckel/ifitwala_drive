# Context Browse Placement Matrix

## Status

Proposed.

This note turns the storage/navigation repair proposal into a concrete browse-placement matrix.

It does **not** redefine governance.

It defines where files should appear for humans, while preserving:

* one authoritative business-document owner
* slot semantics
* canonical Drive identity
* folders as navigation only

---

## Checked Sources

Repo-grounded sources checked for this matrix:

* [09_phase1_contract_matrix.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/09_phase1_contract_matrix.md)
* [11_storage_navigation_repair_proposal.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/11_storage_navigation_repair_proposal.md)
* [06_api_contracts.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/06_api_contracts.md)
* [00_discussions.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/00_discussions.md)
* [04_coupling_with_ifiwala_ed.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/04_coupling_with_ifiwala_ed.md)

Important:

* rows below use exact contracts where the repo already locks them
* where the repo does not yet lock owner or slot contracts, the matrix marks that explicitly instead of inventing them

---

## 1. Locked Or Near-Locked Browse Surfaces

These are ready enough to drive implementation planning now.

| Surface | Human semantic path | Authoritative owner | Binding role | Placement mode | Contract status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Applicant document | `Admissions / Applicant / <applicant> / Documents / Identity` or `Academic` | `Student Applicant` | `applicant_document` | system-managed | locked | Sub-bucket under `Documents` should come from the applicant document type classification, not user choice. |
| Applicant health vaccination proof | `Admissions / Applicant / <applicant> / Documents / Health` | `Student Applicant` | `applicant_document` | system-managed | near-locked | Health evidence should live under `Documents`, not as a separate top-level branch. |
| Applicant image | `Admissions / Applicant / <applicant> / Profile / Applicant Image` | `Student Applicant` | `general_reference` | system-managed | near-locked | Current admissions wrappers exist; a dedicated profile-image browse role may be added later, but is not locked yet. |
| Guardian image | `Admissions / Applicant / <applicant> / Profile / Guardian Images` | `Student Applicant` | `general_reference` | system-managed | near-locked | Images are profile media, not document rows. |
| Student image | `Student / <student> / Profile / Student Image` | `Student` | `student_image` | system-managed | locked | Existing contract already locks owner, slot `profile_image`, and `student_image` binding role. |
| Employee image | `Employees / <employee> / Profile / Employee Image` | `Employee` | `employee_image` | system-managed | locked | Implemented with an organization-rooted `Employees` tree and employee-owned `staff_documents` folders. |
| Task submission artifact | `Student / <student> / Academic Year / <year> / Courses / <course> / Tasks / <task> / Submissions` | `Task Submission` | `submission_artifact` | system-managed projection | locked | Must also be reachable from the task and submission surfaces without duplicating the blob. |
| Task resource | `Course / <course> / Tasks / <task> / Resources` | `Task` | `task_resource` | system-managed | partially locked | Browse target is clear; attached target and slot contract remain blocked in the existing Phase 1 matrix. |
| Organization logo/media | `Organization Media / Organization / Logos` or `Public Media` | `Organization` | `organization_media` | system-managed plus reuse-first selection | locked | Existing organization-media contract already forbids a parallel media governance system. |
| School logo/media | `Organization Media / Schools / <school> / Logos` or `Campus Media` | `Organization` with optional school scope | `organization_media` | system-managed plus reuse-first selection | locked | School-scoped items should still resolve through organization-owned media governance. |
| Portfolio or journal evidence | `Portfolio / <student> / <year> / Journal` or `Reflections` or `Evidence` | blocked pending Ed contract lock | `portfolio_evidence` | system-managed projection | partially locked | API contracts already mention `upload_portfolio_evidence(...)` and slot `portfolio_artefact`, but the authoritative Ed owner record still needs to be locked against live code. |
| Lesson resource | `Course / <course> / Lessons / <lesson> / Resources` | `Lesson` | `lesson_resource` | system-managed | concept locked, implementation blocked | `00_discussions.md` already uses lesson ownership as an example, but the concrete Ed contract is not yet wired in Drive. |
| Lesson activity resource | `Course / <course> / Lessons / <lesson> / Activities / <activity> / Resources` | `Lesson Activity` | `lesson_activity_resource` | system-managed | concept locked, implementation blocked | Same rule: clear browse path, but contract still needs an Ed-grounded matrix row. |

---

## 2. Required Student-Centric Projections

These are not separate governance roots.

They are the human views that should be generated from owner + binding + slot + context.

| Projection surface | Human semantic path | Backing records | Placement mode | Notes |
| --- | --- | --- | --- | --- |
| Student overview | `Student / <student>` | `Student`, `Drive Binding`, related governed owners | derived projection | A student home should aggregate image, current-year evidence, recent submissions, and key portfolio items. |
| Academic year view | `Student / <student> / Academic Year / <year>` | year-scoped bindings across task, portfolio, activities | derived projection | Year is a retrieval axis, not necessarily the owner. |
| Course view | `Student / <student> / Academic Year / <year> / Courses / <course>` | task resources, submissions, lesson resources, reflections | derived projection | One file may appear here and also in task or portfolio views. |
| Task view | `Student / <student> / Academic Year / <year> / Courses / <course> / Tasks / <task>` | `Task`, `Task Submission`, feedback and rubric evidence when governed | derived projection | This is where users should find the complete task evidence chain. |
| Reflection view | `Student / <student> / Academic Year / <year> / Reflections` | portfolio/journal records once locked | derived projection | Keep this separate from course-specific journals when the business meaning differs. |
| Activity view | `Student / <student> / Academic Year / <year> / Activities / <activity>` | activity participation and certificate records once locked | derived projection | Certificates and media should appear here without creating a second owner model. |

---

## 3. Human-Semantic Work Libraries

These should exist because people also need work-oriented retrieval, not only ERP context retrieval.

| Work surface | Human semantic path | Backing logic | Placement mode | Notes |
| --- | --- | --- | --- | --- |
| Teacher personal library | `Teacher / <teacher> / My Resources` | files bound to teaching contexts and personal reusable collections | user-choosable within governed limits | This is a work surface, not an owner tree. |
| Shared course library | `Teacher / <teacher> / Shared Course Resources` or `Course / <course> / Resources` | `task_resource`, `lesson_resource`, reusable governed resources | mixed | Reuse-first behavior matters here. |
| Reusable templates | `Teacher / <teacher> / Reusable Templates` | template-class resources once contract is locked | mixed | Do not duplicate blobs per student until needed. |
| Drive home | `Workspaces / Home` | readable review assignments, own readable contexts, readable root folders | derived saved view plus root browse | Current landing groups targets into `Reviewing`, `My Drive`, and `Folders`, and may auto-open a single readable target. |
| Recent uploads | `Workspaces / Recent` | recent Drive activity by authorized context | derived saved view | This is a convenience surface only. |
| Needs review | `Workspaces / Needs Review` | workflow-state-driven bindings | derived saved view | This should be built from workflow metadata, not folder placement. |
| Shared with me | `Workspaces / Shared With Me` | permission-resolved bindings across visible contexts | derived saved view | Keep it rooted in owning-document visibility; do not create a detached ACL model. |

---

## 4. Surfaces We Should Support But Must Not Fake Yet

These are important, but the underlying Ed contract is not yet locked enough in this repo to assign exact owners, slots, or binding roles.

| Surface | Human semantic path | What is still blocked | Recommendation |
| --- | --- | --- | --- |
| Course-level reflections outside portfolio | `Student / <student> / Academic Year / <year> / Courses / <course> / Reflections` | exact owner record in Ed, exact binding role, exact slot taxonomy | Keep as a required browse projection, but lock the Ed owner contract first. |
| Year-level reflections outside course | `Student / <student> / Academic Year / <year> / Reflections` | whether this is portfolio, journal, advisory, or another record type | Do not invent a second reflection governance system. |
| Activity certificates | `Student / <student> / Academic Year / <year> / Activities / <activity> / Certificates` | authoritative owner doctype, slot contract, replace/version semantics | Lock against the actual activity/certificate record before implementation. |
| Activity media/evidence | `Student / <student> / Academic Year / <year> / Activities / <activity> / Media` | owner model and privacy/public rules | Do not let gallery-style browsing weaken private-by-default governance. |
| Staff governed documents beyond images | `Employees / <employee> / Documents / Identity` or `HR` or `Compliance` | exact Ed contract, slot taxonomy, attached-field behavior | Use the same document/profile split as admissions once the Ed records are checked. |

---

## 5. Placement Rules

Across all rows, placement should follow these rules:

1. Workflow-bound uploads default to system-managed placement.
2. Reusable library surfaces may allow user-chosen folders, but only within an authorized context root.
3. One file may appear in multiple human views through bindings and projections.
4. Physical object keys never define the human browse path.
5. Folder moves must not rewrite governance truth.
6. If the owner, slot, or context cannot be proven, placement fails closed.

---

## 6. Immediate Next Matrix To Lock In Code

If implementation starts now, the first concrete placement matrix to wire should be:

1. admissions applicant documents, health, applicant image, guardian image
2. student image
3. task submissions
4. organization and school media
5. task resources
6. portfolio or journal evidence

That order keeps the work aligned with existing repo contracts while expanding human findability quickly.

The corresponding execution artifact is [13_first_slice_implementation_checklist.md](/Users/francois.de/Documents/ifitwala_drive/ifitwala_drive/docs/13_first_slice_implementation_checklist.md).
