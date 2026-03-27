from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def test_patch_normalizes_ifitwala_drive_desktop_icon_to_workspace_sidebar():
	_purge_modules("frappe", "ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	delete_key_calls = []
	set_value_calls = []

	class FakeDB:
		def __init__(self):
			self.icon = {
				"app": "ifitwala_drive",
				"link_type": "Workspace",
				"link_to": "Ifitwala Drive",
				"icon_type": "Link",
			}

		def exists(self, doctype, name=None):
			return doctype == "Desktop Icon" and name == "Ifitwala Drive"

		def get_value(self, doctype, name, fields, as_dict=False):
			assert doctype == "Desktop Icon"
			assert name == "Ifitwala Drive"
			assert fields == ["app", "link_type", "link_to", "icon_type"]
			assert as_dict is True
			return dict(self.icon)

		def set_value(self, doctype, name, values, update_modified=False):
			set_value_calls.append((doctype, name, values, update_modified))
			self.icon.update(values)

	class FakeCache:
		def delete_key(self, key):
			delete_key_calls.append(key)

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	frappe.cache = lambda: FakeCache()
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	module.execute()

	assert frappe.db.icon["link_type"] == "Workspace Sidebar"
	assert frappe.db.icon["link_to"] == "Ifitwala Drive"
	assert frappe.db.icon["icon_type"] == "Link"
	assert set_value_calls == [
		(
			"Desktop Icon",
			"Ifitwala Drive",
			{"link_type": "Workspace Sidebar"},
			False,
		)
	]
	assert delete_key_calls == ["desktop_icons", "bootinfo"]


def test_patch_skips_non_ifitwala_drive_icon():
	_purge_modules("frappe", "ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	set_value_calls = []

	class FakeDB:
		def __init__(self):
			self.icon = {
				"app": "another_app",
				"link_type": "Workspace",
				"link_to": "Ifitwala Drive",
				"icon_type": "Link",
			}

		def exists(self, doctype, name=None):
			return doctype == "Desktop Icon" and name == "Ifitwala Drive"

		def get_value(self, doctype, name, fields, as_dict=False):
			assert doctype == "Desktop Icon"
			assert name == "Ifitwala Drive"
			assert fields == ["app", "link_type", "link_to", "icon_type"]
			assert as_dict is True
			return dict(self.icon)

		def set_value(self, doctype, name, values, update_modified=False):
			set_value_calls.append((doctype, name, values, update_modified))

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	module.execute()

	assert frappe.db.icon["link_type"] == "Workspace"
	assert set_value_calls == []
