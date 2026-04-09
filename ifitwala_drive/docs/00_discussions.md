Below is the working draft I would use for **Ifitwala_drive**.

---

# `AGENTS.md`

```md
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
- file classification
- slot enforcement
- version lineage
- canonical references
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
- `finalize_upload(...)`
- `create_and_classify_file(...)`
- `replace_version(...)`

This preserves the existing locked dispatcher-only architecture. Any business flow bypassing it is a bug.  See the governance notes: all file writes go through the dispatcher; direct `File.insert()` in business logic is forbidden, and hooks must remain “dumb” finalizers only.

### 2.2 No file becomes meaningful without governance metadata

A file must not be finalized without classification metadata.

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

This is already locked in the existing `File Classification` contract and must remain true in Ifitwala_drive.

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

### 4.2 Preserve current governance intent
If refactoring from Ifitwala_Ed into Ifitwala_drive, preserve:
- dispatcher-only discipline
- classification invariants
- erasure posture
- canonical URL discipline
- ownership rules for tasks, admissions, portfolio, organization media

### 4.3 Legacy tolerance
The system may tolerate legacy unclassified files temporarily, but no new governed flow may rely on them. This is already locked as a production-safe migration rule. :contentReference[oaicite:7]{index=7}

### 4.4 Async by default for heavy work
Never block hot user flows on:
- preview generation
- derivatives
- scans
- indexing
- reconciliation

### 4.5 Fail closed
If a file cannot be proven governed, routable, and policy-valid, stop. Do not silently fall back to generic attach behavior.

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
```

---

# Exact v1 DocTypes for `ifitwala_drive`

I would keep v1 **lean but strict**.

## 1. `Drive File`

**Purpose:** authoritative governed file record for Drive.
This becomes the main domain object instead of exposing raw `File` as the product object.

### Core fields

* `file` → Link to `File` (required, unique for current active record)
* `attached_doctype` (Data, required)
* `attached_name` (Data, required)
* `organization` (Link → Organization, required)
* `school` (Link → School, optional when valid by policy)
* `primary_subject_type` (Select / Link contract, required)
* `primary_subject_id` (Dynamic Link, required)
* `data_class` (Select, required)
* `purpose` (Select, required)
* `retention_policy` (Select, required)
* `retention_until` (Date, computed later)
* `slot` (Data, required)
* `folder` (Link → Drive Folder, optional for browse UX)
* `current_version_no` (Int)
* `current_version` (Link → Drive File Version)
* `status` (Select: `active`, `processing`, `blocked`, `erased`, `superseded`)
* `preview_status` (Select)
* `processing_status` (Select)
* `legal_hold` (Check)
* `erasure_state` (Select: `active`, `pending`, `blocked_legal`, `erased`)
* `canonical_ref` (Data / generated stable identifier)
* `canonical_url` (Data, optional cached safe URL for renderable public cases only)
* `upload_source` (Select: `Desk`, `SPA`, `API`, `Job`)
* `created_via` (Data, optional method name)
* `content_hash` (Data, sha256)
* `is_private` (Check)

### Child table

* `Drive File Subject`

  * `subject_type`
  * `subject_id`
  * `role` (`co-owner`, `referenced`, `contextual`)

### Why this exists

This preserves the existing classification/subject contract while making it a first-class Drive domain object instead of a bolt-on to generic `File`. The existing required classification fields and secondary-subject model are already locked.

---

## 2. `Drive File Version`

**Purpose:** immutable file lineage/version rows.

### Core fields

* `drive_file` (Link → Drive File, required)
* `version_no` (Int, required)
* `file` (Link → File, required)
* `source_version` (Link → Drive File Version, optional)
* `source_file` (Link → File, optional)
* `is_current` (Check)
* `version_reason` (Select: `initial_upload`, `replace`, `derivative`, `system_regeneration`)
* `size_bytes` (Int)
* `mime_type` (Data)
* `content_hash` (Data)
* `created_by` (Link → User)
* `created_on` (Datetime)
* `processing_status` (Select)
* `preview_status` (Select)

### Why

