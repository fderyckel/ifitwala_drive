# Object Storage Adapter Contract

## Bottom Line

`ifitwala_drive` should treat storage as a provider-neutral object-storage boundary.

The runtime should support:

- `local`
- `gcs`
- `s3_compatible`

Ifitwala_Press owns the environment storage profile.
Ifitwala_drive consumes resolved runtime configuration and never makes synchronous control-plane calls on normal request paths.

---

## 1. Why This Contract Exists

The storage layer is now materially better, but the contract still needs to stay explicit:

- runtime resolution now supports `local`, `gcs`, and `s3_compatible`
- the `gcs` backend now implements direct resumable uploads and object inspection
- storage semantics still need to stay provider-neutral above the adapter

Without a clear contract, that is still not enough for:

- S3-style object storage
- Press-managed tenant environment profiles
- long-term provider portability
- real high-concurrency upload/finalize behavior

The storage contract must be explicit before deeper file-platform work continues.

---

## 2. Design Rules

### 2.1 Provider-neutral above the adapter

Outside the storage adapter, no code should depend on:

- bucket names
- endpoint URLs
- provider-specific signed URL formats
- filesystem paths
- rename/move semantics

Everything above the adapter should work in terms of:

- upload targets
- object keys
- finalize operations
- existence checks
- signed grants
- delete / purge operations

The adapter boundary is storage-only:

- business permissions still come from Ed owning documents
- workflow meaning still comes from Ed contracts
- the storage adapter never decides admissions, task, or media semantics

### 2.2 Press owns environment storage configuration

Ifitwala_Press already models tenant environment storage provider and quota.

Press should own the resolved environment storage profile, including:

- provider type
- bucket/container binding
- object prefix strategy
- region
- endpoint when required
- quota
- runtime identity / secret delivery
- worker profile for heavy file jobs

Drive should read a resolved runtime profile from local app config or environment.
Drive should not call Press on upload, finalize, browse, preview, or download requests.

### 2.3 High concurrency is a first-class requirement

The storage contract must work safely under:

- client retries
- repeated finalize attempts
- slow networks
- worker restarts
- concurrent requests for the same upload session

Therefore:

- upload session creation must be idempotent when the caller provides an idempotency token
- finalize must be safely replayable for the same upload session
- network-bound object operations must not require broad locks
- object-store operations must be safe to retry or detect as already completed

### 2.4 Metadata truth vs blob truth

The database remains the truth for:

- canonical refs
- governance metadata
- browse projections
- preview state
- processing state

More specifically:

- Ed remains the source of business meaning and permission inheritance
- Drive remains the source of storage/access/read-model state

Object storage remains the truth for:

- original blob bytes
- derivative blob bytes

---

## 3. Resolved Runtime Storage Profile

Drive should consume a resolved runtime profile with this meaning:

- `backend_name`
- `provider_family`
- `bucket_or_container`
- `base_prefix`
- `region`
- `endpoint`
- `signing_mode`
- `quota_scope`
- `credential_source`

These are contract concepts, not locked DocType fieldnames.

Important:

- the runtime profile may be sourced from Press-owned tenant environment data
- the app should receive the resolved profile through deployment/runtime configuration
- the profile must be environment-specific, not hard-coded in the app

---

## 4. Canonical Adapter Interface

The current `StorageBackend` protocol is close, but it should evolve into a clearer object-storage contract.

Recommended minimum interface:

```python
class ObjectStorageBackend(Protocol):
    backend_name: str

    def create_temporary_upload_target(
        self,
        *,
        session_key: str,
        filename: str,
        mime_type: str | None = None,
        upload_token: str | None = None,
        expected_size_bytes: int | None = None,
    ) -> dict[str, Any]: ...

    def write_temporary_object(
        self,
        *,
        object_key: str,
        content: bytes,
    ) -> dict[str, Any]: ...

    def temporary_object_exists(
        self,
        *,
        object_key: str,
    ) -> bool: ...

    def read_temporary_object_head(
        self,
        *,
        object_key: str,
        max_bytes: int,
    ) -> bytes: ...

    def finalize_temporary_object(
        self,
        *,
        object_key: str,
        final_key: str,
    ) -> dict[str, Any]: ...

    def abort_temporary_object(
        self,
        *,
        object_key: str,
    ) -> None: ...

    def issue_download_grant(
        self,
        *,
        object_key: str,
        file_url: str | None,
        expires_on: datetime,
        filename: str | None = None,
    ) -> dict[str, Any]: ...

    def issue_preview_grant(
        self,
        *,
        object_key: str,
        file_url: str | None,
        expires_on: datetime,
    ) -> dict[str, Any]: ...

    def delete_object(
        self,
        *,
        object_key: str,
    ) -> None: ...
```

Optional later methods:

- `copy_object(...)`
- `get_object_metadata(...)`
- `open_read_stream(...)`
- `issue_multipart_upload_target(...)`

---

## 5. Upload Target Contract

