# Semantic Browse Proposal

## Bottom line

The current Drive browse surface is leaking internal folder identity into the UX.

That is happening in two ways:

1. `Drive Folder.name` is an opaque `DRF-*` key and must stay internal.
2. Several folder `title` values are currently derived from raw document names, which are also opaque in some Ifitwala_Ed records.

The fix is not to rename storage objects into human IDs.
The fix is to make browse a semantic projection layer:

- keep opaque internal folder IDs
- return human display labels from authoritative context
- collapse structural-only nesting that adds no user meaning

This stays aligned with the existing architecture rule that folders are navigation only, not governance truth.

---

## Current problems

### 1. Internal identifiers are visible in browse

Current code keeps `Drive Folder.name` opaque, which is correct:

- `DriveFolder.autoname()` builds `DRF-<sha1>` identifiers

But browse currently treats folder `title` as the full user-facing label without a separate semantic presentation layer:

- `ifitwala_drive/services/folders/browse.py`
- `ifitwala_drive/public/js/drive_workspace.js`
- `ifitwala_drive/ui-spa/src/apps/workspace/App.vue`

If a folder `title` is opaque, the user sees opaque browse.

### 2. Resolution uses raw record names as folder titles

Several folder branches are created with titles taken directly from business record names:

- student folder title = `student`
- employee folder title = `employee`
- task folder title = `task_name`
- course folder title = `course`
- school folder title = `school`
- applicant folder title = `student_applicant`

That is safe technically, but not semantic if those names are hashes or generated IDs.

### 3. Structural nesting is too literal

The current tree materializes many intermediate system-managed nodes even when they add little or no browse value.

Examples:

- `Employees / <employee> / Profile / Employee Image`
- `Student / <student> / Tasks / <task> / Submissions`
- `Admissions / Applicant / <applicant> / Documents / ...`

These paths are useful internally, but not every node needs to be a visible click target all the time.

### 4. Existing data may already contain poor titles

The screenshots strongly suggest there are already `Drive Folder` records whose `title` values are opaque.

So this is not only a frontend problem.
It also needs a presentation rule plus a backfill/migration for existing folders.

---

## Proposal

### 1. Treat folder identity and folder presentation as separate concerns

Keep these internal fields unchanged:

- `Drive Folder.name`
- `Drive Folder.system_key`
- `Drive Folder.path_cache`

Add a separate browse projection for user-facing semantics:

- `display_title`
- `display_caption`
- `display_path`
- `is_structural_only`

Rule:

- UI must never show `Drive Folder.name` to end users
- UI must not fall back from missing title to opaque ID
- if semantic presentation is unavailable, show a safe generic label instead of a hash

Example safe fallback:

- `Student`
- `Employee`
- `Task`
- `Course`
- `Folder`

Not:

- `DRF-2E6856437B1F8756`

### 2. Resolve labels through Ifitwala_Ed, not hard-coded schema guesses in Drive

Do not invent fieldnames inside Ifitwala_drive.

Instead, add an Ed bridge delegate for browse labels, for example:

- `resolve_drive_context_label(doctype, name)`
- or `resolve_drive_folder_presentation(...)`

That delegate should return the authoritative human label for records such as:

- `Student`
- `Employee`
- `Task`
- `Course`
- `School`
- `Student Applicant`

Why this boundary is correct:

- Drive should own file/folder navigation mechanics
- Ed should own business-document display semantics
- this avoids baking uncertain fieldnames into Drive

### 3. Visible folders should use semantic buckets, not storage-ish nodes

Visible structural titles should stay small and stable:

- `Admissions`
- `Applicant`
- `Students`
- `Employees`
- `Courses`
- `Tasks`
- `Resources`
- `Submissions`
- `Profile`
- `Documents`
- `Health`
- `Organization Media`

Visible entity nodes should use human labels from Ed.

Examples:

- `Employees / Jane Doe / Profile / Employee Image`
- `Students / Amina Khan / Tasks / Biology Quiz 3 / Submissions`
- `Courses / Grade 8 Science / Tasks / Lab Report / Resources`