Slots are versioned, and replacement behavior must be explicit. Task `submission`, `feedback`, and other slots are already defined as versioned in your examples.

---

## 3. `Drive Upload Session`

**Purpose:** authoritative upload lifecycle object for resumable/multipart flows.

### Core fields

* `session_key` (Data, unique)
* `attached_doctype` (Data, required)
* `attached_name` (Data, required)
* `intended_primary_subject_type` (Data, required)
* `intended_primary_subject_id` (Data, required)
* `intended_data_class` (Data, required)
* `intended_purpose` (Data, required)
* `intended_retention_policy` (Data, required)
* `intended_slot` (Data, required)
* `organization` (Link → Organization, required)
* `school` (Link → School)
* `folder` (Link → Drive Folder)
* `status` (`created`, `uploading`, `uploaded`, `finalizing`, `completed`, `aborted`, `expired`)
* `storage_backend` (Data)
* `storage_key_tmp` (Data)
* `expected_size_bytes` (Int)
* `received_size_bytes` (Int)
* `mime_type_hint` (Data)
* `filename_original` (Data)
* `expires_on` (Datetime)
* `created_by` (Link → User)
* `upload_source` (Select)
* `request_ip` (Data)

### Why

You want lower-friction uploads and future high concurrency. This object is the clean place to put resumable-upload logic without contaminating business DocTypes.

---

## 4. `Drive Folder`

**Purpose:** navigable Drive/browser surface.

### Core fields

* `title` (Data, required)
* `parent_folder` (Link → Drive Folder)
* `organization` (Link → Organization, required)
* `school` (Link → School)
* `folder_kind` (Select: `teacher_private`, `course_shared`, `organization_media`, `system_bound`, `student_workspace`, `applicant_docs`)
* `owner_user` (Link → User)
* `context_doctype` (Data)
* `context_name` (Data)
* `is_system_managed` (Check)
* `path_cache` (Data)
* `depth` (Int)
* `status` (Select)
* `visibility_scope` (Data / enum later)

### Why

You asked for real folder navigation. But folders are a browse surface, not the governance truth. Keep that distinction explicit.

---

## 5. `Drive Binding`

**Purpose:** explicit binding between a Drive file and an Ifitwala_Ed domain use.

### Core fields

* `drive_file` (Link → Drive File, required)
* `binding_doctype` (Data, required)
* `binding_name` (Data, required)
* `binding_role` (Select: `task_resource`, `submission_artifact`, `feedback_attachment`, `applicant_document`, `portfolio_evidence`, `organization_media`, `employee_image`, `student_image`)
* `slot` (Data, required)
* `is_primary` (Check)
* `sort_order` (Int)

### Why

This keeps contextual UX clean and avoids overloading one file row with all UI binding semantics.

---

## 6. `Drive Processing Job`

**Purpose:** async job state for previews, derivatives, scans, indexing.

### Core fields

* `drive_file` (Link → Drive File)
* `drive_file_version` (Link → Drive File Version)
* `job_type` (`preview`, `derivative`, `scan`, `index`, `reconcile`)
* `status` (`queued`, `running`, `failed`, `completed`, `blocked`)
* `queue_name` (`drive_short`, `drive_default`, `drive_heavy`)
* `attempt_count` (Int)
* `error_log` (Small Text)
* `payload_json` (Code / JSON)
* `started_on` (Datetime)
* `finished_on` (Datetime)

### Why

Keeps hot upload paths cheap and lets you grow processing safely.

---

## 7. `Drive Access Event`

**Purpose:** minimal audit of file actions.

### Core fields

* `drive_file` (Link → Drive File)
* `drive_file_version` (Link → Drive File Version)
* `event_type` (`upload`, `replace`, `download_grant`, `preview_open`, `delete`, `erase`, `bind`, `unbind`)
* `actor` (Link → User)
* `request_ip` (Data)
* `event_on` (Datetime)
* `metadata_json` (Code / JSON)

### Why

You already want minimal but real audit, especially around erasure and access.

---

## 8. `Drive Erasure Request`

