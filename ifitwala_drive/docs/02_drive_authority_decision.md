# Drive Authority Decision

Status: LOCKED architecture decision
Date: 2026-04-20

## Bottom line

- The Drive-authority model remains the chosen direction.
- Ed remains the workflow authority.
- Drive becomes the sole governed file execution and metadata authority.
- `File Classification` may exist only as temporary migration baggage and must not survive the refactor.

## 1. Decision

We are keeping the hybrid transition model, formerly called Option C, but with a sharper end-state than the earlier notes implied.

Chosen target:

- new governed uploads, finalize, derivatives, delivery, and metadata truth go through Drive
- Ed supplies workflow semantics and permissions
- no permanent parallel governance layer remains in Ed

This is:

- not a storage-only forever model
- not a detached microservice split
- not a permanent compatibility architecture

## 2. Why this decision still stands

Option C still best balances:

- migration realism
- product UX
- governance safety
- object-storage readiness
- same-bench Frappe execution

What changes in this reset is the clarity of the end-state:

- compatibility projections are temporary
- the final model does not keep `File Classification` as co-equal truth

## 3. End-state architecture

### 3.1 Ed owns

- workflow semantics
- business owner resolution
- permission and scope rules
- surface-specific visibility rules
- post-finalize business mutation

### 3.2 Drive owns

- session lifecycle
- blob ingress
- object identity
- file/version/binding/derivative records
- grants
- audit and erasure execution

### 3.3 Compatibility during migration

Compatibility projections may exist temporarily if needed to keep the product running while surfaces migrate.

But:

- they are not authority
- no new design may depend on them
- they must be removable

## 4. Non-negotiable invariants

- every governed file has one authoritative business owner
- every governed file has one resolved slot
- folders are browse aids, not governance truth
- file content is not the business record
- no raw path assumptions
- no parallel ACL system
- heavy file work stays off the request path

## 5. Phase model after the docs reset

### Phase 1

Docs reset and boundary lock.

Goal:

- stop design drift
- make current leaks explicit defects

### Phase 2

Boundary cleanup.

Goal:

- completed in code

### Phase 3

Authority collapse.

Goal:

- Drive metadata becomes sole governance authority
- completed in code
- historical governed files are backfilled into authoritative Drive session/file/version records before cleanup
- historical `File Classification` rows are removed only through an explicit migration patch once matching `Drive File` authority exists

### Phase 4

Compatibility and schema retirement.

Goal:

- remove `File Classification` rows and DocTypes
- retire dead Ed-local dispatcher baggage

Status:

- completed in code

### Phase 5

Derivative and read-path cleanup.

Goal:

- Drive becomes sole derivative authority
- Ed hot read paths stop probing storage directly

Status:

- completed in code for governed profile-image delivery
- Ed now resolves profile-image compatibility variants from Drive derivative roles instead of separate governed files

### Phase 6

Drive-native reuse and browse UX expansion.

Goal:

- richer resource library and reuse flows on top of the clean boundary

## 6. What this plan must not do

It must not:

- preserve the old Ed-local governance model indefinitely
- introduce new legacy shims as permanent design
- add more cross-app internal imports
- keep `File Classification` because migration feels inconvenient
- turn folders into governance truth

## 7. Canonical API direction

Ed should think in:

- workflow IDs
- upload sessions
- Drive files and bindings
- canonical refs
- grants

Ed should stop thinking in:

- raw `File`
- raw attachment path
- `File Classification`
- Ed-owned derivative files
