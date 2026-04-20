from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def test_patch_copies_legacy_session_secondary_subjects_once():
	_purge_modules("frappe", "ifitwala_drive.patches.migrate_legacy_upload_session_secondary_subjects")
	inserted_rows = []

	class FakeDoc:
		def __init__(self, data):
			self.data = data

		def insert(self, ignore_permissions=False):
			inserted_rows.append((self.data, ignore_permissions))
			return self

	class FakeDB:
		def table_exists(self, doctype):
			return doctype in {"File Classification Subject", "Drive Upload Session Subject"}

	def fake_get_all(doctype, filters=None, fields=None, limit=None):
		if doctype == "File Classification Subject":
			assert filters == {"parenttype": "Drive Upload Session"}
			return [
				{
					"parent": "DUS-0001",
					"parentfield": "secondary_subjects",
					"parenttype": "Drive Upload Session",
					"idx": 1,
					"subject_type": "Student",
					"subject_id": "STU-0001",
					"role": "co-owner",
				},
				{
					"parent": "DUS-0002",
					"parentfield": "secondary_subjects",
					"parenttype": "Drive Upload Session",
					"idx": 1,
					"subject_type": "Guardian",
					"subject_id": "GRD-0001",
					"role": "referenced",
				},
			]
		if doctype == "Drive Upload Session Subject":
			return [
				{
					"parent": "DUS-0002",
					"parentfield": "secondary_subjects",
					"parenttype": "Drive Upload Session",
					"idx": 1,
					"subject_type": "Guardian",
					"subject_id": "GRD-0001",
					"role": "referenced",
				}
			]
		raise AssertionError(f"Unexpected get_all call: {doctype}")

	frappe = types.ModuleType("frappe")
	frappe.db = FakeDB()
	frappe.get_all = fake_get_all
	frappe.get_doc = lambda data: FakeDoc(data)
	sys.modules["frappe"] = frappe

	module = importlib.import_module(
		"ifitwala_drive.patches.migrate_legacy_upload_session_secondary_subjects"
	)
	module.execute()

	assert inserted_rows == [
		(
			{
				"doctype": "Drive Upload Session Subject",
				"parent": "DUS-0001",
				"parentfield": "secondary_subjects",
				"parenttype": "Drive Upload Session",
				"idx": 1,
				"subject_type": "Student",
				"subject_id": "STU-0001",
				"role": "co-owner",
			},
			True,
		)
	]
