# Coupling with Ifitwala_Ed

## Non-negotiable position

Ifitwala_drive is separate as an app boundary, but **tightly coupled to Ifitwala_Ed at all times**.

That means:

* Ifitwala_Ed remains the workflow authority.
* Ifitwala_drive remains the file authority.
* Neither should drift into the other’s job.

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
