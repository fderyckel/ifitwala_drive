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

### 6. Synchronous byte validation before governance

`mime_type_hint` is advisory only.
Before a governed file is finalized, Drive should inspect the uploaded bytes, reject dangerous executable/script payloads, and fail closed on MIME mismatches. Deeper scans can still run async later.
For picture uploads, callers must derive `mime_type_hint` from the uploaded file metadata when available, or from the filename as a fallback. Transport-envelope MIME values such as `multipart/form-data` are invalid hints and must never be forwarded to Drive.

### 7. Minimal retained audit for erasure

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
* validate uploaded bytes / MIME
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

Drive keeps semantic processing classes on `Drive Processing Job.queue_name`:

* `drive_short`
* `drive_default`
* `drive_heavy`

Preferred production topology is to provision matching custom worker queues so file processing stays isolated from academic workloads.

Runtime rule:

* if the site has matching custom queues configured, enqueue onto those same `drive_*` workers
* otherwise fall back at the enqueue boundary to Frappe's standard queues:
  * `drive_short` -> `short`
  * `drive_default` -> `default`
  * `drive_heavy` -> `long`

That preserves Drive's internal job semantics without letting governed uploads fail on sites that only run the standard worker set.

### Hot-path safeguard

Preview, derivative, offload, and similar async follow-up work must not turn a successful governed mutation into a browser-visible error merely because the site omitted custom Drive worker queues.

Rules:

* queue choice is a runtime contract, not just an internal label
* enqueue boundaries must validate or normalize queue names before calling `frappe.enqueue(...)`
* if a feature truly requires dedicated custom workers with no fallback, that operator dependency must be explicit in the canonical API contract and runbook before the feature is considered production-ready

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
* keep proxy uploads local-only; remote storage flows should stay direct-to-object-storage
* use template/workspace model instead of naive mass duplication
