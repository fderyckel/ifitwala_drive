The exact generated markdown files are no longer available in the workspace, so I cannot paste them verbatim.

What I can do is reconstruct them cleanly here from the locked decisions we already made and from your existing file-governance notes. This version is the one I would treat as the working draft going forward.

---

# 1) Product principles and user flows

## Purpose

**Ifitwala_drive** is a separate Frappe app that acts as the governed file platform for **Ifitwala_Ed**.

It is **not** a generic consumer Drive clone.
It is **not** a free-form attachment layer.
It is **not** an independent business product.

It exists to make file-heavy workflows inside Ifitwala_Ed:

* fast,
* low-friction,
* secure,
* cost-aware,
* governance-safe,
* and ready for higher concurrency later.

This follows your locked rule that all files across Ifitwala_Ed must conform to one governance architecture, with one dispatcher boundary, deterministic ownership, slot semantics, and no direct business-logic bypasses.

## Product position

The right product position is:

* **Context first**
* **Drive second**

Meaning:

* Most users should encounter files through context:

  * Task
  * Submission
  * Lesson
  * Student Applicant
  * Student Portfolio
  * Employee
  * Referral
  * Organization Media
* But users must still be able to browse, search, and manage files in a proper Drive-like surface when needed.

So the UX is hybrid:

* **Primary UX**: contextual, workflow-based
* **Secondary UX**: navigable Drive/browser surface

## Core product principles

### 1. Frictionless common actions

The most common jobs must be nearly thoughtless:

* attach a resource to a lesson/task
* reuse a prior teacher resource
* upload student work
* give feedback files
* distribute a blank template to a whole student group
* relink or reuse governed media

### 2. Governance without user burden

Users should not have to think about storage paths, retention, routing, or backend location.
The system decides and returns canonical references. Your notes already lock this: storage is system-decided, not user-decided, and UI must consume canonical URLs/references only.

### 3. File ≠ business record

A file is evidence, attachment, media, or artifact.
It is not the grade, not the academic decision, not the applicant outcome, not the transcript.
That separation is already locked for tasks and assessments.

### 4. No orphan files

Every governed file must belong to one owning business document and one semantic slot. Files do not float free.

### 5. Reuse before re-upload

For teacher resources and organization media, the system should make reuse the first move, not repeated upload. Your organization media rules already enforce a reuse-first picker model.

### 6. Safe by default

Education is a soft target. Students will probe. Families will make mistakes. Staff will upload wrong things. So:

* no raw path trust,
* no direct bucket exposure,
* no permissive long-lived file links,
* no UI-only permission enforcement.

## Primary user journeys

## A. Teacher adds resources to a task

Target UX:

* click “Add Resource”
* pick from:

  * My Resources
  * Course/Team Resources
  * Organization/School Resources
  * Upload New
  * Create Blank Template
* attach instantly to task

The system handles:

* governed storage
* metadata
* slot classification
* versioning
* resource binding

## B. Teacher distributes a blank template to a whole student group

This is one of the most important flows.

Recommended product model:

* the teacher starts from a template/resource,
* creates a per-student workspace or submission work item,
* the system only creates actual derivative file blobs when truly needed.

Do **not** default to blind binary duplication for every student if the workflow can be modeled more cheaply and more cleanly.

This keeps:

* storage cost down,
* versioning clearer,
* submission state cleaner.

## C. Student submits work

Student should only experience:

* open task,
* add or replace work,
* see status,
* submit.

The system must enforce:

* slot = `submission`
* ownership rooted in student/task submission context
* versioning if replacements are allowed
* retention and deletion independence from grades.

## D. Teacher gives feedback

Teacher can:

* upload feedback file,
* annotate later,
* replace with new version,
* attach rubric evidence if needed.

System enforces:

* dedicated slots like `feedback` and `rubric_evidence`
* version-safe replacement
* independent retention behavior.

## E. Admissions uploads

Admissions must feel simple for families, but under the hood remain stricter than teacher workflows.

Locked rule:

* admissions files are always primarily owned by the **Student Applicant**, not Student or Guardian.

That rule stays.

## F. Drive browsing

Drive browsing exists for:

* teachers managing reusable resources,
* admins managing governed files,
* staff searching/document lookup,
* organization media management.

But the product must avoid turning every workflow into “go browse a folder.”






