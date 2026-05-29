# Ifitwala Drive: Code & Architecture Audit

This audit evaluates the current state of the `ifitwala_drive` project against its stated architectural principles and governance rules. The focus is placed heavily on Google Cloud configuration, security/DevOps, UX drift, and documentation ambiguities.

Each feedback item is rated on a 0-1 scale for:
- **User Impact (UX)**: How much this affects the end-user (students, staff).
- **Engineering (Eng)**: How much this affects DevOps, Security, and Product Management.

---

### 1. UX Drift: No Resumable Uploads for Google Cloud Storage
**User Impact: 0.9 | Eng: 0.7**
**Context**: `03_security_concurrency.md` heavily emphasizes "keep uploads resumable to reduce failed restarts and support unstable networks".
**Resolution**: `gcs.py` now owns a concrete GCS adapter that initiates resumable uploads through ADC / Workload Identity and returns `upload_strategy = "resumable_put"` with the provider-issued session URI. `Drive Upload Session` persists the negotiated upload contract so idempotent retries reuse the same target instead of minting a new one.
**Implication**: Governed GCS uploads now stay direct-to-cloud and retry-safe on unstable connections without routing blob streams through Frappe.

### 2. Security & Scalability: Proxy Upload Bypass Overhead
**User Impact: 0.5 | Eng: 0.9**
**Context**: The application explicitly seeks to optimize GCP infrastructure and protect Frappe nodes from being overwhelmed by heavy file operations.
**Resolution**: `upload_session_blob` is now hard-gated by the persisted upload contract. Only `proxy_post` sessions are accepted; GCS / remote sessions fail closed and must use the issued direct upload target.
**Implication**: Local dev keeps its proxy path, but governed remote uploads no longer have a Frappe-streaming bypass that undermines concurrency and cost posture.

### 3. Security: Lack of Deep Magic-Byte MIME Validation
**User Impact: 0.2 | Eng: 0.9**
**Context**: Threat model dictates "students will try anything".
**Resolution**: Finalization now performs synchronous head-byte inspection before governed file creation. Drive reads the first 2048 bytes from temp storage, detects MIME via `python-magic`, rejects dangerous executable/script payloads, and rejects mismatches against `mime_type_hint`. Async deep scanning remains a later enhancement, not the first line of defense.
**Implication**: A file no longer becomes meaningful governance state based only on frontend claims; byte validation is now part of the fail-closed finalize gate.

### 4. Public Media Storage & CDN Caching Still Open
**User Impact: 0.8 | Eng: 0.8**
**Context**: `03_security_concurrency.md` states "Public media is the exception and still must use canonical managed references."
**Current State**: Private GCS reads now have a direct signed-URL path in `services/storage/gcs.py`, which removes the old ambiguity around private download delivery. The remaining gap is public-media topology. `remote.py` and the storage profile still do not distinguish public CDN/public-bucket reads from private governed reads strongly enough.
**Suggested Fix**: Branch the URL building utility found in `remote.py`'s `_build_object_url` to construct unauthenticated Canonical CDN Domain requests distinctly reserved for blobs marked `is_private=0` within Frappe documents. 
**Rationale**: By pushing organizations' public imagery globally to Google Cloud CDN and removing all Frappe authentication checks specifically for public buckets, critical latency on initial page rendering is vastly minimized while preserving the authoritative Canonical Reference framework for edits or replacements. 

### 5. Ops & Cost: Orphaned Temporary Objects in Google Storage
**User Impact: 0.1 | Eng: 0.8**
**Context**: Cost optimization principle states "don't duplicate blobs".
**Drift**: `services/uploads/sessions.py` correctly aborts temp blobs if `abort_upload_session` is explicitly called. However, if a session silently expires (`expires_on`), the codebase lacks an active garbage collector/cron job (the `hooks.py` `scheduler_events` are commented out) to confidently sweep `tmp` objects from the GCS bucket. Over time, partial or abandoned uploads will silently bloat Google Storage costs.
**Suggested Fix**: Re-enable `scheduler_events` in `hooks.py` specifically for `drive_short` worker queues. Implement an hourly `frappe.db.sql` search traversing all `Drive Upload Session` records carrying the `created` status and timestamp strings trailing standard `expires_on` intervals, actively invoking `abort_temporary_object` requests upstream. 
**Rationale**: Frappe's background schedulers act as critical automated lifecycle hooks minimizing bloated cloud expenses. Alternatively, combining this Frappe script loosely with formal Google Storage Object Lifecycle Rules targeting `tmp/` root prefixes older than 24 hours cleanly isolates tenant environments.