If a secondary machine identifier is useful for admins, show it as subdued metadata, not as the primary folder label.

### 4. Collapse structural-only chains in browse

Add browse compaction rules for system-managed folders when all of the following are true:

- the node is system-managed
- it has exactly one readable child folder
- it contains no direct files
- it adds no distinct upload choice or policy meaning at that level
- it stays within the same business context

What this means in practice:

- personal/context views should open at the first meaningful node
- intermediate empty nodes should be skipped or flattened in the UI
- breadcrumbs may still preserve the semantic path, but the list view should not force redundant clicks

Examples:

- Employee context can land directly on `Profile` or `Employee Image`
- Student submission context can land on the actionable submission folder instead of exposing every empty ancestor

### 5. Home should prioritize contexts over raw roots

The current workspace still exposes generic readable roots.

That is useful for admins, but not for normal user orientation.

Proposal:

- keep root folders for admin/scoped browse
- prefer context cards for normal users
- hide or de-emphasize generic system roots when they only lead to one readable context chain

This matches the product rule that Drive should be context-first.

### 6. Backfill existing folder titles

Existing folders with opaque titles should be repaired without changing identity.

Migration rules:

- do not change `Drive Folder.name`
- do not change `Drive Folder.system_key`
- recompute `title`, `slug`, and descendant `path_cache`
- only backfill system-managed folders where title is clearly non-semantic

Non-semantic heuristics:

- title equals folder `name`
- title matches `DRF-[A-F0-9]+`
- title is an owner/context raw identifier and a better semantic label is available from Ed

---

## Recommended implementation order

### Phase 1. Stop the leak in browse

Changes:

- extend folder browse responses with semantic display fields
- update both renderers to use display fields only
- remove all user-facing fallback to raw folder IDs

Files likely affected:

- `ifitwala_drive/services/folders/browse.py`
- `ifitwala_drive/public/js/drive_workspace.js`
- `ifitwala_drive/ui-spa/src/apps/workspace/App.vue`
- `ifitwala_drive/ui-spa/src/features/workspace/types.ts`

This phase is low risk and immediately improves the screenshots you shared.

### Phase 2. Introduce Ed-backed label resolution

Changes:

- add bridge delegate(s) in Ifitwala_Ed for semantic folder labels
- update folder resolution to use semantic titles instead of raw document names

Files likely affected:

- `ifitwala_drive/services/folders/resolution.py`
- `ifitwala_drive/services/integration/ifitwala_ed_bridge.py`
- matching delegate implementation in Ifitwala_Ed

This phase fixes new folder creation.

### Phase 3. Collapse redundant hierarchy in browse

Changes:

- add compaction logic in browse services
- only show meaningful nodes by default
- preserve full semantic path in breadcrumbs where useful

This phase improves UX without changing governance.

### Phase 4. Run a title backfill

Changes:

- patch existing bad folder titles
- rebuild slugs/path caches
- add tests for migrated browse output

This phase fixes legacy data already visible to users.

---

## Acceptance criteria

The work is done only if all of the following are true:

- no end-user browse surface shows `DRF-*`
- folder names shown to users are semantic and context-aware
- folder identity remains opaque and internal
- browse hierarchy is shallower when intermediate nodes are empty/system-only
- no governance rule moves from file classification into folder naming
- canonical refs, upload wrappers, and slot semantics remain unchanged
- tests cover both new folder creation and legacy-folder browse rendering

---

## Explicit non-goals

This proposal does not do any of the following:

- make folders governance truth
- rename storage keys to human labels
- infer governance from folder paths
- create a second ACL system
- replace context-first upload flows with generic folder uploads

---

## Code paths behind this proposal

Current internal folder ID generation:

- `ifitwala_drive/ifitwala_drive/doctype/drive_folder/drive_folder.py`

Current folder title creation from raw record names:

- `ifitwala_drive/services/folders/resolution.py`

Current browse serialization:

- `ifitwala_drive/services/folders/browse.py`

Current legacy UI rendering:

- `ifitwala_drive/public/js/drive_workspace.js`

Current SPA rendering:

- `ifitwala_drive/ui-spa/src/apps/workspace/App.vue`
