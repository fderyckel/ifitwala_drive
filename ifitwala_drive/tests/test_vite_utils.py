from __future__ import annotations

import json

from ifitwala_drive.website.vite_utils import get_vite_assets


def test_get_vite_assets_reads_manifest_entry_and_imports(tmp_path):
	manifest_path = tmp_path / "manifest.json"
	manifest_path.write_text(
		json.dumps(
			{
				"src/apps/workspace/main.ts": {
					"file": "assets/workspace.123.js",
					"isEntry": True,
					"css": ["assets/workspace.456.css"],
					"imports": ["assets/chunk.789.js"],
				},
				"assets/chunk.789.js": {
					"file": "assets/chunk.789.js",
					"imports": [],
				},
			}
		),
		encoding="utf-8",
	)

	js_entry, css_files, preload_files = get_vite_assets(
		app_name="ifitwala_drive",
		manifest_paths=[str(manifest_path)],
		public_base="/assets/ifitwala_drive/vite/",
		entry_keys=["src/apps/workspace/main.ts"],
	)

	assert js_entry == "/assets/ifitwala_drive/vite/assets/workspace.123.js"
	assert css_files == ["/assets/ifitwala_drive/vite/assets/workspace.456.css"]
	assert preload_files == ["/assets/ifitwala_drive/vite/assets/chunk.789.js"]


def test_get_vite_assets_falls_back_when_manifest_missing(tmp_path):
	js_entry, css_files, preload_files = get_vite_assets(
		app_name="ifitwala_drive",
		manifest_paths=[str(tmp_path / "missing.json")],
		public_base="/assets/ifitwala_drive/vite/",
		entry_keys=["src/apps/workspace/main.ts"],
	)

	assert js_entry == "/assets/ifitwala_drive/vite/main.js"
	assert css_files == []
	assert preload_files == []