### 5.1 Supported strategies

Drive should support these upload strategies at the contract layer:

- `proxy_post`
- `resumable_put`
- `signed_put`
- `multipart`

V1 can implement:

- `proxy_post` for `local`
- `resumable_put` for `gcs`
- `signed_put` or `multipart` for `s3_compatible`

The rest of the app should not care which strategy is returned.

### 5.2 Canonical response shape

```json
{
  "object_key": "tmp/session-key/original-filename.pdf",
  "upload_strategy": "resumable_put",
  "upload_target": {
    "method": "PUT",
    "url": "provider-issued-upload-url-or-session-uri",
    "headers": {
      "Content-Type": "application/pdf"
    }
  }
}
```

For resumable uploads:

- the adapter may do the provider-specific initiation request itself
- the returned `upload_target.url` may be a resumable session URI rather than a raw signed object URL
- the upload session should persist the full negotiated contract for idempotent retries

For multipart later:

- the adapter may return multipart initiation data
- the upload session should persist whatever state is needed to complete or abort it safely

---

## 6. Finalization Semantics

### 6.1 No rename assumption

The adapter contract must not assume object rename support.

This is critical because:

- local storage can move files
- GCS often behaves like copy/rewrite plus delete
- S3-compatible providers usually need copy-plus-delete or multipart completion semantics

So `finalize_temporary_object(...)` means:

> make the final object exist at `final_key`, ensure the temporary upload is no longer the active source of truth, and return the final storage artifact.

### 6.2 Finalization response shape

```json
{
  "object_key": "files/ab/cd/hash.pdf",
  "storage_backend": "s3_compatible",
  "file_url": null
}
```

Notes:

- `file_url` may be `null` for pure object-storage backends if Drive issues grants from object keys only
- if a backend returns a provider URL internally, that is still not a canonical UI contract

### 6.3 Idempotency rule

If finalize is called twice for the same session:

- the same final object should be resolved
- the same final storage identity should be returned
- the application should not create duplicate governed records

This means finalize must be safe against:

- duplicate client submissions
- client timeout + retry
- worker/process restart mid-flow

---

## 7. Download And Preview Grant Contract

The adapter owns provider-specific signing.

The application receives only:

```json
{
  "grant_type": "signed_url",
  "url": "short-lived-access-url"
}
```

Rules:

- grant URLs are short-lived
- preview and download can share implementation initially, but remain separate contracts
- no long-lived public URLs for governed private files
- UI and business code must call Drive grant APIs, not construct storage URLs

---

## 8. Object Key Rules

Object keys should be:

- deterministic enough for idempotent finalization
- opaque enough that users never infer governance from storage shape
- provider-neutral

Recommended structure:

- temporary keys under `tmp/...`
- final originals under `files/...`
- derivatives under `derivatives/...` later

Do not encode business-governance truth in the object key.
That truth already belongs in `File Classification`.

---

## 9. Backend Notes

### 9.1 `local`

Purpose:

- development
- local test environments
- emergency fallback for founder/runtime phases

Allowed traits:

- proxy upload
- same-host private file URL
- direct disk path resolution for local-only derivative tooling

Not acceptable as the long-term production abstraction.

### 9.2 `gcs`

Purpose:

- native Google Cloud object storage

Required traits:

- signed upload targets
- signed download/preview grants
- object existence checks
- finalize semantics that do not assume rename

### 9.3 `s3_compatible`

Purpose:

- S3-style object storage under Press-managed tenant environments
- future portability away from provider-specific assumptions

Required traits:

- signed PUT or multipart upload targets
- copy/delete or multipart-complete aware finalize semantics
- signed GET grants
- endpoint/region aware configuration

Strategic rule:

the rest of Drive should work unchanged when switching between `gcs` and `s3_compatible`.

---

## 10. Press Boundary

Ifitwala_Press should own:

- storage provider selection
- quota policy
- bucket/container binding
- environment-level prefix policy
- credentials and secret handling
- worker profile and isolation class

Ifitwala_drive should own:

- session lifecycle
- canonical file identity
- short-lived grants
- provider-neutral object-key handling
- read-model metadata

Ifitwala_Ed should own:

- workflow truth
- governance truth
- post-finalize business state

---

## 11. Immediate Implementation Direction

### In Drive

- keep `services/storage/base.py` as the single adapter resolver
- add `services/storage/s3_compatible.py`
- harden `gcs.py` from stub to real object-store behavior
- make the rest of Drive depend only on the adapter protocol

### In Press

- publish a resolved runtime storage profile per tenant environment
- treat provider choice and quota as environment operations concerns
- do not expose storage orchestration details through synchronous application calls

### In Ed

- continue to treat Drive as the file-platform boundary
- never let workflow code reason about provider-specific storage mechanics

---

## 12. Decision To Lock

If only one storage decision is locked now, it should be this:

**Drive speaks a provider-neutral object-storage contract, and Ifitwala_Press decides which backend profile each tenant environment runs.**
