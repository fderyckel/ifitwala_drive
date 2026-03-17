#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

python3 -m ruff check ifitwala_drive
python3 -m ruff format --check ifitwala_drive
python3 -m pytest -q \
	ifitwala_drive/ifitwala_drive/doctype/drive_upload_session/test_drive_upload_session.py \
	ifitwala_drive/tests/test_task_submission_upload_flow.py
