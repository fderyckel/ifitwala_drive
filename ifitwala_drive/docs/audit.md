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

### 4. Ambiguity: Public Media Storage & CDN Caching
**User Impact: 0.8 | Eng: 0.8**
**Context**: `03_security_concurrency.md` states "Public media is the exception and still must use canonical managed references."
**Ambiguity**: `remote.py` does not aggressively differentiate between public and private buckets. `_build_object_url` acts broadly the same for both. If public organizational media (like school logos) utilizes short-lived signed URLs, it entirely bypasses the benefits of Google Cloud CDN. There needs to be a dedicated public GCS bucket with uniform public read access mapped to `is_private=0` blobs.
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

### 7. Code Drift: Generic S3/GCS Abstraction vs Documentation Mandates
**User Impact: 0.0 | Eng: 0.5**
**Context**: Earlier phase-planning notes expected a more provider-specific `services/storage/gcs.py` implementation.
**Drift**: The actual implementation abstracted this out into `remote.py` and `base.py`, with `gcs.py` being merely a 10-line subclass overriding `backend_name` and `grant_type`. While this is a better abstraction for multicloud, it represents a substantial documentation drift preventing straightforward understanding by newly onboarded developers.
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

The current implementation securely establishes `ifitwala_drive` as the authoritative execution boundary for file governance, successfully keeping business logic within `ifitwala_ed` while extracting file storage. However, the application currently limits the scalability of Google Cloud Storage and leaves several Frappe-specific API layers loosely protected. 

To bridge the gap between an MVP and a hardened, enterprise-grade architecture, the following strategic improvements to the Frappe app must be prioritized:

1. **Shift to Native GCP Resumable Uploads**: Decouple Frappe entirely from the binary upload stream. Refactor `ConfiguredRemoteStorageBackend` to issue `POST` signature requests to GCS for chunked, resumable session URIs. This protects the Frappe Gunicorn/waitress workers from bandwidth saturation and ensures students on slow connections do not experience timeouts.
2. **Harden the Frappe API Boundary**: Enforce strict rate-limiting on all `api/uploads.py` endpoints using Frappe's `@frappe.whitelist(limit=...)` decorators to prevent DDOS-style session generation. Replace loose `**kwargs` in API controllers (e.g., `submissions.py`) with strongly-typed arguments to leverage Frappe's automatic request validation and provide clear contracts for the SPA UI.
3. **Enforce Zero-Trust Payload Validation**: Do not blindly trust client assertions. `validation.py` must validate actual file magic numbers (via python-magic or Frappe utilities) upon storage finalization rather than relying on `mime_type_hint`. Furthermore, validate `slot` names against a strict Enum or a locked configuration list to prevent arbitrary governance tags.
4. **Implement Distinct Public/Private Storage Topologies**: Separate public organizational media from private student assessments at the bucket level. Route the public bucket through Google Cloud CDN, bypassing signed URL generation entirely for public assets, dramatically speeding up the SPA load times.
5. **Activate Automated Lifecycle Management**: Un-comment `scheduler_events` in `hooks.py` and implement a routine to garbage-collect expired upload sessions and call `abort_temporary_object`. Without this, partial uploads will permanently bloat the GCS bucket, driving up unnecessary storage costs.