You already have a strong precedent from `Data Erasure Request`. I would mirror that but keep file-domain execution in Drive.

### Core fields

* `data_subject_type`
* `data_subject_id`
* `requested_by`
* `request_reason`
* `scope` (`all`, `files_only`, `slot_only`)
* `slot_filter` (optional)
* `status` (`draft`, `approved`, `executing`, `completed`, `blocked`)
* `executed_on`
* `result_deleted_count`
* `result_blocked_count`

### Why

Your current erasure workflow is already deterministic and file-centric enough that Drive should own execution, while Ifitwala_Ed keeps higher-level policy/legal UI if needed.

---

# Exact v1 service and module layout

I would keep the repo organized like this:

```text
ifitwala_drive/
  ifitwala_drive/
    hooks.py
    modules.txt

    api/
      __init__.py
      uploads.py
      resources.py
      submissions.py
      admissions.py
      media.py
      access.py
      folders.py

    drive/
      __init__.py

      doctype/
        drive_file/
          drive_file.json
          drive_file.py
          drive_file.js
          test_drive_file.py

        drive_file_subject/
          drive_file_subject.json
          drive_file_subject.py
          drive_file_subject.js
          test_drive_file_subject.py

        drive_file_version/
          drive_file_version.json
          drive_file_version.py
          drive_file_version.js
          test_drive_file_version.py

        drive_upload_session/
          drive_upload_session.json
          drive_upload_session.py
          drive_upload_session.js
          test_drive_upload_session.py

        drive_folder/
          drive_folder.json
          drive_folder.py
          drive_folder.js
          test_drive_folder.py

        drive_binding/
          drive_binding.json
          drive_binding.py
          drive_binding.js
          test_drive_binding.py

        drive_processing_job/
          drive_processing_job.json
          drive_processing_job.py
          drive_processing_job.js
          test_drive_processing_job.py

        drive_access_event/
          drive_access_event.json
          drive_access_event.py
          drive_access_event.js
          test_drive_access_event.py

        drive_erasure_request/
          drive_erasure_request.json
          drive_erasure_request.py
          drive_erasure_request.js
          test_drive_erasure_request.py

    services/
      __init__.py
      uploads/
        __init__.py
        sessions.py
        finalize.py
        validation.py

      files/
        __init__.py
        create.py
        versions.py
        bindings.py
        folders.py
        derivatives.py
        previews.py

      governance/
        __init__.py
        classification.py
        slots.py
        retention.py
        subjects.py
        organization_scope.py
        policy_checks.py

      storage/
        __init__.py
        base.py
        gcs.py
        local.py
        signed_urls.py
        keys.py

      access/
        __init__.py
        permissions.py
        grants.py
        downloads.py

      audit/
        __init__.py
        events.py
        erasure.py

      integration/
        __init__.py
        ifitwala_ed_tasks.py
        ifitwala_ed_admissions.py
        ifitwala_ed_portfolio.py
        ifitwala_ed_media.py

    jobs/
      __init__.py
      previews.py
      derivatives.py
      scans.py
      reconcile.py
      erasure.py

    utils/
      __init__.py
      hashing.py
      mime.py
      filenames.py
      paths.py
      query.py

    patches/
      txt/
      v1_initialize_drive_doctypes.py
      v1_seed_slot_and_purpose_contracts.py

    tests/
      test_task_submission_flow.py
      test_applicant_document_flow.py
      test_portfolio_flow.py
      test_organization_media_flow.py
      test_erasure_flow.py
      test_folder_visibility_flow.py
```

---

# What each layer should do

## `api/`

Thin whitelisted API surface only.

Examples:

* `uploads.py`

  * `create_upload_session`
  * `abort_upload_session`
  * `finalize_upload_session`
* `resources.py`

  * `attach_existing_resource`
  * `upload_task_resource`
* `submissions.py`

  * `upload_submission_artifact`
  * `replace_submission_artifact`
* `admissions.py`

  * `upload_applicant_document`
* `media.py`

  * `upload_organization_media`
  * `list_selectable_media`
