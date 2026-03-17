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

### License

mit
