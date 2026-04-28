# Canonical API Contracts

Status: LOCKED target API direction
Date: 2026-04-27
Related docs:

- `ifitwala_drive/docs/02_system_architecture.md`
- `ifitwala_drive/docs/04_coupling_with_ifiwala_ed.md`
- `ifitwala_ed/docs/files_and_policies/files_07_education_file_semantics_and_cross_app_contract.md`

## Bottom line

- The stable contract should be small.
- Drive APIs are governed file APIs, not raw attachment helpers.
- Workflow semantics come from Ed through a versioned workflow contract.
- The browser never receives guessed storage paths as product truth.

## 1. API design rules

### 1.1 Context first

The API should be called in workflow terms, not raw file mechanics.

Good:

- create upload session for `workflow_id = task.submission`
- finalize upload session
- issue preview grant for a Drive file

Bad:

- generic attach file
- raw file move
- raw private path retrieval

### 1.2 Fail closed

If governance context is missing or invalid:

- reject the request
- do not fall back to generic attach behavior

### 1.3 Canonical refs and grants only

Consumers may receive:

- `drive_file_id`
- `drive_file_version_id`
- `canonical_ref`
- short-lived download/preview grants

Consumers must not construct storage paths.

### 1.4 Do Not Do

- Do not add new wrapper-specific governance contracts when the workflow can be represented by `workflow_id + workflow_payload`.
- Do not duplicate Ed-resolved owner, subject, slot, purpose, retention, organization, or school semantics in Drive wrappers.
- Do not turn folders into permission, retention, ownership, or erasure truth.
- Do not expose derivative role names as Ed/browser DTO fields; use stable `open_url`, optional `preview_url`, and optional `thumbnail_url`.
- Do not add schema changes before seam tests prove the existing contract cannot express the workflow.

## 2. Cross-app integration surface

The preferred long-term cross-app contract is:

### 2.1 Ed -> Drive

- `create_upload_session(workflow_id, workflow_payload, filename_original, mime_type_hint, expected_size_bytes, upload_source, idempotency_key)`
- `finalize_upload_session(upload_session_id, received_size_bytes, content_hash?)`
- `abort_upload_session(upload_session_id)`
- `issue_download_grant(drive_file_id | canonical_ref)`
- `issue_preview_grant(drive_file_id | canonical_ref)`

### 2.2 Drive -> Ed

- resolve authoritative `GovernedUploadSpec` for `workflow_id`
- validate finalize context where the workflow requires a fresh business check
- run post-finalize business mutation

The long-term goal is one narrow integration surface, not many wrapper-specific imports.

## 3. Session creation contract

### Purpose

Create a governed upload session before bytes are finalized.

### Required conceptual inputs

- `workflow_id`
- `workflow_payload`
  business identifiers needed to resolve the workflow contract
- `filename_original`
- `mime_type_hint`
- `expected_size_bytes`
- `upload_source`
- optional `idempotency_key`

### Required behavior

- resolve or validate the authoritative workflow spec
- persist the resolved contract on `Drive Upload Session`
- current runtime stores `workflow_id` and `contract_version` under `upload_contract_json.workflow`
- negotiate an upload target and strategy
- return session identifiers, upload target info, explicit buffered-upload credentials, and typed workflow metadata

### Response contract

At minimum:

- `upload_session_id`
- `session_key`
- `status`
- `expires_on`
- `upload_strategy`
- `upload_target`
- `workflow_id`
- `contract_version`
- `workflow_result`

Current rule:

- the public `create_upload_session(...)` API is workflow-spec only
- missing `workflow_id` fails closed for new session creation
- current runtime may also include `upload_token` for browser/proxy upload targets
- migration/backfill code must use internal service helpers or explicit `Drive Upload Session` materialization, not the public API
- wrapper-specific create-session extras must live only under `workflow_result`, not as ad hoc top-level keys
- public workflow wrappers that are also whitelisted Frappe API methods must tolerate the same flat request payload shapes used by Ed portals: explicitly bound kwargs, flat form values, flat JSON bodies, and nested `args`. This is request-binding tolerance only; wrappers must still pass only approved workflow fields into the governed service.
- slot meaning comes from the Ed-resolved `GovernedUploadSpec`; Drive validates slot shape and path safety, not a second exact/prefix slot registry
- transitional wrappers may add local Drive metadata such as UX folders or typed `workflow_result` after Ed workflow resolution, but must not hand-author owner, subject, slot, purpose, retention, organization, or school semantics
- `create_upload_session_service(...)` is the only public Drive session creation service; wrappers must not import resolved-session helper names or bypass the generic workflow boundary

## 4. Blob ingress contract

### `ingest_upload_session_content`

Purpose:

- receive already-buffered file content from trusted server-side app code

Rules:

- this is a Drive-owned in-process helper, not a browser-facing API
- callers resolve the session by authoritative Drive identity (`upload_session_id` or `session_key`)
- callers must not be required to replay browser upload-token headers
- Drive still owns temporary-object writes, remote upload relay, and session-state transitions
- Ed must not bypass this helper by calling storage backends directly

### `upload_session_blob`

Purpose:

- receive bytes only for proxy/local upload strategies

Rules:

- this is the public/browser blob route for `proxy_post` sessions
- session identity and upload token must match the persisted `Drive Upload Session`
- valid only when the session upload strategy is `proxy_post`
- Drive writes the temporary object
- Drive advances session state
- Ed must not bypass this API by calling storage backends directly

