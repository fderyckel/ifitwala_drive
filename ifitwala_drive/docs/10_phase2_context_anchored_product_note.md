# Phase 2 Product Note: Context-Anchored Findability

## Status

Working note for the next product phase.

This note refines the existing locked direction:

* **Ifitwala_Ed remains the workflow authority**
* **Ifitwala_drive remains the mandatory file execution boundary**
* **Context-first retrieval becomes the primary product advantage**

It does not replace the existing governance rules. It clarifies how the next phase should feel to users.

---

## Bottom line

`ifitwala_drive` should not become a generic file bucket with better search.

It should become a **context-aware file system for schools** built on top of the structured reality already known by `ifitwala_ed`.

The guiding product promise for this phase is:

> You do not have to remember where a file is. Ifitwala already knows what it belongs to.

This is the product edge over generic Drive tools.

---

## Core product rule

**A file must be findable by context first, not by remembered location.**

Primary retrieval should come from school reality already known by the system, such as:

* task
* submission
* course
* student group
* term
* student
* applicant
* employee
* organization
* school
* website/media context

Folders may exist, but they are secondary. They help humans browse. They do not create the file's meaning.

---

## Product balance to preserve

The correct balance for this phase is:

### Deterministic underneath

Every governed file should have:

* a stable file identity
* an authoritative owner/binding context
* one or more semantic anchors
* a clear role or slot
* permission inheritance from the owning record
* predictable retrieval routes

### Flexible on top

Users, especially teachers, should still be able to:

* set a display title
* add tags
* place an item in a folder or collection
* star or pin items
* keep personal library areas
* reuse a resource across contexts

Freedom should augment findability, not create it from scratch.

---

## Product model

The next phase should treat the domain as three separate layers.

### 1. Files

The governed file object with canonical identity, storage abstraction, version lineage, and policy-controlled delivery.

### 2. Bindings

The system-known reason the file matters.

Examples already aligned with existing Drive direction include:

* task resource
* submission artifact
* applicant document
* portfolio artifact
* student image
* employee image
* organization media

Bindings are where determinism comes from.

### 3. Collections, folders, and saved views

Human browsing surfaces such as:

* My Resources
* Shared Course Resources
* Department Shared
* School Media
* Admissions Review Docs

These are where user freedom comes from.

Collections are not the governance truth.

---

## Hard rule to lock

**Every file must have a system-known context anchor. Not every file must have a user-chosen folder.**

This should be treated as the key product rule for the next phase.

That means:

* every upload must create or attach to at least one context anchor
* folder placement may be optional
* important files must never depend on naming discipline or folder memory to be found again

---

## Retrieval model

Every important file should have at least two retrieval paths:

* a **context path**
* a **work path**

### Context path

Guaranteed retrieval through the owning or bound workflow surface.

Examples:

* student submission from the task, submission, and student surfaces
* applicant document from the applicant surface
* employee image from the employee record
* organization media from organization or school media surfaces

### Work path

Guaranteed retrieval through a teacher or staff work surface.

Examples:

* recent uploads
* reusable resource library
* course resource library
* department shared resources
* school media library

Search and filters should strengthen these paths, not act as the only rescue plan.

---

## Browse model

Browse should be designed in this order:

### 1. Context surfaces first

This should be the main way users encounter files.

Examples:

* task files
* student files
* submission files
* applicant files
* employee files
* organization media

### 2. Work surfaces second

This is where teachers and admins manage reusable material.

Examples:

* My recent uploads
* My teaching resources
* shared course resources
* department shared resources
* school media library

### 3. Structured search and filters third

Search should be structured around ERP reality, not only full text.

Important filters include:

* course
* student group
* term
* owner type
* slot
* file type
* uploader
* school
* date used
* binding role

### 4. Folders as optional human organization

Folders remain useful for:

* teacher resource libraries
* shared resource areas
* media assets
* department archives

Folders should not be required for:

* submissions
* profile images
* applicant identity documents
* other governed workflow files whose retrieval already comes from context

---

## Reuse-first behavior

Reuse should become first-class for reusable assets.

The default teacher experience should favor:

* reuse from last term or last year
* reuse from course resources
* reuse from personal library
* reuse from department or school shared resources
* attach existing file to a new task or context

Blind re-upload should not be the dominant path for reusable resources.

---

## What not to copy from generic Drive products

The next phase should explicitly avoid these assumptions:

* folder equals truth
* search is the main rescue plan
* user naming discipline is the main organizing mechanism
* duplicates are the normal reuse model
* sharing semantics can live outside workflow context

Those assumptions are the source of school-file chaos that this product should avoid.

---

## Practical meaning of "deterministic enough"

If a teacher uploads a worksheet during task creation, the system should already know enough to make that file automatically discoverable through:

* the task
* the course
* the student group
* the teacher's recent resources
* the teacher's reusable library
* an optional chosen folder or collection

The teacher may still rename it, tag it, star it, or place it in a folder, but those actions should enrich retrieval rather than define it.

---

## MVP principles for the next phase

1. **Every upload creates a context anchor**, even when no folder is chosen.
2. **Every important file has at least two retrieval paths**: context plus work surface.
3. **Folders are optional by default** and only required in selected library areas.
4. **Search is structured**, not only full-text.
5. **Reuse is first-class** and should beat repeated upload for reusable resources.
6. **User-facing organization never depends on storage paths.**
7. **Shared resource libraries and governed workflow files are distinct product surfaces**, even when backed by the same Drive authority.

---

## Spec work this note should drive next

The next hard product spec should convert this note into explicit definitions for:

* file classes already in scope for Drive
* allowed context anchors per file class
* guaranteed retrieval routes per file class
* which surfaces are context surfaces vs work surfaces
* when folders are optional, required, or disallowed
* how personal libraries interact with ERP-driven bindings
* reuse flows versus version-replacement flows
* structured filter dimensions and default saved views

That spec should stay grounded in the already locked governance rules from `AGENTS.md` and the existing Drive docs.
