# Canonical API Contracts

Status: LOCKED target API direction
Date: 2026-04-20
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

## 2. Cross-app integration surface

The preferred long-term cross-app contract is:

### 2.1 Ed -> Drive

- `create_upload_session(workflow_id, workflow_payload, filename_original, mime_type_hint, expected_size_bytes, upload_source, idempotency_key)`
- `finalize_upload_session(upload_session_id, received_size_bytes, content_hash?)`
- `abort_upload_session(upload_session_id)`
- `issue_download_grant(drive_file_id | canonical_ref)`
- `issue_preview_grant(drive_file_id | canonical_ref, derivative_role?)`

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
- return session identifiers and upload target info

### Response contract

At minimum:

- `upload_session_id`
- `session_key`
- `status`
- `expires_on`
- `upload_strategy`
- `upload_target`

Current rule:

- the public `create_upload_session(...)` API is workflow-spec only
- migration/backfill code must use internal service helpers or explicit `Drive Upload Session` materialization, not the public API

## 4. Blob ingress contract

### `upload_session_blob`

Purpose:

- receive bytes only for proxy/local upload strategies

Rules:

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
- `canonical_ref`
- upload session terminal `status`
- `preview_status`

The response must not rely on raw private file URLs as the primary browser contract.

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

## 10. Current-runtime note

Current code still contains wrapper-heavy and cross-import-heavy paths.

Those are transitional implementation details, not the target API model.