## 5. Finalize contract

### Purpose

Turn an uploaded temporary object into a governed Drive file.

### Required inputs

- `upload_session_id`
- `received_size_bytes`
- optional `content_hash`

### Required behavior

- validate session state
- verify temporary object existence
- inspect uploaded bytes
- finalize object placement
- create authoritative Drive file/version/binding records
- run allowed post-finalize business mutation
- enqueue async derivatives/previews/scans using runtime-valid queues

### Response contract

At minimum:

- `drive_file_id`
- `drive_file_version_id`
- `file_id`
- `canonical_ref`
- upload session terminal `status`
- `preview_status`
- `workflow_id`
- `contract_version`
- `workflow_result`

The response must not rely on raw private file URLs as the primary browser contract.
Current rule:

- finalize first validates that `Drive Upload Session.upload_contract_json.workflow` contains persisted `workflow_id` and `contract_version`; missing metadata fails before storage resolution or Ed finalize delegation
- finalize resolves workflow behavior only from persisted `workflow_id` and `contract_version`; it must not scan workflow specs to detect legacy/pre-registry sessions
- legacy sessions without persisted workflow metadata must be repaired or retired by explicit migration/backfill patches, not by finalize-time fallback logic
- `file_id` remains part of the locked Ed/Drive seam only as a transitional compatibility projection until Drive DocTypes and Ed post-upload writes no longer require native `File`
- wrapper-specific finalize extras such as admissions item metadata or generated row identifiers must live under `workflow_result`, not as top-level keys
- generic finalize callers must not depend on raw `file_url`

## 6. Abort contract

### Purpose

Abort a pending upload session and invalidate its temporary upload target.

### Required behavior

- mark the session terminal
- delete temporary objects when present
- refuse future blob or finalize actions for the session

## 7. Access grant contracts

### `issue_download_grant`

Rules:

- resolve by `drive_file_id` or `canonical_ref`
- enforce read permission through the approved boundary
- return a short-lived download contract

### `issue_preview_grant`

Rules:

- resolve by `drive_file_id` or `canonical_ref`
- select the ready derivative when the preview contract requires one
- return a short-lived preview contract
- Drive-internal and server-to-server callers may select a concrete preview variant when they need thumbnail delivery, but Ed/browser-facing DTOs must expose only stable `preview_url` and `thumbnail_url` action URLs, never derivative role names

### Surface-scoped Ed grants

Rules:

- generic `issue_download_grant` and `issue_preview_grant` remain owner-DocPerm based
- Ed-owned portal surfaces whose business authorization is not broad owner DocPerm must use a surface-scoped wrapper after Ed validates that surface context
- admissions applicant document/profile/health reads must use `ifitwala_drive.api.admissions.issue_admissions_file_download_grant` and `issue_admissions_file_preview_grant`, not the generic owner-doc grant API

## 7.5 Erasure execution contract

Drive executes governed file erasure only from authoritative Drive metadata. Folders, storage paths, browser URLs, and compatibility `File` rows are not valid erasure truth.

Execution inputs:

- `erasure_request_id`
- optional metadata filters for owner, attached document, slot, purpose, retention policy, organization, school, and data class
- optional Ed decision items with `erase`, `retain`, `anonymize`, or `skip`

Rules:

- the `Drive Erasure Request` must already be approved before execution
- Drive always scopes execution by the request subject
- metadata filters narrow the subject scope; they do not replace the subject
- legal hold blocks physical erasure even when Ed asks to erase
- Ed decisions are legal/business instructions; Drive enforces storage mechanics and legal-hold safety
- `anonymize` is treated as an Ed structured-record decision; Drive retains the file unless Ed explicitly sends an `erase` decision for that file
- the response returns itemized `erased`, `retained`, and `skipped` rows with reasons
- access events are recorded for actual file erasure

Counsel-reviewed retention policy remains outside Drive code. Drive stores and filters retention metadata, but does not decide jurisdiction-specific legal outcomes.

## 8. MIME contract

`mime_type_hint` is the caller's claim about the uploaded bytes, not the outer request envelope.

Therefore:

- callers should derive it from the uploaded file object when available
- callers may fall back to filename-based resolution
- callers must not forward `multipart/form-data` as the file MIME
- Drive remains responsible for byte inspection and rejection on mismatch

## 9. Transitional wrapper rule

Workflow-specific wrapper exports may exist during migration for ergonomics or compatibility.

But:

- they are not the desired long-term contract
- they must delegate to the canonical session/finalize/grant behavior
- they must not become a second place where workflow semantics are authored
- Ed callers must use the public `ifitwala_drive.api.*` wrapper when a surface-scoped wrapper exists; they must not import Drive integration services directly as a runtime fallback
- if a required public wrapper export is unavailable, the caller must fail closed or use its own already-authorized local delivery path; it must not fall back to generic owner-doc grant APIs for an Ed-owned surface
- current surface-scoped public wrappers include admissions files (`ifitwala_drive.api.admissions.issue_admissions_file_preview_grant` and `issue_admissions_file_download_grant`) and Student Log evidence (`ifitwala_drive.api.student_logs.upload_student_log_evidence_attachment`, `issue_student_log_evidence_attachment_preview_grant`, and `issue_student_log_evidence_attachment_download_grant`)

## 10. Current-runtime note

Current code still contains wrapper-heavy and cross-import-heavy paths.

Those are transitional implementation details, not the target API model.
