# Cross-Portal Governed Attachment Preview Contract

## Status

**Proposed canonical contract for cross-app implementation**

Date: 2026-04-16

Code refs:

- `ifitwala_drive/api/access.py`
- `ifitwala_drive/services/files/access.py`
- `ifitwala_drive/services/files/derivatives.py`
- `ifitwala_drive/services/files/versions.py`
- `ifitwala_drive/services/storage/base.py`
- `ifitwala_drive/services/storage/local.py`
- `ifitwala_drive/services/storage/gcs.py`
- `ifitwala_drive/ifitwala_drive/doctype/drive_file/drive_file.py`
- `ifitwala_drive/ifitwala_drive/doctype/drive_file/drive_file.json`
- `ifitwala_drive/ifitwala_drive/doctype/drive_file_derivative/drive_file_derivative.py`
- `ifitwala_drive/ifitwala_drive/doctype/drive_file_derivative/drive_file_derivative.json`
- `ifitwala_drive/ifitwala_drive/doctype/drive_file_version/drive_file_version.py`
- `ifitwala_drive/ifitwala_drive/doctype/drive_file_version/drive_file_version.json`
- `ifitwala_drive/ifitwala_drive/doctype/drive_processing_job/drive_processing_job.json`

Test refs:

- `ifitwala_drive/tests/test_access_grants.py`
- `ifitwala_drive/tests/test_drive_versioning_and_erasure.py`
- `ifitwala_drive/tests/test_browse_services.py`
- `ifitwala_drive/tests/test_local_storage_backend.py`
- `ifitwala_drive/tests/test_gcs_storage_backend.py`
- `ifitwala_drive/tests/test_preview_jobs.py`

Related docs:

- `ifitwala_drive/docs/02_system_architecture.md`
- `ifitwala_drive/docs/03_security_concurrency.md`
- `ifitwala_drive/docs/04_coupling_with_ifiwala_ed.md`
- `ifitwala_drive/docs/05_optionC_design_lock.md`
- `ifitwala_drive/docs/06_api_contracts.md`
- `../ifitwala_ed/docs/files_and_policies/files_08_cross_portal_governed_attachment_preview_contract.md`

## Bottom line

The proposal is mostly correct and should be kept as the target direction, but it needs four explicit corrections before it is safe to implement:

1. Drive access grants for Ed-owned portal surfaces are infrastructure endpoints, not direct SPA contracts.
2. Preview grants must resolve derivative artifacts tied to `Drive File Version`; the current file-level preview grant shape is not enough.
3. Derivatives must be modeled separately from original file versions; they must not masquerade as new current file versions or sibling governed files.
4. Current `preview_status` on `Drive File` is only a lightweight hint today. It is not a complete derivative lifecycle model.

Phase 1 scope must also stay tight:

- image thumbnail / preview
- optional PDF preview
- clean status lifecycle
- Org Communication first

Do not over-model early with broad media ambitions, many derivative roles, or video-specific logic before the first governed preview surface is working end to end.

## Current implemented baseline

Drive currently has:

- `Drive File` with a file-level `preview_status`
- `Drive File Version` for immutable original-file versions
- `Drive File Derivative` for version-bound derivative metadata
- derivative-role resolution for preview grants, with `viewer_preview` preferred for images and `pdf_page_1` preferred for PDFs when ready
- async `preview` jobs that create image derivatives and first-page PDF derivatives for supported MIME types
- provider-neutral final-object reads for `local` and `gcs` storage backends
- version replacement that marks old derivatives `stale` and creates new pending derivative rows/jobs

Drive still does not have:

- broader media support beyond the narrow image Phase 1 set
- an Ed-facing portal contract; Ed still owns that boundary

Treat current preview support as a partial Phase 1 implementation, not as the final governed preview architecture.

## Assessment Of The Proposal

What is correct and should be kept:

- Drive owns preview infrastructure, derivative generation, derivative storage, and grant issuance
- preview artifacts must be bound to `Drive File Version`
- derivative generation belongs on async queues
- preview failure must degrade cleanly to open/download or metadata-only behavior
- storage object keys must remain internal implementation details

What must be tightened:

- the portal-facing contract should not be "Ed asks Drive for grant URLs and embeds them in list DTOs"
- for Ed-owned surfaces, Drive grants should be requested just in time by an Ed-owned route after business-surface authorization
- `issue_preview_grant(drive_file_id=...)` is too weak once multiple derivative roles exist
- derivative rows need their own lifecycle state and object key ownership

## Canonical Drive Ownership

Drive owns:

- immutable governed file identity
- immutable original-file versions
- derivative generation and derivative storage
- derivative invalidation on version replacement
- derivative erasure when source lifecycle requires it
- object-storage abstraction
- short-lived preview/open/download grant issuance

Drive does not own:

- portal semantics
- business-surface grouping
- family/student/staff audience math
- portal permission decisions for Ed-owned surfaces

Rule:

> Drive delivers already-authorized file actions. It does not become the portal authorization engine for Ifitwala_Ed surfaces.

## Portal Contract Boundary

For Ifitwala_Ed-owned portals:

- the SPA must not call `ifitwala_drive.api.access.issue_preview_grant` or `issue_download_grant` directly
- Ed should validate the business surface first, then call Drive to issue a short-lived grant, then redirect

Direct Drive grant APIs remain valid for:

- Drive-native workspace surfaces
- internal Ed server integrations
- public or non-Ed surfaces explicitly designed around Drive as the primary product boundary

This distinction is required because current Drive access checks are based on governed file ownership and standard document read access, not on Ed's portal-specific audience contracts.
The APIs are not wrong in general. They are the wrong portal-facing boundary for Ed-owned surfaces.

## Data Model Direction

### Recommended new model: `Drive File Derivative`

Recommended fields:

- `drive_file`
- `drive_file_version`
- `derivative_role`
- `status`
- `storage_backend`
- `storage_object_key`
- `mime_type`
- `size_bytes`
- `width`
- `height`
- `page_count`
- `generated_on`
- `error_code`
- `error_message_sanitized`
- `source_hash` or an equivalent version-correlation marker

Recommended derivative roles in the first contract:

- `thumb`
- `viewer_preview`
- `pdf_page_1`

Recommended statuses:

- `pending`
- `processing`
- `ready`
- `failed`
- `unsupported`
- `stale`

Do not add more derivative roles in Phase 1 unless one is required by a shipped surface. The first milestone needs the smallest model that can support Org Communication correctly.

### Lightweight hints may remain on `Drive File`

Cheap browse/read-model hints may stay on `Drive File` or the current version, for example:

- `preview_status`
- `has_preview`
- `preview_generated_on`

These are optimization hints only. They do not replace derivative records.

## Version Rule

Preview artifacts must attach to `Drive File Version`, not only to `Drive File`.

Consequences:

- replacing the source file creates a new current version and a new derivative lifecycle
- historical derivatives are not the current preview truth
- invalidation becomes deterministic
- audit and erasure stay aligned with the actual byte history

Do not represent derivatives as:

- extra `Drive File Version` rows on the original version chain
- separate first-class governed files owned by the business surface

Original versions and derivative artifacts are different concepts and need different tables.

## Grant Contract Direction

Current state:

- `issue_preview_grant(...)` still uses the current `Drive File.preview_status` gate
- preview grant resolution prefers a ready primary derivative for the current version: `viewer_preview` for images and `pdf_page_1` for PDFs
- preview grant resolution falls back to the current original object only while no derivative is ready yet

Target state:

- preview grants resolve a derivative for the current version and requested derivative role
- download/open grants continue to resolve the original current object
- preview issuance should fail closed if the requested derivative is not `ready`

The API shape must evolve accordingly. One acceptable direction is:

```python
issue_preview_grant(
    drive_file_id: str | None = None,
    canonical_ref: str | None = None,
    derivative_role: str = "viewer_preview",
)
```

Equivalent internal service shapes are acceptable if they preserve the same contract.

## Processing And Lifecycle Rules

Derivative generation belongs to Drive async workers.

Required behavior:

1. resolve the current governed file version
2. dedupe work by `drive_file_version + derivative_role`
3. generate derivative artifacts only for supported media classes
4. persist derivative metadata rows
5. update lightweight preview hints
6. mark failures and unsupported types explicitly
7. mark affected derivative rows stale on replacement
8. delete derivative blobs and metadata during governed erasure

Failure posture:

- preview failure must never block normal file ownership or download semantics
- unsupported files remain valid governed files
- heavy processing must stay off hot request paths

## Storage Contract

Derivative objects must use the same provider-neutral storage abstraction as original files.

Rules:

- no UI or Ed business code sees derivative object keys
- no portal contract assumes bucket names, filesystem paths, or provider URL shapes
- derivative keys remain storage internals
- `derivatives/...` is an acceptable internal object-key namespace, not a public contract

## Cross-App Implementation Plan

Phase 1: contract lock

- add canonical preview contract docs in Drive and Ed
- explicitly document that current preview support is partial groundwork

Phase 2: Drive foundation

- add `Drive File Derivative` or equivalent
- add derivative-role status model and storage ownership
- extend grant resolution to derivative roles
- keep current download/open behavior unchanged

Phase 3: processing pipeline

- add idempotent derivative jobs on Drive queues
- support image derivatives and first-page PDF derivatives on the narrow shipped path
- keep broader media beyond those two cases deferred until the narrow path is stable

Phase 4: Ed integration

- expose Ed-owned stable preview routes that request Drive grants just in time
- ship Org Communication first, then learning resources, then stricter version-aware surfaces

Phase 5: regression protection

- add derivative lifecycle tests
- add replace/version invalidation tests
- add erasure cleanup tests
- add access-grant tests that prove portal surfaces do not depend on direct Drive SPA calls

## Explicit anti-patterns

Do not do any of the following:

- issue provider-signed grants during page bootstrap for every attachment in a list
- treat `Drive File.preview_status` as sufficient derivative truth
- use current original object keys as the long-term preview contract
- let Ed portal clients call Drive grant APIs directly for governed business surfaces
- store derivative blobs as if they were first-class original governed files
- move portal authorization into Drive just because preview delivery happens there
