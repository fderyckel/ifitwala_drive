### Ifitwala Drive

file managemetn for ifitwala_ed

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app ifitwala_drive
```

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
- the local pytest suite for the current Phase 1 upload/session tests

GitHub Actions runs the same script for pull requests targeting `main` and for pushes to `main`.

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

### License

mit
