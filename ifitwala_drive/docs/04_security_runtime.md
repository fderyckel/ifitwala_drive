# Security And Runtime

Status: LOCKED target runtime posture
Date: 2026-04-19
Code refs:
- `ifitwala_drive/api/uploads.py`
- `ifitwala_drive/services/files/access.py`
- `ifitwala_drive/services/files/derivatives.py`
- `ifitwala_drive/services/queueing.py`

## Bottom line

- Keep the synchronous path short and authoritative.
- Keep storage and grant decisions inside Drive.
- Keep Ed out of blob ingress, object movement, and derivative generation.
- Treat queue validity as part of the runtime contract, not an operator afterthought.

## 1. Threat model

Assume:

- students probe URLs and permissions
- staff accidentally overshare
- families upload the wrong files
- networks are unstable
- storage backends may change without warning at the product layer

## 2. Security rules

### 2.1 No raw path trust

The browser must not receive guessed storage paths as product truth.

### 2.2 Short-lived grants for private media

Downloads and previews use server-owned routes or short-lived grants, not durable direct links.

### 2.3 Private by default

Governed files are private unless a workflow explicitly defines a public media contract.

### 2.4 Byte validation before finalize

`mime_type_hint` is advisory only.

Before finalize succeeds, Drive must:

- validate the uploaded bytes
- reject dangerous or disallowed MIME types
- fail closed on hint mismatches where policy requires it

### 2.5 Narrow trust boundary

Ed may authorize and describe workflow context.

Ed may not:

- write temporary objects
- mutate Drive upload session state directly
- move finalized Drive objects

### 2.6 Minimal retained audit for erasure

Erasure removes content and recoverable versions while leaving only the minimal audit required by the governance contract.

## 3. Concurrency model

### 3.1 Synchronous hot path

The request path may do only this:

- authorize the caller
- resolve workflow context
- create the upload session
- receive or verify blob upload completion
- validate bytes
- finalize the object
- create canonical Drive records
- return canonical identifiers

### 3.2 Async cold path

The request path must not block on:

- derivative generation
- preview generation
- scans
- indexing
- reconciliation
- heavy media transforms

### 3.3 Hot-path safeguard

No user-visible success response may depend on deferred work unless the response clearly says the file is still processing and the workflow contract allows that state.

## 4. Upload strategy rules

### 4.1 Direct upload preferred for remote storage

For remote/object storage, the browser should upload directly to the Drive-issued target whenever possible.

### 4.2 Proxy upload is local-only fallback

`upload_session_blob` exists for:

- local development
- same-host proxy strategies

It is not the preferred remote-storage path.

### 4.3 Session state is owned by Drive

Only Drive APIs and services advance session state.

## 5. Queue runtime contract

Drive may keep semantic queue classes internally:

- `drive_short`
- `drive_default`
- `drive_heavy`

At the enqueue boundary:

- if matching custom worker queues exist, use them
- otherwise normalize to Frappe runtime-valid queues such as `short`, `default`, and `long`

Follow-up work must not fail the user-visible mutation merely because a semantic queue label had no live worker.

## 6. Read-path rules

Read/open/preview flows must resolve from:

- Drive metadata
- Drive derivatives
- Drive grants
- Ed-owned authorization decisions

Read/open/preview flows must not depend on:

- repeated disk existence checks
- ad hoc path probing from Ed list surfaces
- Ed-side discovery of which derivative should exist

## 7. Cost and storage posture

Principles:

- store metadata in MariaDB/Frappe records
- store blobs in the Drive storage backend
- do not duplicate blobs unless workflow value justifies it
- generate derivatives lazily and reuse them
- prefer resumable/direct uploads for unreliable networks

## 8. Runtime compatibility note

Compatibility behavior may exist for migration and local development.

That does not change the runtime contract defined here.
