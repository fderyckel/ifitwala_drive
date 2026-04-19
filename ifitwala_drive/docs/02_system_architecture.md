# System Architecture

Status: LOCKED target architecture
Date: 2026-04-19
Code refs:
- `ifitwala_drive/api/uploads.py`
- `ifitwala_drive/services/uploads/finalize.py`
- `ifitwala_drive/services/files/creation.py`
- `ifitwala_drive/services/files/derivatives.py`
Test refs: Pending as part of the boundary refactor

## Bottom line

- Drive is the sole governance and execution boundary for governed files.
- Ed remains the workflow and permission authority.
- Drive is not a storage proxy and not a generic consumer cloud drive.
- `File Classification` is not part of the target Drive architecture and must not survive as a parallel authority.

## 1. System split

### 1.1 Ifitwala_Ed

Owns:

- academic, admissions, and business workflows
- owner/context resolution
- tenant scope and permission checks
- workflow-specific read/open visibility rules
- post-finalize business mutation

### 1.2 Ifitwala_drive

Owns:

- upload sessions
- blob ingress
- temporary object handling
- governed storage identity
- file/version/binding records
- derivatives and previews
- canonical refs
- download/preview grants
- audit and erasure execution

### 1.3 Ifitwala_Press later

Owns later:

- provisioning
- bucket bindings
- quota/cost controls
- worker topology
- environment policy

## 2. Core architecture rule

All governed writes go through Drive.

That means:

- Drive owns the session state machine
- Drive owns blob ingress
- Drive owns finalize
- Drive owns the storage object key after finalize

Ed may validate workflow context before the request reaches Drive, but Ed must not perform governed file execution itself.

## 3. Canonical domain model

### 3.1 `Drive Upload Session`

The upload session is the authoritative pre-finalize contract.

It stores:

- resolved workflow contract
- temporary object identity
- filename and expected byte contract
- upload strategy
- session status

### 3.2 `Drive File`

The governed file identity.

It stores:

- owner
- organization/school scope
- slot
- canonical ref
- current version pointer
- active lifecycle state

### 3.3 `Drive File Version`

Immutable version records for blob history.

Drive versions are authoritative.

### 3.4 `Drive Binding`

The product-facing relationship between a governed file and a bound surface or row.

Bindings support:

- resource reuse
- surface lookup
- context retrieval

Bindings do not replace owner/slot governance.

### 3.5 `Drive File Derivative`

The only derivative authority.

Thumbnails, previews, and profile-media variants belong here.

### 3.6 Audit and erasure

Drive owns:

- access event recording
- erasure execution against stored versions and derivatives

## 4. Authority of metadata

Target authority lives in Drive-owned records:

- `Drive Upload Session`
- `Drive File`
- `Drive File Version`
- `Drive Binding`
- `Drive File Derivative`

Drive must not depend on Ed-local governance records as primary truth.

If temporary compatibility projections still exist elsewhere during migration:

- they are derived from Drive
- they are not primary truth
- they must be removable

## 5. Storage model

Drive storage is opaque to Ed.

Drive owns:

- storage backend selection
- object key generation
- temporary object lifecycle
- final object identity
- derivative storage

Ed must not:

- call Drive storage backends directly
- write temporary blobs
- rename finalized Drive objects
- infer object identity from file URLs

## 6. Execution model

### 6.1 Synchronous path

1. create upload session
2. receive blob directly or via Drive proxy
3. validate bytes and finalize
4. create Drive file/version/binding
5. run post-finalize business mutation
6. return canonical artifact identifiers

### 6.2 Asynchronous path

Drive handles asynchronously:

- derivative generation
- preview generation
- scans
- indexing
- reconciliation

## 7. Folder and browse model

Drive may expose folders and browse views.

Folders are:

- navigation and reuse aids
- not governance truth

Browse state must not replace:

- owner
- slot
- organization/school scope
- permission checks

## 8. End-state rule for `File Classification`

Drive does not need a `Drive File Classification` mirror of the old Ed model.

The refactor target is:

- governed semantics live in Drive-owned metadata
- Ed-owned `File Classification` is removed through migration

## 9. Current-runtime note

Current code still contains cross-app leaks and transitional compatibility logic.

That current-runtime gap is tracked in the Ed-side implementation note and the coupling contract:

- `ifitwala_ed/docs/files_and_policies/files_03_implementation.md`
- `ifitwala_drive/docs/04_coupling_with_ifiwala_ed.md`
