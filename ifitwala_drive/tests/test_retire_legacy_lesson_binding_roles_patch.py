from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def test_patch_retires_legacy_lesson_binding_roles_once():
	_purge_modules("frappe", "ifitwala_drive.patches.retire_legacy_lesson_binding_roles")
	updates = []

	class FakeDB:
		def table_exists(self, doctype):
			return doctype == "Drive Binding"

		def set_value(self, doctype, name, values, update_modified=False):
			updates.append((doctype, name, values, update_modified))

	def fake_get_all(doctype, filters=None, fields=None, order_by=None, limit=None):
		assert doctype == "Drive Binding"
		assert filters == {"binding_role": ["in", ["lesson_resource", "lesson_activity_resource"]]}
		return [
			{"name": "DB-LESSON-1", "status": "active"},
			{"name": "DB-LESSON-2", "status": "inactive"},
			{"name": "DB-LESSON-3", "status": "superseded"},
		]

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	frappe.get_all = fake_get_all
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.retire_legacy_lesson_binding_roles")
	module.execute()

	assert updates == [
		(
			"Drive Binding",
			"DB-LESSON-1",
			{
				"binding_role": "supporting_material",
				"is_primary": 0,
				"primary_key": None,
				"status": "superseded",
			},
			False,
		),
		(
			"Drive Binding",
			"DB-LESSON-2",
			{
				"binding_role": "supporting_material",
				"is_primary": 0,
				"primary_key": None,
			},
			False,
		),
		(
			"Drive Binding",
			"DB-LESSON-3",
			{
				"binding_role": "supporting_material",
				"is_primary": 0,
				"primary_key": None,
			},
			False,
		),
	]


def test_patch_returns_when_drive_binding_table_is_missing():
	_purge_modules("frappe", "ifitwala_drive.patches.retire_legacy_lesson_binding_roles")

	class FakeDB:
		def table_exists(self, doctype):
			return False

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	frappe.get_all = lambda *args, **kwargs: (_ for _ in ()).throw(
		AssertionError("get_all should not run when Drive Binding is unavailable")
	)
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.retire_legacy_lesson_binding_roles")
	module.execute()
