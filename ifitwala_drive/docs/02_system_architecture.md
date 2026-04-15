# System architecture

## High-level split

### Ifitwala_Ed

Owns:

* academic workflows
* admissions workflows
* task/submission/business context
* portfolio, applicant, employee, referral, etc.

### Ifitwala_drive

Owns:

* governed upload sessions
* file classification
* slots
* versions
* canonical references
* file routing/storage abstraction
* preview state
* derivative state
* erasure state
* audit events

### Ifitwala_Press

Owns later:

* tenant/container provisioning
* bucket bindings
* quota/cost monitoring
* worker topology
* lifecycle and ops

This matches both your current direction and the existing architecture note that physical storage may later separate from app runtime and DB without changing the business contract.

## Deployment shape for early phase

Because you want low cost and demo customers first:

* one tenant/site
* one DB
* one Redis
* one paired container image or paired deployment containing:

  * `ifitwala_ed`
  * `ifitwala_drive`

But the architecture must preserve later separation of:

* app runtime,
* DB,
* storage bucket,
* workers.

That is already in your locked storage-boundary thinking.

## Core design rule

**All new governed file writes go through Ifitwala_drive APIs.**

The old rule remains:

> all file writes go through the dispatcher; direct `File.insert()` in business logic is an architectural violation.

In the new architecture, the “dispatcher” becomes the Drive service boundary.

## Domain model

Recommended core doctypes/services for Ifitwala_drive:

### `Drive File`

The user-facing governed file record.

Fields conceptually include:

* current file/version pointer
* owning doctype / docname
* organization
* school
* slot
* classification
* purpose
* primary subject
* status
* current preview status
* current malware/validation state

Current implemented shape also includes:

* `current_version_no`
* `current_version`
* `legal_hold`
* `erasure_state`
* canonical `storage_object_key`

This means Drive File now carries both the active version pointer and the minimum erasure posture needed for deterministic file-domain erasure.

### `Drive File Classification`

This should preserve your current 1:1 classification concept, or absorb it as Drive’s canonical metadata layer.

Your existing required fields already include:

* attached_doctype
* attached_name
* primary_subject_type / id
* data_class
* purpose
* retention_policy
* slot
* organization
* school
* legal_hold
* erasure_state
* version_number
* source_file
* content_hash
* upload_source
* ip_address.

### `Drive Upload Session`

First-class resumable upload/session object.

Needed for:

* large files
* unstable school networks
* student interruptions
* multi-part uploads
* retries

### `Drive Version`

Immutable version row.
Keep versioning per slot. That matches your current architecture.

Current implementation note:

* governed finalize creates `version_no = 1`
* replacements append a new immutable `Drive File Version`
* `Drive File.current_version` and `current_version_no` advance without changing the governed file identity

### `Drive Processing Job`

Tracks:

* preview generation
* derivative generation
* validation/scanning
* indexing
* reconciliation

### `Drive Access Event`

Audit/event log for:

* upload
* replace
* download grant
* preview access
* delete
* erasure action

Current implementation now records minimal audit events for:

* upload
* replace
* download grant issuance
* preview grant issuance
* erase

This is intentionally compact audit, not a second workflow engine.

### `Drive Erasure Request`

File-domain erasure request object.

Current implementation supports:

* subject-scoped request creation
* execution after approval
* deterministic deletion across all stored versions for a governed file
* blocked execution when `legal_hold` is active
* result counters for deleted vs blocked files

### `Drive Resource Binding`

Useful as explicit bindings for:

* task resource
* lesson resource
* submission artifact
* applicant document
* portfolio evidence
* organization media

## Documentation and downstream coordination rule

Whenever Drive behavior changes, the relevant docs must be updated with:

* the technical behavior change
* the design or architecture decision behind it
* any downstream impact on Ifitwala_Ed

If the change affects file delivery semantics for Ifitwala_Ed, that downstream app must be informed explicitly. This is part of the engineering contract, not release polish.

## Slot model

Do not weaken this.
Slots are one of the strongest parts of your current governance model.

Files are identified semantically by slots such as:

* `submission`
* `feedback`
* `rubric_evidence`
* `identity_passport`
* `portfolio_artefact`
* `school_logo__<school>`
* `organization_media__<media_key>`

Slot rules control:

* replacement vs multiplicity
* versioning
* retention
* deletion scope
* auditability

## Folder/navigation model

You want real folder navigation, so include it.
But folders must remain subordinate to governance, not the source of truth.

Recommended:

* folders for browse/search UX
* resources can live in navigable teacher/team/shared areas
* actual compliance semantics still come from:

  * owning document
  * subject
  * slot
  * classification
  * retention

In other words:

* folders are a navigation aid,
* not the legal/semantic authority.

## Template distribution model

For “copy blank template to a whole student group,” use:

* template resource
* per-student work item/workspace
* lazy derivative creation only when needed

Do not force immediate physical duplication of every blob for every student unless there is a hard product need.
