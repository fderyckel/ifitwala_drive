from __future__ import annotations

import importlib


def test_hourly_runs_prune_and_reconcile(monkeypatch):
	module = importlib.import_module("ifitwala_drive.tasks")
	calls: list[str] = []

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

	assert calls == ["prune", "reconcile"]
