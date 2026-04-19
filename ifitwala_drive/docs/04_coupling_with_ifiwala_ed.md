# Coupling With Ifitwala_Ed

Status: LOCKED boundary contract
Date: 2026-04-19
Code refs:
- `ifitwala_ed/integrations/drive/bridge.py`
- `ifitwala_ed/utilities/governed_uploads.py`
- `ifitwala_drive/services/uploads/finalize.py`
- `ifitwala_drive/services/files/access.py`

## Bottom line

- Ed remains the workflow and permission authority.
- Drive remains the governed file execution authority.
- Neither app may reach through the other app's internals to finish its job.
- Current code still contains leaks; those leaks are transitional defects, not approved architecture.

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

### 2.2 Finalize

Drive finalizes the upload and creates authoritative Drive records.

Ed participates only through the approved integration surface for:

- authoritative workflow-spec resolution and validation
- post-finalize business mutation

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

This is preferable to many wrapper-specific imports spread across both repos.

Workflow-specific wrapper exports may exist temporarily during migration, but they are compatibility shims only.

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

But tight coupling is not permission to call each other's internals arbitrarily.

## 8. Current-runtime violations to remove

Current code still shows these defects:

- Ed upload helpers that write temp blobs and mutate upload sessions directly
- Drive finalize code that imports Ed dispatcher logic

These patterns must be removed during the boundary refactor.
