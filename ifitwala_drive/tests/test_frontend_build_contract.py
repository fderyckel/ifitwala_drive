from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
	return json.loads(path.read_text(encoding="utf-8"))


def test_root_package_exposes_bench_build_wrapper_for_ui_spa():
	root_package = _load_json(ROOT.parent / "package.json")

	assert root_package["engines"]["node"] == ">=24"
	assert root_package["packageManager"] == "yarn@1.22.22"
	assert root_package["scripts"]["build"] == "yarn spa:install && yarn build:spa"
	assert "ifitwala_drive/ui-spa build" in root_package["scripts"]["build:spa"]
	assert "ifitwala_drive/ui-spa install --check-files" in root_package["scripts"]["spa:install"]


def test_ui_spa_package_matches_root_runtime_contract():
	root_package = _load_json(ROOT.parent / "package.json")
	spa_package = _load_json(ROOT / "ui-spa" / "package.json")

	assert spa_package["engines"]["node"] == root_package["engines"]["node"]
	assert spa_package["packageManager"] == root_package["packageManager"]


def test_pyproject_runtime_note_matches_frontend_packages():
	pyproject_text = (ROOT.parent / "pyproject.toml").read_text(encoding="utf-8")
	match = re.search(r'node = "([^"]+)"', pyproject_text)

	assert match is not None
	assert match.group(1) == ">=24"