### 6. Security: API Abuse Thresholds Absent (Rate Limiting)
**User Impact: 0.3 | Eng: 0.8**
**Context**: Threat model explicitly highlights URL probing and abuse. 
**Drift**: The core endpoints in `api/uploads.py` (`create_upload_session` and `finalize_upload_session`) lack strict Frappe rate-limiting decorators (e.g., `@frappe.whitelist(limit=...)`). A single student could run a loop to generate thousands of orphaned `Drive Upload Session` records and sign thousands of unused GCS PUT URLs within a minute, causing a heavy denial-of-wallet attack.
**Suggested Fix**: Wrap all vital `api/uploads.py` HTTP endpoints using the updated `@frappe.whitelist(allow_guest=False)` and configure explicit route-based thresholds specifically leveraging Frappe's native `Rate Limit` document schemas directly referencing Redis cache keys matching users to max sessions.
**Rationale**: Explicitly filtering malicious traffic using Redis-managed rate limits ensures DDoS or logic probes block malicious users strictly before creating any internal DB overhead or generating GCS token requests. 

### 7. Documentation Drift Around Storage Adapter Shape
**User Impact: 0.0 | Eng: 0.5**
**Context**: Earlier phase-planning notes expected a more provider-specific `services/storage/gcs.py` implementation.
**Current State**: The code is now clearly hybrid: `remote.py` and `base.py` hold the shared contract, while `gcs.py` owns concrete GCS upload and signed-read behavior. The drift is now mostly documentation, not implementation.
**Suggested Fix**: Update `02_system_architecture.md` and `AGENTS.md` explicitly defining a unified AWS `S3/GCS` implementation path mapping to `ConfiguredRemoteStorageBackend`. 
**Rationale**: The Frappe multi-cloud readiness posture requires that any `Ifitwala_Press` abstractions rely fundamentally on an overarching wrapper class interacting securely across clouds. Synchronizing these changes prevents onboarded UI engineers from falsely hunting down nonexistent provider-specific integration codebases while maintaining the exact security boundaries expected.

### 8. Governance Drift: Loose "Slot" Validation Strings
**User Impact: 0.1 | Eng: 0.6**
**Context**: "Slot semantics are law". 
**Resolution**: `services/uploads/slots.py` now defines the canonical slot registry used by `validate_create_session_payload`. The registry is exact/prefix-based and only admits slot families already present in the repo contracts and tests, such as `submission`, `feedback`, `rubric_evidence`, `supporting_material__*`, `communication_attachment__*`, `expense_claim_receipt__*`, `identity_*`, `prior_*`, and the organization-media/public-image slot families.
**Implication**: New governed upload sessions now fail closed on free-form slot strings instead of treating `slot` as an undisciplined label.

### 9. Ambiguity: Google Workload Identity Documentation
**User Impact: 0.0 | Eng: 0.8**
**Context**: Notes explicitly recommend Workload Identity over long-lived keys.
**Resolution**: `20_gcs_ops_runbook.md` now documents the actual adapter behavior for ADC / Workload Identity, service-account-file fallback, the required storage capabilities, the signed-read caveat, expected `Drive Storage Settings` values, and the stale-public-link routing dependency.
**Implication**: production storage auth no longer depends on undocumented operator memory.

### 10. UX Drift: `api/submissions.py` Wrapper Lacks Type Contracts
**User Impact: 0.4 | Eng: 0.5**
**Context**: The docs mention the creation of a specialized `upload_task_submission_artifact(...)` taking very precise inputs (`student`, `mime_type_hint`, etc.).
**Resolution**: upload/session/access/domain wrappers now expose explicit parameters and compact those into the exact payloads consumed by their services. This now covers `api/uploads.py`, `api/access.py`, `api/submissions.py`, `api/resources.py`, `api/materials.py`, `api/admissions.py`, `api/communications.py`, and `api/media.py`.
**Implication**: SPA and Desk callers now get a more explicit, self-documenting Frappe endpoint contract without changing the underlying service semantics.

---

**Summary for Product Management & Architecture:**

The current implementation now has three important storage foundations in place:

1. GCS resumable uploads for new governed writes
2. direct signed GCS reads for private governed downloads/previews
3. settings-driven dry-run and queued offload jobs for existing local attachments

The remaining high-priority work is now narrower and more operational:

1. **Public/Private Storage Split**: Separate public organization media from private governed files so public reads can use CDN/public-bucket delivery without signed URL overhead.
2. **Lifecycle Cleanup**: Keep the active hourly scheduler for expiring abandoned upload sessions and temp objects healthy in production; treat failures here as an ops/runbook issue, not missing architecture.
3. **API Hardening**: Rate limits now exist on upload/session endpoints; remaining work is tuning limits and tightening any wrappers that still rely on loose `**kwargs`.
4. **Migration Completion**: Compatibility reads now exist for app-routed missing local `/files/...` and `/private/files/...` attachments. Verified private-file pruning also exists for completed offloads and for eligible new offloads with `delete_local_after_verification`. Public-file pruning now exists too, because public legacy `File.file_url` values can be rewritten onto canonical remote/proxy URLs before local deletion. The remaining compatibility gap is stale copied old `/files/...` links: static misses still need to route through the app if those old URLs must keep working.
5. **Abuse Monitoring**: rate limits and scheduler cleanup now exist; remaining work is observability, alerting, and tuning under real traffic.
6. **Wrapper Reduction**: continue removing any broad helper seams that still obscure the explicit workflow-spec boundary.
