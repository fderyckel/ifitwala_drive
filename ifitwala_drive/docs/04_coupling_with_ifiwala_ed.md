# Coupling with Ifitwala_Ed

## Non-negotiable position

Ifitwala_drive is separate as an app boundary, but **tightly coupled to Ifitwala_Ed at all times**.

That means:

* Ifitwala_Ed remains the business, permission, and workflow authority.
* Ifitwala_drive remains the file-platform authority.
* Neither should drift into the other’s job.

In practical terms:

* Ed decides what a file means.
* Ed decides whether the user can act on the owning record.
* Drive decides how the file is uploaded, stored, secured, granted, previewed, and browsed.
* Drive folder trees are browse projections, not governance truth.

## Integration rule

Ifitwala_Ed should stop thinking in:

* raw `File`
* raw attachment path
* generic upload widget

And start thinking in:

* Drive resource
* Drive submission artifact
* Drive media reference
* Drive upload session
* Drive canonical file/ref URL

Important boundary:

* Ifitwala_Ed builds the governed upload contract
* Ifitwala_drive validates contract completeness at the boundary
* Ifitwala_drive must not become the place where admissions, task, or media workflow rules are authored

### MIME boundary rule

For any Ed wrapper that sends `mime_type_hint` to Drive:

* `mime_type_hint` describes the expected file bytes, not the outer HTTP request envelope
* Ed must derive it from the uploaded file object when available, typically `request.files["file"].mimetype` or `.content_type`
* if no trustworthy file-object MIME is available, Ed should fall back to `filename_original`
* Ed must never forward `frappe.request.mimetype` or the top-level request `Content-Type` from a multipart upload endpoint, because on `upload_file`-style flows that value is usually `multipart/form-data`
* Drive must continue inspecting the uploaded bytes at finalize time and fail closed on mismatches

Concrete anti-pattern:

* browser uploads that arrive through `/api/method/upload_file` often have `frappe.request.mimetype == "multipart/form-data"`
* forwarding that value to Drive is a contract bug and will cause finalize-time rejection when the bytes are actually `image/png`, `image/jpeg`, `application/pdf`, and so on

Cross-app deployment rule:

* if `Ifitwala_Ed` starts calling a new `ifitwala_drive.api.*` wrapper, that wrapper export is part of the runtime contract
* the thin API export and the underlying integration service must ship together
* `bench clear-cache` is not sufficient for new Python exports; running app processes must be restarted after deploy
* browser testing is not valid until the deployed module surface is verified from bench console

Recommended verification:

```python
import ifitwala_drive.api.media as m
hasattr(m, "upload_guardian_image")
m.__file__

import ifitwala_drive.services.integration.ifitwala_ed_media as i
hasattr(i, "upload_guardian_image_service")
i.__file__
```

## Example integrations

### Task resource

Task stores:

* bound resource IDs / canonical refs

Drive stores:

* actual file/resource metadata
* versions
* folder placement
* preview state

### Task submission

Task Submission stores:

* one or more Drive artifact references

Drive stores:

* file versions
* slot `submission`
* student subject ownership
* retention metadata

This preserves your locked rule that deleting student files must not break grades or analytics.

### Org Communication attachment

Org Communication stores:

* the authored class announcement
* attachment rows shown in archive/detail
* external links when the teacher shares a URL instead of uploading a file

Drive stores:

* the governed class-communication file
* one deterministic attachment slot per row
* folder placement under the authoritative course and student-group context
* preview/download grants for archive/history access

Boundary rule:

* Ed owns who can see the communication and whether the author can still access their own archive copy
* Drive owns upload, classification, binding, storage, preview, and grant issuance

### Admissions

Student Applicant stores:

* required document refs
* review state

Drive stores:

* applicant-owned files
* slots like `identity_passport`, `prior_transcript`, etc.

### Organization/school media

Ifitwala_Ed surfaces continue to use:

* organization media picker
* governed upload flow
* canonical references

This already matches your organization-media extension.

## UX guidance for coupling

### Context first

Inside Ifitwala_Ed surfaces, users should mostly see:

* Add resource
* Reuse resource
* Upload work
* Replace submission
* Choose organization media

not:

* “browse bucket”
* “pick random storage path”

### Drive surface when needed

Provide a Drive browser for:

* teacher libraries
* course/shared resources
* admin search/retrieval
* organization media management

But keep the ownership rule clear:

* the folder tree is a Drive read model
* permission still roots in the owning Ed document
* folder membership is never the legal source of file visibility

---

# 5) Phased rollout

## Phase 0 — foundation

Goal:

* keep costs low
* lock architecture
* stop drift

Deliverables:

* Ifitwala_drive app skeleton
* canonical service boundary
* upload session model
* preserved classification/slot model
* object-storage abstraction
* Ed integration wrappers

## Phase 1 — first real governed flows

Migrate first:

* task resources
* task submissions
* applicant documents
* organization media

Why these first:

* highest product value
* strongest governance need
* already partially specified in your docs.

## Phase 2 — Drive UX

Add:

* teacher resource library
* shared team/course folders
* search/filter
* Drive browser
* resource reuse flows
* template/workspace distribution UX

## Phase 3 — processing and optimization

Add only when justified:

* richer previews
* derivative generation expansion
* scanning
* quota dashboards
* lifecycle automation
* cost analytics

## Phase 4 — Press-operated scale

When customer count/load justifies it:

* bucket policy automation
* worker topology by tenant class
* environment class policy
* cost and quota surfaces in Ifitwala_Press
* possible split of services/workers

## Things explicitly not to do too early

* full consumer-grade generic drive clone
* deep infra complexity before product fit
* PG-specific over-optimization as architecture center
* externalized permission graph systems before your simpler ownership/context model is exhausted
* blind mass file duplication for classroom workflows