* `access.py`

  * `issue_download_grant`
  * `issue_preview_grant`
* `folders.py`

  * `list_folder_items`
  * `create_folder`
  * `move_item`

These should be very thin and delegate immediately to services.

## `services/uploads/`

Responsible for upload-session lifecycle.
No business-specific semantics beyond validation of required governance payload.

## `services/files/`

Responsible for:

* creating Drive File + Drive File Version
* replacing versions
* binding/unbinding
* folder placement
* derivative/previews orchestration

This is the equivalent evolution of your current dispatcher and file management split. The current dispatcher responsibilities already include resolving org/school, enforcing slot rules, applying versioning, attaching to owner, and returning canonical records.

## `services/governance/`

This is the heart.

Responsible for:

* validating required classification contract
* slot behavior
* purpose/data_class validity
* organization/school scope checks
* retention rules
* subject rules
* ownership invariants

This preserves the strongest part of your current design.

## `services/storage/`

Abstracts physical storage.

Start with:

* `gcs.py` as strategic default
* `local.py` for dev fallback
* `signed_urls.py` for short-lived access

No caller outside this layer should build storage URLs.

## `services/access/`

Responsible for:

* checking if the actor can download/preview/replace/delete
* issuing short-lived grants
* enforcing private/public differences

Keep this simple and tightly tied to owning document visibility plus slot/action rules. Do not jump to externalized graph authorization yet.

## `services/integration/`

This is the “tight coupling without pollution” layer.

Adapters for Ifitwala_Ed workflows:

* tasks
* admissions
* portfolio/journal
* organization media

That makes the coupling explicit and keeps both apps honest.

## `jobs/`

Only heavy async work:

* previews
* derivatives
* scans if enabled
* reconciliation
* erasure execution

## `tests/`

End-to-end flow tests by domain, not just unit tests by helper.

That matters because your real risk is contract drift across layers.

---

# v1 API surface I would lock now

Keep it small.

## Upload/session APIs

* `create_upload_session(...)`
* `finalize_upload_session(...)`
* `abort_upload_session(...)`

## File creation APIs

* `create_and_classify_file(...)`
* `replace_drive_file_version(...)`

## Domain wrappers

* `upload_task_submission_artifact(...)`
* `upload_task_resource(...)`
* `upload_applicant_document(...)`
* `upload_portfolio_evidence(...)`
* `upload_organization_media(...)`

## Browse/search APIs

* `list_folder_items(...)`
* `list_context_files(...)`
* `search_drive_files(...)`

## Access APIs

* `issue_download_grant(...)`
* `issue_preview_grant(...)`

## Erasure APIs

* `create_drive_erasure_request(...)`
* `execute_drive_erasure_request(...)`

---

# Product-manager call: what to keep small in v1

Do **not** try to ship all of this at once.

The right v1 functional target is:

1. **Task resources**
2. **Task submissions**
3. **Applicant documents**
4. **Organization media**
5. **Basic Drive folders/browse for reusable resources**

Not yet:

* full collaborative docs
* massive preview matrix
* generalized public sharing
* generic external guest link system
* complex teacher team-sharing graphs

That is how you stay cost-conscious without painting yourself into a corner.

---

# My blunt recommendation on naming/migration

Because your current docs already use `File Classification` and dispatcher terminology, I would do this carefully:

* **Inside Ifitwala_drive v1**, keep compatibility with the existing `File Classification` mental model.
* Do **not** rename everything at once just because “Drive File” sounds cleaner.
* Let `Drive File` become the new domain shell, but preserve field names and invariants where practical to reduce migration risk.

That gives you continuity instead of unnecessary churn.

---

If you want, the next step should be the **exact JSON schema draft for the first 4 DocTypes**:

* `Drive File`
* `Drive File Version`
* `Drive Upload Session`
* `Drive Folder`

and I’ll include the minimal `.py`, `.js`, and test templates for each, since you explicitly want that in every DocType handoff.



Agreed. That is the correct correction.

The **owner must be the business document/context**, not the human who uploaded it and usually not the person the file is about.

So the rule should be:

