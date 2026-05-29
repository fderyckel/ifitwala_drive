from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe():
	def _throw(message, exc=None):
		raise RuntimeError(message)

	class Document:
		def __init__(self, data=None):
			for key, value in (data or {}).items():
				setattr(self, key, value)

		def get(self, key, default=None):
			return getattr(self, key, default)

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")
	document.Document = Document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document


def test_drive_binding_rejects_retired_lesson_binding_roles():
	_purge_modules(
		"frappe",
		"frappe.model",
		"frappe.model.document",
		"ifitwala_drive.ifitwala_drive.doctype.drive_binding.drive_binding",
	)
	_install_fake_frappe()
	module = importlib.import_module("ifitwala_drive.ifitwala_drive.doctype.drive_binding.drive_binding")

	for binding_role in ("lesson_resource", "lesson_activity_resource"):
		doc = module.DriveBinding({"binding_role": binding_role})
		try:
			doc._validate_binding_role()
		except RuntimeError as exc:
			assert str(exc) == f"Invalid binding role for Drive Binding: {binding_role}"
		else:
			raise AssertionError(f"{binding_role} should be rejected")


def test_drive_binding_accepts_current_curriculum_binding_role():
	_purge_modules(
		"frappe",
		"frappe.model",
		"frappe.model.document",
		"ifitwala_drive.ifitwala_drive.doctype.drive_binding.drive_binding",
	)
	_install_fake_frappe()
	module = importlib.import_module("ifitwala_drive.ifitwala_drive.doctype.drive_binding.drive_binding")

	doc = module.DriveBinding({"binding_role": "supporting_material"})
	doc._validate_binding_role()
