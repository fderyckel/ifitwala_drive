from __future__ import annotations

import importlib
import sys
import types


def test_hourly_runs_expire_prune_and_reconcile(monkeypatch):
	sys.modules.pop("ifitwala_drive.tasks", None)
	derivatives_module = types.ModuleType("ifitwala_drive.services.files.derivatives")
	derivatives_module.prune_stale_derivatives_service = lambda: None
	derivatives_module.reconcile_preview_derivatives_service = lambda: None
	sys.modules["ifitwala_drive.services.files.derivatives"] = derivatives_module

	sessions_module = types.ModuleType("ifitwala_drive.services.uploads.sessions")
	sessions_module.expire_abandoned_upload_sessions_service = lambda: None
	sys.modules["ifitwala_drive.services.uploads.sessions"] = sessions_module

	module = importlib.import_module("ifitwala_drive.tasks")
	calls: list[str] = []

	monkeypatch.setattr(
		module,
		"expire_abandoned_upload_sessions_service",
		lambda: calls.append("expire"),
	)
	monkeypatch.setattr(
		module,
		"prune_stale_derivatives_service",
		lambda: calls.append("prune"),
	)
	monkeypatch.setattr(
		module,
		"reconcile_preview_derivatives_service",
		lambda: calls.append("reconcile"),
	)

	module.hourly()

	assert calls == ["expire", "prune", "reconcile"]
