from __future__ import annotations

import importlib
import sys
import types


def test_drive_workspace_context_falls_back_when_vite_entry_is_missing(tmp_path, monkeypatch):
	frappe = types.ModuleType("frappe")
	frappe.get_app_path = lambda app_name: str(tmp_path)
	frappe.sessions = types.SimpleNamespace(get_csrf_token=lambda: "csrf-token")
	monkeypatch.setitem(sys.modules, "frappe", frappe)
	sys.modules.pop("ifitwala_drive.templates.pages.drive_workspace", None)

	module = importlib.import_module("ifitwala_drive.templates.pages.drive_workspace")
	monkeypatch.setattr(
		module,
		"get_vite_assets",
		lambda **kwargs: (
			"/assets/ifitwala_drive/vite/assets/src/apps/workspace/main.ts.missing.js",
			["/assets/ifitwala_drive/vite/assets/main.css"],
			["/assets/ifitwala_drive/vite/assets/chunk.js"],
		),
	)

	context = types.SimpleNamespace()
	module.get_context(context)

	assert context.title == "Drive Workspace"
	assert context.csrf_token == "csrf-token"
	assert context.has_vite_workspace is False
	assert context.vite_css == []
	assert context.vite_preload == []