* **creator/uploader** = who performed the action
* **data subject** = who the file is about
* **business owner** = the authoritative document that owns lifecycle
* **storage/governance authority** = Drive

Those are different things, and collapsing them would be a mistake.

## What this means in practice

A file should be owned by things like:

* `Lesson`
* `Lesson Activity`
* `Task`
* `Task Submission`
* `Policy Document`
* `Employee`
* `Student Applicant`
* `Student Portfolio Entry`
* `Student Referral`
* `Organization`
* `School`

Not by:

* the teacher who uploaded it
* the student who uploaded it
* the employee who created it
* the guardian who submitted it

Those people are:

* uploader
* creator
* submitter
* data subject
* reviewer

But not the lifecycle owner.

## Why this is the right rule

Because ownership must survive:

* staff turnover
* student graduation
* user deactivation
* role changes
* reassignment of work
* compliance and retention review

If ownership were tied to a person, the model would rot immediately.

A lesson resource does not stop belonging to the lesson because the teacher leaves.
An HR document does not belong to the HR officer who uploaded it.
A policy file does not belong to the staff member who edited it.
A submission artifact should belong to the submission record, not directly to the student as a person.

That is much cleaner.

## The refined ownership model

We should lock this:

### 1. Business owner

Exactly one authoritative **business document owner**.

Examples:

* lesson file → `Lesson`
* lesson activity worksheet → `Lesson Activity`
* task handout → `Task`
* student work artifact → `Task Submission`
* applicant passport → `Student Applicant`
* contract or personnel document → `Employee`
* policy PDF → `Institutional Policy`
* school logo/media → `Organization` or governed org-media record

### 2. Creator / uploader

The user who initiated the upload or creation.

This is audit metadata only:

* `created_by`
* `uploaded_by`

Never ownership.

### 3. Primary subject

Who the file is about.

Examples:

* employee contract → subject = Employee
* applicant passport → subject = Student Applicant
* student submission → subject = Student
* referral attachment → subject = Student

Subject is not ownership.

### 4. References / bindings

Other documents may reference the file, but references are not ownership.

For example:

* a portfolio entry may reference a task submission artifact
* a lesson may reuse a school resource
* a webpage may reference organization media

Still only one lifecycle owner.

## One nuance I would keep

You said “never the employee itself or the student itself.”

I agree for **student** almost completely.

For **employee**, I would be a bit more precise:

* **not the employee user/person**
* but **yes, the `Employee` business document can own employee records/files**

Because `Employee` in your ERP is not just a person; it is the authoritative HR record/document.

So:

* owner = `Employee` DocType → valid
* owner = actual human uploader/creator → invalid

That distinction matters.

Same for applicant:

* owner = `Student Applicant` DocType → valid
* owner = guardian user or family member → invalid

## Revised locked rule

I would rewrite it like this:

> Every governed file must have exactly one authoritative **business-document owner**.
> Ownership is never the human creator/uploader.
> The uploader, creator, and data subject are separate metadata roles.
> Other records may reference the file, but references do not become co-ownership.

That is the right version.

## Consequence for our earlier wording

So yes, I would correct the earlier statement from:

> one authoritative owner

to:

> one authoritative **business-document owner**

That is much better and much closer to your original intent.

## Good examples

### Correct

* worksheet PDF owned by `Lesson Activity`
* assessment rubric owned by `Task`
* student uploaded essay owned by `Task Submission`
* applicant transcript owned by `Student Applicant`
* teacher handbook owned by `Institutional Policy`
* contract PDF owned by `Employee`
* school logo owned by `Organization` or organization-media governing record

### Incorrect

* worksheet PDF owned by teacher user
* essay owned by student user
* transcript owned by guardian
* policy owned by HR manager who uploaded it

## What we should lock before continuing

We should update the architecture notes with this exact rule:

1. **Owner always means business-document owner.**
2. **Uploader/creator is audit metadata only.**
3. **Primary subject is the person/entity the file concerns, not the owner.**
4. **A file may be referenced by many records, but lifecycle ownership remains singular.**

That is the right correction.
