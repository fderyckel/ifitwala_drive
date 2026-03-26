# Lean Bridge And True Drive View Proposal

## Bottom Line

`File` plus `File Classification` in `ifitwala_ed` should remain the only authoritative governance truth for governed files.

`ifitwala_drive` should become a lean file-platform layer that owns:

- upload sessions
- idempotent, concurrency-safe finalize paths
- storage object resolution
- provider-neutral object-storage adapters
- canonical refs and access grants
- preview / processing state
- a read-model for Drive browsing

It should stop acting like a second governance database.

---

## 1. Current Diagnosis

### 1.1 Governance truth already exists in Ed

Today, `ifitwala_ed` already has the authoritative governance contract:

- `File Classification` enforces required governance fields and file attachment alignment
- `file_dispatcher.create_and_classify_file(...)` is the authoritative write path
- version/current-state semantics already exist on `File Classification`

This is the real governed source of truth.

### 1.2 Drive currently writes a shadow governance layer

After `ifitwala_drive` finalizes storage, it calls back into the Ed dispatcher, then creates:

- `Drive File`
- `Drive File Version`
- `Drive Binding`

The problem is that `Drive File` copies many fields that already exist on `File Classification` and `File`:

- attached doctype / name
- owner doctype / name
- organization / school
- primary subject
- data class
- purpose
- retention policy
- slot
- content hash

That creates two persistent places that both look governance-authoritative.

### 1.3 Upload-session duplication is acceptable; persistent governance duplication is not

`Drive Upload Session` is fine as a first-class lifecycle record. It is temporary operational state.

The waste is not the session itself. The waste is persisting a second long-lived governance shell after finalization.

### 1.4 Versioning is duplicated too early

`Drive File Version` exists, but current code uses it mostly as a mirrored initial version row.

Meanwhile Ed already tracks:

- `File Classification.version_number`
- `File Classification.is_current_version`
- `File.custom_version_no`
- `File.custom_is_latest`

That is too much version bookkeeping for the current product slice.

### 1.5 The current Drive UI is context-card browse, not a real drive

The current workspace is built around:

- workspace home sections
- context targets
- context browse
- system-materialized `Drive Folder` trees

That is useful for deep links, but it does not behave like a real file workspace. Users want:

- a left rail
- folders
- files
- breadcrumbs
- sortable lists
- one stable place to browse what they can read

For the current read-only requirement, the UX should optimize for navigation, not presentation.

---

## 2. Proposal: One Governance Truth, One Drive Read Model

### 2.1 Authoritative system of record

Keep as the only governance authority:

- `File`
- `File Classification`
- owning business doc in `ifitwala_ed`

These remain the legal truth for:

- attachment ownership
- primary subject
- slot
- data class
- purpose
- retention
- erasure posture
- current governed version

### 2.2 Drive becomes a lean platform/index layer

Drive should keep only fields that Ed does not already own.

Recommended persistent Drive record:

- `file`
- `source_upload_session`
- `canonical_ref`
- `storage_backend`
- `storage_object_key`
- `preview_status`
- `scan_status` or processing status later
- `is_private`
- optional `folder_path` or `path_key` for browse projection

Recommended removal from persistent Drive file metadata:

- attached doctype
- attached name
- owner doctype
- owner name
- organization
- school
- primary subject type / id
- data class
- purpose
- retention policy
- slot
- duplicated content hash if Ed already keeps it

Those should be resolved by join from `file -> File Classification -> File`.

### 2.3 Rename the concept if needed

If keeping the doctype, rename conceptually from `Drive File` to something like:

- `Drive Asset`
- `Drive File Index`
- `Drive Blob`

The current name encourages it to grow into a second file authority.

### 2.4 Reduce `Drive Binding` to non-owning reuse only

Keep `Drive Binding`, but only for cases where a file must appear in an additional browse context beyond its authoritative owner.

Use `Drive Binding` for:

- organization media visible in multiple scopes
- future reuse / shared references
- future workspace collections

Do not require a primary binding for every governed file when the owning context is already represented by `File Classification.attached_doctype`, `attached_name`, and `slot`.

Primary owner browse should be derivable, not separately stored.

### 2.5 Defer `Drive File Version`

