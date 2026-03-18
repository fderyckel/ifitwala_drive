# Ifitwala Drive North Star V1

## Status

Locked as the working product frame for current implementation.

This note exists to prevent drift.

Ifitwala_drive is not trying to become a generic cloud drive.
It is the governed file product for Ifitwala_Ed.

The standard is:

* easy to find the right file in the educational workflow
* hard to create governance chaos
* possible to keep personal and shared teaching resources organized

---

## 1. Product Definition

Ifitwala_drive is:

* a governed file authority for Ifitwala_Ed
* a contextual file experience for educators, students, admissions, and staff
* a human-browseable workspace layer on top of governed file ownership

Ifitwala_drive is not:

* a generic attachment bucket
* a raw storage browser
* a second permission universe
* a folder system where folders define legal truth

The core rule remains:

> users should usually find files from their educational context first, and from Drive workspaces second.

---

## 2. Primary User Promise

Users should be able to do four things well:

1. find files from the record they are already working in
2. browse clear human-semantic folders when they need orientation or reuse
3. keep teaching resources organized without turning the system into chaos
4. trust that sensitive files stay governed and do not leak through weak file handling

If we are not improving one of those four things, we are probably drifting.

---

## 3. V1 Product Shape

V1 has two surfaces.

### 3.1 Contextual Surfaces First

These are the primary product surface.

Users should reach files directly from Ifitwala_Ed contexts such as:

* `Applicant`
* `Task`
* `Task Submission`
* `Student`
* `Course`
* `Activity`
* `Organization`
* `School`

Examples:

* `Applicant -> Documents / Profile`
* `Task -> Resources`
* `Task Submission -> Submission Artefacts`
* `Student -> Profile / Academic Year / Courses / Tasks`
* `Organization / School -> Media`

This is the main UX.
Users should not need to remember storage locations to do normal work.

### 3.2 Drive Workspaces Second

Drive browsing exists to support navigation, reuse, cleanup, and orientation.

The first workspace set should be:

* `My Resources`
* `Shared Course Resources`
* `Reusable Templates`
* `Recent`
* `Archived`

These are useful because educators do need some freedom and library behavior.
But these workspaces must still sit on top of governed file ownership.

---

## 4. What Must Be Strictly Governed

The following stay system-managed and context-anchored:

* applicant documents
* applicant health documents
* applicant profile and guardian images
* student profile images
* task submission artefacts
* organization and school media
* portfolio or journal artefacts once the Ed owner contract is locked

For these flows:

* owner is authoritative
* slot is authoritative
* retention is authoritative
* folder is browse metadata only
* physical storage path is irrelevant to the user

These are not user-managed folders.

---

## 5. Where Users Get Freedom

Teachers and educators do need some controlled freedom.

V1 should allow freedom in:

* personal teaching resource organization
* shared course resource libraries
* reusable resource collections and templates
* workspace browsing, filtering, and cleanup

That freedom is still bounded:

* files remain anchored to a valid governing context
* reuse should prefer logical references or bindings before blob duplication
* moving a file in a workspace must not rewrite governance truth
* visibility still resolves from the owning document and policy rules

This is the balance:

* strict for workflow evidence
* flexible for reusable teaching resources

---

## 6. Folder Philosophy

Folders are part of the product, but only as human navigation.

Folders must help users answer:

* where should I look
* what kind of file is this
* what belongs together

Folders must not become:

* the source of permission truth
* the source of retention truth
* the source of ownership truth

The model is:

* governed owner underneath
* bindings for projections and reuse
* human folders for browse and orientation

This is how we get "Google Drive feel" without losing school-grade governance.

---

## 7. V1 Browse Surfaces To Lock

The first browse surfaces that matter are:

1. `Admissions / Applicant / <applicant> / Documents / ...`
2. `Admissions / Applicant / <applicant> / Profile / ...`
3. `Student / <student> / Profile`
4. `Student / <student> / Academic Year / <year> / Courses / <course> / Tasks / <task>`
5. `Course / <course> / Resources`
6. `Organization Media / Organization / ...`
7. `Organization Media / Schools / <school> / ...`
8. `Teacher / <teacher> / My Resources`
9. `Teacher / <teacher> / Shared Course Resources`

If a new implementation slice does not clearly improve one of these surfaces, it should be questioned.

---

## 8. V1 Explicitly Out Of Scope

To avoid drift, V1 is not trying to solve all file problems.

Out of scope unless separately locked:

* generic end-user freeform Drive for everyone
* detached cross-tenant sharing
* a new ACL model separate from Ed visibility
* raw storage browser UI
* document authoring suite behavior
* broad public-link sharing for governed private files
* complex desktop-sync style file-system metaphors

If a proposed feature pulls us toward one of these, it needs a separate decision.

---

## 9. Implementation Gate

Before shipping more Drive work, ask:

1. Does this make files easier to find in Ifitwala_Ed context?
2. Does this support human-semantic browsing without making folders governance truth?
3. Does this preserve owner, slot, retention, and canonical reference discipline?
4. Does this give educators useful freedom without opening chaos?

If the answer to any of those is no, stop and re-evaluate.

---

## 10. Practical Interpretation For Current Work

What we have already built is still aligned:

* Drive file identity
* Drive file versioning
* system-managed folder placement for key flows
* browse APIs
* concurrency hardening

What must happen next is not uncontrolled backend expansion.

The next work should stay tied to:

* the first browse surfaces above
* teacher resource workspace rules
* migration safety
* UI retrieval clarity

That keeps Ifitwala_drive as the file-management product for Ifitwala_Ed, not an abstract storage project.
