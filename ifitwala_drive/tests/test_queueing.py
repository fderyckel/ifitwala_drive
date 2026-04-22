from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe(*, workers=None):
	frappe = types.ModuleType("frappe")
	frappe.get_conf = lambda: {"workers": workers or {}}
	sys.modules["frappe"] = frappe


def _load_module():
	_purge_modules("ifitwala_drive.services.queueing")
	return importlib.import_module("ifitwala_drive.services.queueing")


def test_resolve_enqueue_queue_falls_back_to_standard_frappe_queues():
	_install_fake_frappe()
	module = _load_module()

	assert module.resolve_enqueue_queue("drive_short") == "short"
	assert module.resolve_enqueue_queue("drive_default") == "default"
	assert module.resolve_enqueue_queue("drive_heavy") == "long"


def test_resolve_enqueue_queue_preserves_configured_custom_drive_queue():
	_install_fake_frappe(workers={"drive_default": {"timeout": 5000, "background_workers": 2}})
	module = _load_module()

	assert module.resolve_enqueue_queue("drive_default") == "drive_default"