For the current stage, remove or freeze `Drive File Version` as a required artifact for every upload.

Use existing Ed version semantics until Drive truly supports:

- replace version
- immutable object lineage
- version-to-version preview history
- cross-storage replacement workflows

Add a dedicated Drive version table only when those behaviors are real, not anticipated.

---

## 3. Proposal: Leaner Bridge Between Ed And Drive

### 3.1 Current bridge is too wide and too coupled

Right now:

- Ed calls many workflow-specific Drive APIs
- Drive imports Ed workflow modules for admissions, tasks, and media
- Drive re-validates workflow contracts with business-specific code
- post-finalize mutations live in Drive integration modules

That creates cross-repo duplication of workflow knowledge.

### 3.2 Replace per-workflow glue with a contract bridge

Use one bridge contract between Ed and Drive.

Recommended flow:

1. Ed resolves the authoritative governed upload contract for a workflow.
2. Ed sends that contract to Drive when creating the upload session.
3. Drive stores the contract snapshot on the session.
4. On finalize, Drive calls one Ed bridge hook to revalidate the contract and run post-finalize business mutations.
5. Drive then persists only storage/access/read-model state.

### 3.3 Contract contents

The contract should contain only what Drive needs:

- owner doc
- attached doc
- governance payload
- private/public flag
- optional browse projection metadata
- integration key
- optional post-finalize action hints

This lets Ed own business semantics while Drive owns upload/storage mechanics.

### 3.4 Where the code should live

Move workflow-specific contract building and post-finalize business mutation into Ed.

Good target shape:

- `ifitwala_ed.integrations.drive.contracts`
- registry keyed by workflow type, for example:
  - `task_submission_artifact`
  - `task_resource`
  - `applicant_document`
  - `applicant_profile_image`
  - `organization_media`

Drive then only needs:

- generic upload session API
- generic finalize API
- generic grant API
- generic browse API

### 3.5 Keep one exception list very small

Legacy flows that still bypass Drive should be removed or explicitly isolated.

Example: desk applicant image upload still has a direct local dispatcher path in Ed. That should either:

- move onto the same Drive upload-session bridge

or

- be declared a temporary legacy exception and scheduled for removal

but it should not remain as an accidental parallel system.

### 3.6 High-concurrency requirements

This proposal must follow the active high-concurrency posture already locked in `ifitwala_ed`:

- synchronous truth is minimal
- heavy recomputation is deferred
- cache correctness beats hit rate
- hot request paths stay bounded

For Drive specifically, that means:

- `create_upload_session` and `finalize_upload` must be explicitly idempotent under retries, double-submits, and client reconnects
- lock scope must stay narrow: per upload session, per logical file identity, or per binding key, never broad tenant- or organization-wide locks
- unique constraints, not just application checks, should enforce session keys, canonical refs, and any binding primary keys that must remain unique
- preview generation, malware scanning, indexing, usage/quota refresh, and derivative generation stay off the hot path
- browse endpoints must read from indexed metadata or read models, not rebuild large trees or context aggregations on every request
- Drive must not make synchronous calls into Ifitwala_Press on the request path

Recommended API additions:

- `client_request_id` or equivalent idempotency token on session creation
- idempotent finalize semantics keyed by upload session
- explicit `processing` / `ready` states for async file enrichments

### 3.7 Storage and Ifitwala_Press boundary

This proposal should be refined from “GCS-ready” to “provider-neutral object-storage ready”.

Ifitwala_Press should own the environment storage profile, including:

- storage provider
- bucket or container binding
- tenant/environment prefix strategy
- region / endpoint
- quota
- worker profile for heavy Drive jobs
- credential / identity delivery

Drive should not query Press live during normal file requests.

Instead, Press should provision or publish resolved environment config to the tenant runtime, and Drive should consume that local resolved config.

The storage contract should support at least:

- `Local Temporary`
- `GCS`
- `S3 Compatible`

That aligns with the current Press environment model and avoids baking GCS assumptions into the Drive domain.

### 3.8 S3-compatible storage design rules

To stay ready for S3-compatible object storage on Google Cloud under Press orchestration:

- the storage adapter contract must be based on object operations, not filesystem assumptions
- object finalization must not assume rename/move support; S3-compatible providers often require copy-plus-delete or multipart-complete semantics
- canonical refs and browse paths must remain provider-neutral
- neither Ed nor the UI may ever depend on bucket names, object URLs, or provider-specific path shapes
- signed upload and signed download generation must live behind the storage adapter
- metadata truth stays in DB; blob truth stays in object storage
- no long-lived embedded storage keys in app code; identity should come from Press-managed runtime configuration and platform secret handling

Immediate design implication:

the current `storage/base.py` abstraction should evolve from a `local`/`gcs` switch into a stable object-storage contract with concrete backends such as:

- `local`
- `gcs`
- `s3_compatible`

The rest of Drive should not care which one is active.

---

## 4. Proposed True Drive View

### 4.1 Product direction

For read-only V1, the Drive workspace should become a real governed file browser.

Not:

- a home of cards
- a list of contexts first
- a “pretty router”

But:

- a stable folder tree
- files and folders in the main pane
- breadcrumbs
- preview and download actions
- sorting by name / modified / type

The target interaction model should feel familiar to anyone who has used Google Drive:

- left navigation rail with stable roots and expandable folders
- top toolbar with current location, search/filter entry, and primary actions
- center pane as a dense folder/file list, not a card gallery
- breadcrumbs above the list
- row-based actions on hover or selection
- optional right-side detail panel later, but not required for V1

That does **not** mean copying Google Drive visually.
It means copying the useful navigation grammar:

- predictable tree
- quick scanning
- low-friction folder traversal
- stable file list
- obvious selection and open actions

### 4.2 Important rule

Folders are browse UX, not governance truth.

Permissions still come from the owning document and governance rules.

The folder tree is only a readable projection of governed files the user already has permission to see.

### 4.3 For current scope, prefer virtual folders over many persisted folder rows

Because this V1 is read-only, the folder tree should be a deterministic projection over governed metadata.

That is leaner than materializing many `Drive Folder` rows for every context.

Recommended approach:

- build folder paths deterministically from governance + owner context
- list folders by grouped path segments
- only persist folder records later if users can create/move/rename folders

If caching is needed, cache the projection. Do not make the cache the truth.

Under high concurrency, this also means:

- browse trees should be path/index driven
- expensive folder expansion should be incremental
- large “home” pages should not fan out across many contexts synchronously
- recent/recommended views should come from bounded read models, not repeated broad scans

### 4.4 Recommended top-level tree

Use a small number of stable roots:

- `My Drive`
- `Admissions`
- `Students`
- `Employees`
- `Teaching`
- `Media`

`My Drive` is a convenience view, not separate ownership.

### 4.5 Recommended deterministic paths

Examples:

- `Admissions / Applicants / <Applicant> / Documents / Identity`
- `Admissions / Applicants / <Applicant> / Documents / Academic`
- `Admissions / Applicants / <Applicant> / Profile`
- `Students / <Student> / Profile`
- `Employees / <Employee> / Profile`
- `Teaching / <Course> / Tasks / <Task> / Resources`
- `Teaching / <Course> / Tasks / <Task> / Submissions / <Student>`
- `Media / Organization / Logos`
- `Media / Schools / <School> / Logos`
- `Media / Schools / <School> / Gallery`

This is far closer to how users expect Drive to work.

### 4.6 How context deep-links should work

Context pages in Ed should deep-link into the same folder tree, not a different browse mode.

Examples:

- Task page “Open in Drive” opens `Teaching / <Course> / Tasks / <Task>`
- Applicant page “Open in Drive” opens `Admissions / Applicants / <Applicant>`
- Employee page “Open in Drive” opens `Employees / <Employee>`

This preserves context-first workflow entry while giving users one consistent workspace.

### 4.7 What should be visible in read-only V1

In folder view:

- folders first
- files second
- filename
- file type
- modified time
- source context badge
- preview action
- download action

In side rail:

- tree roots
- recent folders
- filters for file classes or contexts later

Not needed yet:

- move
- rename
- drag-and-drop
- freeform folder creation

### 4.8 Visual direction: Google Drive interaction model, Ifitwala_Ed visual language

The workspace should feel like:

- Google Drive in navigation behavior
- Ifitwala_Ed in color, typography, spacing, and tone

Recommended design rules:

- reuse existing Ifitwala_Ed token families such as `ink`, `leaf`, `canopy`, `moss`, `sky`, `sand`, `border`, and the current `Plus Jakarta Sans` / `DM Serif Display` pairing
- keep the shell cleaner and flatter than the current Drive hero-card layout
- use restrained surfaces and borders rather than large decorative marketing panels
- keep the left rail quiet and structural
- keep the main file list dense enough for real work
- use Ifitwala accent colors for state, selection, and focus rings rather than consumer-tech blues as the main brand language
- keep gradients subtle and background-only; navigation must read as a work tool, not a landing page

Recommended V1 layout:

- top app bar
- left tree rail
- main content panel with breadcrumbs + toolbar + table/list
- optional small status strip for indexing/preview state

Recommended row structure:

- icon
- filename
- context or slot badge
- modified time
- file type or subject
- preview/download actions

Recommended state styling:

- selected row uses Ifitwala leaf/canopy emphasis with accessible contrast
- folder rows and file rows are visually distinct but use the same grid
- system/governed state should be shown with compact badges, not large explanation blocks

Avoid:

- oversized hero headers
- card-per-folder layouts for the primary working view
- decorative dashboard KPIs at the top of the main browse surface
- a separate “context mode” visual language that breaks the mental model of one Drive

---

## 5. Concrete Keep / Remove / Change

### Keep

- `File`
- `File Classification`
- `Drive Upload Session`
- access grants in Drive
- provider-neutral storage adapter abstraction in Drive
- canonical refs in Drive
- preview / processing state in Drive
- narrow lock/idempotency utilities in Drive

### Shrink

- `Drive File` into a storage/access/read-model index only
- `Drive Binding` into optional non-owning reuse bindings only

### Remove or defer

- mandatory mirrored governance fields on `Drive File`
- mandatory `Drive File Version` creation for every upload
- per-workflow integration logic living inside Drive
- heavy dependence on persisted `Drive Folder` rows for read-only governed browse
- GCS-specific assumptions in the storage contract
- any design that requires synchronous Press lookups during upload, finalize, browse, preview, or download

---

## 6. Migration Plan

### Phase 1: Normalize authority

- declare `File Classification` the only governance truth
- stop adding new governance fields to Drive doctypes
- mark `Drive File Version` as deferred unless replace-version is implemented
- migrate desk applicant image onto the same bridge or explicitly retire that path
- audit all upload/finalize paths for idempotency and narrow lock scope

### Phase 2: Contract bridge

- replace Drive-side workflow modules with one generic bridge
- move contract building and post-finalize business mutations into Ed
- keep public API compatibility temporarily with thin wrappers
- add request-level idempotency tokens where the client can retry safely

### Phase 3: Read-model simplification

- shrink `Drive File` to storage/access/index fields only
- derive owner/classification fields by join
- create compatibility accessors so existing callers still work during migration
- make browse APIs path/index based rather than context-home fan-out based

### Phase 4: Storage portability and Press contract

- replace GCS-shaped language with provider-neutral object-storage language
- add first-class `s3_compatible` backend support
- define the Press-to-runtime storage profile contract
- ensure no provider-specific behavior leaks above the storage adapter

### Phase 5: True Drive browser

- add path-based browse API
- implement tree + folder listing UI
- deep-link all Ed contexts into real folder paths
- keep permissions inherited from owning docs

---

## 7. Why This Is Better

- one governance truth instead of two
- less drift between Ed and Drive
- smaller bridge surface between repos
- cleaner separation: Ed decides meaning, Drive decides storage/access/browse
- less migration pain later when storage backend changes
- safer under high concurrency and retry-heavy real school networks
- ready for Press-operated S3-compatible object storage on Google Cloud
- a real user-browseable workspace instead of a context-card launcher

---

## 8. Recommended Immediate Decision

If only one decision is made now, it should be this:

**`File Classification` remains the only authoritative governance record, and `ifitwala_drive` is reduced to upload/storage/access/read-model responsibilities.**

Everything else becomes much easier once that line is enforced.
