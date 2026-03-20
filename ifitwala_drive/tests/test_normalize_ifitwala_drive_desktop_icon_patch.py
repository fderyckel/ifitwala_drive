from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeDoc:
	def __init__(self, **values):
		for key, value in values.items():
			setattr(self, key, value)
		self.saved = False
		self.saved_ignore_permissions = None

	def save(self, ignore_permissions=False):
		self.saved = True
		self.saved_ignore_permissions = ignore_permissions


def test_patch_normalizes_ifitwala_drive_desktop_icon_to_workspace_sidebar():
	_purge_modules("frappe", "ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	delete_key_calls = []
	icon_doc = FakeDoc(
		name="Ifitwala Drive",
		app="ifitwala_drive",
		link_type="Workspace",
		link_to="Ifitwala Drive",
		icon_type="Link",
	)

	class FakeDB:
		def exists(self, doctype, name=None):
			return doctype == "Desktop Icon" and name == "Ifitwala Drive"

	class FakeCache:
		def delete_key(self, key):
			delete_key_calls.append(key)

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	frappe.get_doc = lambda doctype, name=None: icon_doc
	frappe.cache = lambda: FakeCache()
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	module.execute()

	assert icon_doc.link_type == "Workspace Sidebar"
	assert icon_doc.link_to == "Ifitwala Drive"
	assert icon_doc.icon_type == "Link"
	assert icon_doc.saved is True
	assert icon_doc.saved_ignore_permissions is True
	assert delete_key_calls == ["desktop_icons", "bootinfo"]


def test_patch_skips_non_ifitwala_drive_icon():
	_purge_modules("frappe", "ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	icon_doc = FakeDoc(
		name="Ifitwala Drive",
		app="another_app",
		link_type="Workspace",
		link_to="Ifitwala Drive",
		icon_type="Link",
	)

	class FakeDB:
		def exists(self, doctype, name=None):
			return doctype == "Desktop Icon" and name == "Ifitwala Drive"

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	frappe.get_doc = lambda doctype, name=None: icon_doc
	sys.modules["frappe"] = frappe

	module = importlib.import_module("ifitwala_drive.patches.normalize_ifitwala_drive_desktop_icon")
	module.execute()

	assert icon_doc.link_type == "Workspace"
	assert icon_doc.saved is False
