### Ifitwala Drive

Governed file management for `ifitwala_ed`.

### Current Backend Status

Implemented core governed-file behavior now includes:

- upload session creation and authoritative finalize through the Drive boundary
- canonical `Drive File` creation with initial `Drive File Version` lineage
- version-safe replacement through `replace_drive_file_version`
- short-lived download and preview grants
- minimal `Drive Access Event` audit rows for upload, replace, download, preview, and erase actions
- `Drive Erasure Request` creation/execution for deterministic file-domain erasure

Current downstream contract note for `ifitwala_ed`:

- callers should persist `drive_file_id`, `drive_file_version_id`, and `canonical_ref` where useful
- delivery logic must continue to use Drive grants / canonical references, not guessed file paths
- replacement and erasure flows now have first-class Drive APIs and should not be re-invented in Ed business logic

### Current Workspace Behavior

The default Drive landing at `/drive_workspace` is now a governed home, not a
query-parameter instruction page.

Current home sections are derived from records the user can already `read`:

- `Reviewing`: open applicant review assignments, including role-based health review
- `My Drive`: the user's own employee, student, or applicant contexts
- `Folders`: readable governed root folders

If exactly one target is available, Drive auto-opens it.

Employee profile media now routes into a deterministic staff tree:

- `Employees / <employee> / Profile / Employee Image`

Browse remains permission-inherited from the owning document. Opening an
organization-level root does not expose child employee folders or files unless
the current user can read that employee's owning document.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app ifitwala_drive
```

For governed upload hardening and GCS direct uploads, the runtime also needs:

- `libmagic` available on the host/container for `python-magic`
- Application Default Credentials / Workload Identity for GCS when `backend_name = "gcs"`

On macOS, `libmagic` is typically provided by `brew install libmagic`.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/ifitwala_drive
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### Local Checks

Run the minimum local gate before pushing:

```bash
./scripts/run_local_checks.sh
```

This runs:

- `ruff check`
- `ruff format --check`
- the full Python test suite currently checked into `ifitwala_drive/tests`

GitHub Actions runs separate CI jobs for Ruff, the full Python suite, and the frontend type-check/build path for pull requests targeting `main` and for pushes to `main`.

### Frontend Build

The Drive workspace Vue app lives in `ifitwala_drive/ui-spa` and builds into
`ifitwala_drive/public/vite`.

Use the repo root wrapper so the build path stays aligned with Bench:

```bash
yarn build
```

This runs the `ui-spa` dependency install and the Vite production build. Once
Node and Yarn are available, `bench build --app ifitwala_drive` will invoke the
same root build script.

If the compiled Vite entry is missing at runtime, the Drive page now falls back
to the legacy workspace JS/CSS surface instead of rendering a broken SPA mount.

Useful commands:

```bash
yarn type-check:spa
yarn dev:spa
```

Runtime baseline:

- Node `>=24`
- Yarn `1.22.22` via Corepack or equivalent

This machine currently has neither `node` nor `yarn`, so frontend build
verification must happen on a workstation or CI runner with that toolchain.

### Documentation Rule

Whenever code changes in this repo, update the relevant docs with:

- the technical changes
- the design or architecture choice behind them
- any downstream impact on `ifitwala_ed`

If the change affects how `ifitwala_ed` delivers files, that downstream app must be informed and the contract change must be documented explicitly.

### License

mit
