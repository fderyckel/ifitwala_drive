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
**Drift**: `validation.py` inside `validate_create_session_payload` utilizes `require_fields` to ensure the `slot` is present, which is good. However, there is no discrete validation matrix confirming that the attached `slot` is actually a canonically valid string (like `submission`, `feedback`, `rubric_evidence`). Accepting unregulated strings effectively renders the "slot" property an undisciplined label, breaking the governance model.
**Suggested Fix**: Integrate an explicit Python `Tuple` linking immutable slot configurations back directly into `validation.py`: `KNOWN_SLOTS = ("submission", "feedback", "organization_media__logo", ...)`. Cross-check inbound requests explicitly against the tuple prior to authorizing session configurations.
**Rationale**: Spelling errors passed blindly from the frontend Vue SPA compromises tracking parameters and archival tasks reliant exactly matching on string arrays during bulk Frappe DB iterations. Securing "Slot" references is the ultimate pillar locking system consistency across Ifitwala Ed APIs.

### 9. Ambiguity: Google Workload Identity Documentation
**User Impact: 0.0 | Eng: 0.8**
**Context**: Notes explicitly recommend Workload Identity over long-lived keys.
**Ambiguity**: There is no documentation within `README.md` or `03_security_concurrency.md` explicitly outlining how the Frappe containers on GKE/Cloud Run map to GCP Service Accounts. `ConfiguredRemoteStorageBackend` relies implicitly on Frappe's underlying integrations. Since DevOps is expected to deploy this using Ifitwala_Press, precise configuration docs covering the `gcp-workload-identity-provider` setup are urgently missing.
**Suggested Fix**: Generate an architectural guide explicitly summarizing deployment logic bridging `Ifitwala_Press` provisioning workflows cleanly alongside standard GCP Kubernetes Workload Identity tokens, highlighting `google-auth` application default credentials instead of legacy json keys.
**Rationale**: Manual deployment mappings via static `.json` fragments fundamentally compromise large-scale GCP topologies by introducing fatal security exposure points mapped historically inside volume mounts or environment configurations. Leveraging GitOps-native mappings binds container-specific authentication automatically.

### 10. UX Drift: `api/submissions.py` Wrapper Lacks Type Contracts
**User Impact: 0.4 | Eng: 0.5**
**Context**: The docs mention the creation of a specialized `upload_task_submission_artifact(...)` taking very precise inputs (`student`, `mime_type_hint`, etc.).
**Drift**: The actual implemented wrapper simply states `upload_task_submission_artifact_service(kwargs)`. Frappe API layers are normally strongly typed in their parameters for auto-documenting what the SPA should send. The loose `kwargs` breaks the deterministic API boundaries required by the new frontend SPA, creating high friction for UI teams trying to submit tasks.
**Suggested Fix**: Reconfigure `upload_task_submission_artifact` stripping `**kwargs` and rigorously mapping parameter inputs: `def upload_task_submission_artifact(task_submission: str, student: str, filename_original: str, mime_type_hint: str = None) -> dict[str, Any]:`.
**Rationale**: Python-level Frappe `@frappe.whitelist()` endpoints seamlessly cast properly formatted signatures, isolating UI debugging directly into standard HTTP `400` payload schema validation errors while blocking injection vulnerabilities automatically.

---

**Summary for Product Management & Architecture:**

The current implementation now has three important storage foundations in place:

1. GCS resumable uploads for new governed writes
2. direct signed GCS reads for private governed downloads/previews
3. settings-driven dry-run and queued offload jobs for existing local attachments

The remaining high-priority work is now narrower and more operational:

1. **Public/Private Storage Split**: Separate public organization media from private governed files so public reads can use CDN/public-bucket delivery without signed URL overhead.
2. **Lifecycle Cleanup**: Re-enable schedulers in `hooks.py` and clean up expired upload sessions / orphaned `tmp/...` objects automatically.
3. **API Hardening**: Add rate limits on upload/session endpoints and tighten wrapper contracts that still rely on loose `**kwargs`.
4. **Slot Registry**: Enforce a canonical slot allowlist in `validation.py` so slot semantics cannot drift into arbitrary strings.
5. **Migration Completion**: Add compatibility reads for migrated legacy `/files/...` and `/private/files/...` attachments before any local-blob pruning is allowed.
6. **Ops Documentation**: Document Workload Identity / ADC deployment clearly so production storage auth does not depend on ad hoc operator knowledge.
