from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def test_patch_repairs_stale_drive_doctype_modules():
	_purge_modules("frappe", "ifitwala_drive.patches.repair_drive_doctype_modules")
	set_value_calls = []
	existing_doctypes = {
		"Drive Upload Session": "Core",
		"Drive File": "Ifitwala Drive",
		"Drive File Version": "Desk",
		"Drive Folder": "Ifitwala Drive",
		"Drive Binding": "Core",
	}

	class FakeDB:
		def exists(self, doctype, name=None):
			return doctype == "DocType" and name in existing_doctypes

		def get_value(self, doctype, name, fieldname):
			assert doctype == "DocType"
			assert fieldname == "module"
			return existing_doctypes[name]

		def set_value(self, doctype, name, fieldname, value, update_modified=False):
			set_value_calls.append((doctype, name, fieldname, value, update_modified))

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.repair_drive_doctype_modules")
	module.execute()

	assert set_value_calls == [
		("DocType", "Drive Upload Session", "module", "Ifitwala Drive", False),
		("DocType", "Drive File Version", "module", "Ifitwala Drive", False),
		("DocType", "Drive Binding", "module", "Ifitwala Drive", False),
	]
