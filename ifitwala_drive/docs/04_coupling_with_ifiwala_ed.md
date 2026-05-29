# Coupling With Ifitwala_Ed

Status: LOCKED boundary contract
Date: 2026-04-21
Code refs:
- `ifitwala_ed/api/file_access.py`
- `ifitwala_ed/integrations/drive/bridge.py`
- `ifitwala_ed/integrations/drive/media.py`
- `ifitwala_ed/integrations/drive/workflow_specs.py`
- `ifitwala_ed/utilities/governed_uploads.py`
- `ifitwala_drive/api/media.py`
- `ifitwala_drive/services/integration/ifitwala_ed_media.py`
- `ifitwala_drive/services/uploads/finalize.py`
- `ifitwala_drive/services/uploads/sessions.py`
- `ifitwala_drive/services/files/access.py`

## Bottom line

- Ed remains the workflow and permission authority.
- Drive remains the governed file execution authority.
- Neither app may reach through the other app's internals to finish its job.
- Ingress and finalize now follow the locked boundary.
- Governed derivative scheduling and profile-image delivery now stay on the Drive side of the boundary.
- Remaining migration work is about removing compatibility baggage, not reopening the boundary.

## 1. The boundary

### 1.1 Ed owns

- workflow meaning
- which business record owns the file
- tenant scope
- who may upload, replace, open, preview, or delete in product context
- which post-finalize business mutation should run

### 1.2 Drive owns

- upload session lifecycle
- blob ingress
- temporary object handling
- finalize
- storage identity
- versions
- bindings
- derivatives
- grants

## 2. Allowed interactions

### 2.1 Session creation

Ed may ask Drive to create an upload session using a workflow identifier and the workflow-specific business identifiers required to resolve the spec.

Current rule:

- new session creation fails closed without `workflow_id`
- wrapper-specific session metadata must be returned only through `workflow_result`

### 2.2 Finalize

Drive finalizes the upload and creates authoritative Drive records.

Ed participates only through the approved integration surface for:

- authoritative workflow-spec resolution and validation
- post-finalize business mutation

When Ed already holds buffered upload bytes in-process, it may hand those bytes back through the Drive-owned `ingest_upload_session_content(...)` helper.
That trusted server-side seam must resolve the session from Drive authority and must not require Ed to replay browser upload-token headers.

### 2.3 Read/open/preview

Ed authorizes the surface-specific action.

Drive issues the download or preview grant.

## 3. Forbidden interactions

### 3.1 Forbidden on the Ed side

Ed must not:

- load and mutate `Drive Upload Session` directly as part of upload ingress
- call Drive storage backends directly
- write temporary objects into Drive storage
- rename or move finalized Drive objects
- generate governed derivatives outside Drive
- probe storage directly to decide governed display URLs for Drive-managed media
- treat `File Classification` as authority for new work

### 3.2 Forbidden on the Drive side

Drive must not:

- import Ed dispatcher/file-routing internals to finish governed finalization
- import Ed image-derivative helpers
- rely on Ed-local storage paths as file truth
- treat Ed compatibility projections as primary governance records

## 4. Integration surface direction

Target shape:

- one narrow Ed integration module resolves `GovernedUploadSpec` by `workflow_id`
- one narrow Ed integration module runs post-finalize business mutation by `workflow_id`
- Drive persists `workflow_id` and `contract_version` on the upload-session contract so finalize does not rediscover workflow meaning ad hoc

This is preferable to many wrapper-specific imports spread across both repos.

Current runtime note:

- the registry now exists in `ifitwala_ed/integrations/drive/workflow_specs.py`
- Drive wrapper services now create sessions using `workflow_id` plus workflow-specific identifiers internally
- the generic session/finalize DTOs now carry `workflow_id`, `contract_version`, and typed `workflow_result`
- wrapper-specific extras such as `row_name` or admissions item metadata must not leak out as scattered top-level keys
- Drive also exposes surface-scoped grant wrappers where generic owner-doc checks are not the same as Ed surface authorization, including org-communication attachments, employee images, public website media, and supporting-material previews opened from placement-aware academic surfaces
- legacy profile-image cleanup is now patch-driven through those same public Drive media wrappers: Ed migration code reimports missing Employee/Student/Guardian profile images via the upload seam and requeues current governed avatar derivatives via the preview-derivative seam instead of adding new runtime repair paths
- wrapper-specific public endpoints still exist only as ergonomics shims during migration
- Ed and Drive runtime entrypoints now import only explicit public bridge/API modules; reload fallback wrappers and `sys.path` rescue are retired
- Ed workflow-spec uploads such as `expense_claim.receipt` must still use Drive-owned canonical slot and binding-role registries. Drive currently accepts the `expense_claim_receipt__*` slot family and `expense_claim_receipt` binding role for reimbursement receipt evidence.

## 5. MIME contract

Ed is responsible for deriving `mime_type_hint` correctly.

Rules:

- use the uploaded file object's MIME when available
- otherwise fall back to filename-based resolution
- never forward the multipart transport envelope as the file MIME

Drive remains responsible for inspecting bytes and failing closed on mismatch.

## 6. Read contract

For private governed media:

- Ed decides whether the current user may perform the surface action
- Drive decides which artifact to serve and issues the grant

The browser must not be taught to guess:

- storage paths
- derivative paths
- raw private file URLs

## 7. Deployment and evolution rule

Because the apps are tightly coupled:

- cross-app contract changes must land together
- docs must be updated together
- tests must cover the shared boundary
- seam tests must pin buffered-upload token handling and the locked session/finalize DTO shapes

But tight coupling is not permission to call each other's internals arbitrarily.

## 8. Remaining migration work

Current code still shows these transitional behaviors:

- Drive still emits native `File` compatibility projections for current Ed surfaces
- historical `File Classification` rows still require cleanup through the Ed migration patch
- some older Ed storage-compatibility helpers still exist for historical image fields and copied legacy links, but current governed admissions, communication, planning, learning, and evidence DTOs no longer use `File.file_url` as their primary identity
- some historical audit/discussion notes may still mention the retired `File Classification` and Ed-side derivative model and must not be treated as runtime design guidance

These are migration constraints, not target architecture.
