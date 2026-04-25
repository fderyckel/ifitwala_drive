# Product Principles

Status: Active product principles
Last updated: 2026-04-25
Code refs:
- `ifitwala_drive/api/uploads.py`
- `ifitwala_drive/services/uploads/sessions.py`
- `ifitwala_drive/services/uploads/finalize.py`
- `ifitwala_drive/services/files/access.py`
Test refs: See workflow-specific tests and seam tests referenced from implementation docs.

## Bottom Line

Ifitwala Drive is the governed file product for Ifitwala Ed. It is not a generic cloud drive, a loose attachment helper, or a second permission universe.

The product rule is context first, Drive second: users should usually find and act on files from the educational workflow they are already using, with Drive browse/search available for orientation and reuse.

## 1. What Drive Owns

Drive owns governed file execution:

- upload sessions
- binary ingress
- storage object identity
- file, version, binding, and derivative metadata
- preview/download grants
- access events
- file erasure execution

Drive must stay storage-backend independent so the product can move between local storage, object storage, and future managed storage without teaching Ed or the SPA about storage topology.

## 2. What Ed Owns

Ifitwala Ed owns:

- academic, admissions, communication, safeguarding, and media workflows
- tenant and school scope
- user authorization in the product surface
- workflow-specific upload meaning
- workflow-specific read/open/preview visibility
- post-finalize business mutation

Drive must not replace those workflow decisions with a parallel permission model.

## 3. UX Principles

- Common actions should be surfaced where users already work.
- Upload, preview, replace, and reuse flows should preserve workflow context.
- Blocked actions must fail closed and explain the missing permission, context, or contract.
- Reusable assets should prefer selection/reuse over blind re-upload when that is the lower-friction path.
- Folders are useful for human browsing, but folders are never permission, retention, ownership, or erasure truth.

## 4. Contract Principles

- New governed file flows use a `workflow_id` plus `workflow_payload`.
- Drive persists the resolved workflow contract with the upload session.
- `File Classification` is retired and must not return as a runtime authority.
- Compatibility `File` rows may exist only as projections for Frappe-native surfaces.
- SPA/API payloads expose stable server-owned actions such as `open_url`, `preview_url`, and `thumbnail_url`, not raw private paths.
- Wrapper-specific APIs may exist during migration, but they must delegate to the canonical session/finalize/grant behavior.

## 5. Product Boundaries

Drive should not become:

- a document authoring suite by default
- a generic cross-tenant shared drive
- an infra orchestration plane
- a replacement for Ed workflows
- a folder system where folders define legal truth

Drive should remain:

- governed
- context-aware
- searchable and browseable
- reusable for teaching resources and institutional media
- strict for student, child, admissions, safeguarding, and private records
