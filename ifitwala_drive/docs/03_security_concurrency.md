# Security, concurrency, and GCP

## Threat model

You explicitly want safety/security high because schools are increasingly targeted and students will try anything.

Correct assumptions:

* students will probe URL patterns,
* students will test permissions,
* staff will accidentally overshare,
* families will upload wrong files,
* shared devices and weak school IT are common.

## Security principles

### 1. No raw path trust

The UI never guesses storage paths.
This is already locked in your governance notes.

### 2. No direct business-logic `File.insert()`

All governed uploads must pass through the Drive boundary.

### 3. Short-lived access grants

Downloads/previews should use short-lived signed or opaque grants, not permanent direct links.

### 4. Private-by-default storage

Use private object storage for governed files.
Public media is the exception and still must use canonical managed references.

### 5. Strong server-side permission enforcement

UI hiding is not security.

### 6. Minimal retained audit for erasure

Your GDPR model is already clear:

* deletion is a workflow,
* minimal audit remains,
* content and recoverable versions must not remain.

## Concurrency architecture

For high concurrency, keep synchronous paths cheap.

### Synchronous hot path

* authorize user
* validate owning context
* create upload session
* finalize session
* create governed record
* return canonical reference

### Async cold path

* preview generation
* derivative generation
* malware scan if enabled
* indexing
* quota/accounting reconciliation
* heavy media jobs

This is the right way to get scale without over-distributing too early.

## Queue design

Use dedicated Drive queues, separate from normal ERP jobs:

* `drive_short`
* `drive_default`
* `drive_heavy`

That prevents file processing from starving academic workflows.

## Cost-conscious GCP shape

### Early phase

* Cloud Run or GKE depending your stack preference
* Cloud Storage bucket for blobs
* Redis already present for Frappe jobs/caching
* tenant prefixes or bucket-per-environment, not necessarily bucket-per-demo-customer at first
* minimal preview pipeline initially

### Storage strategy

* originals in Cloud Storage
* derivatives only when needed
* lazy generation
* lifecycle rules later for stale derivatives/previews/public media cache

### Identity

Use workload identity / service account binding, not embedded long-lived keys.

### Network/security edge

Use basic rate limiting / WAF posture at the edge as soon as public upload/download surfaces exist.

## Cost optimization principles

* don’t duplicate blobs unless needed
* don’t generate previews for every file type up front
* don’t transcode unless user-facing value is proven
* store metadata in DB, blobs in object storage
* keep uploads resumable to reduce failed restarts and support unstable networks
* use template/workspace model instead of naive mass duplication
