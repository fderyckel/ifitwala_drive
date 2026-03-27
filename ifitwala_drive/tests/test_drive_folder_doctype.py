from __future__ import annotations

import hashlib
import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe() -> None:
	class FakeDocument:
		def get(self, key, default=None):
			return getattr(self, key, default)

		def __getattr__(self, _name):
			return None

	def _throw(message):
		raise RuntimeError(message)

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.session = types.SimpleNamespace(user="tester@example.com")

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")
	document.Document = FakeDocument

	sys.modules["frappe"] = frappe
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def _build_folder(module, **kwargs):
	doc = module.DriveFolder()
	for key, value in kwargs.items():
		setattr(doc, key, value)
	return doc


def test_drive_folder_autoname_uses_scoped_identifier_instead_of_title():
	_purge_modules("frappe", "ifitwala_drive.ifitwala_drive.doctype.drive_folder.drive_folder")
	_install_fake_frappe()
	module = _load_module("ifitwala_drive.ifitwala_drive.doctype.drive_folder.drive_folder")

	student_profile = _build_folder(
		module,
		title="Profile",
		parent_drive_folder="DRF-STUDENT-ROOT",
		owner_doctype="Student",
		owner_name="STU-0001",
		organization="ORG-0001",
		school="SCH-0001",
		folder_kind="student_workspace",
	)
	employee_profile = _build_folder(
		module,
		title="Profile",
		parent_drive_folder="DRF-EMPLOYEE-ROOT",
		owner_doctype="Employee",
		owner_name="EMP-0001",
		organization="ORG-0001",
		school="SCH-0001",
		folder_kind="staff_documents",
	)

	student_profile.autoname()
	employee_profile.autoname()

	assert student_profile.system_key == (
		"ORG-0001|SCH-0001|Student|STU-0001|DRF-STUDENT-ROOT|student_workspace|profile"
	)
	assert employee_profile.system_key == (
		"ORG-0001|SCH-0001|Employee|EMP-0001|DRF-EMPLOYEE-ROOT|staff_documents|profile"
	)
	assert student_profile.name == (
		f"DRF-{hashlib.sha1(student_profile.system_key.encode('utf-8')).hexdigest()[:16].upper()}"
	)
	assert employee_profile.name == (
		f"DRF-{hashlib.sha1(employee_profile.system_key.encode('utf-8')).hexdigest()[:16].upper()}"
	)
	assert student_profile.name != employee_profile.name
	assert student_profile.name != "Profile"
	assert employee_profile.name != "Profile"


def test_drive_folder_accepts_guardian_workspace_folder_kind():
	_purge_modules("frappe", "ifitwala_drive.ifitwala_drive.doctype.drive_folder.drive_folder")
	_install_fake_frappe()
	module = _load_module("ifitwala_drive.ifitwala_drive.doctype.drive_folder.drive_folder")

	guardian_profile = _build_folder(
		module,
		title="Guardian Image",
		parent_drive_folder="DRF-GUARDIAN-ROOT",
		owner_doctype="Guardian",
		owner_name="GRD-0001",
		organization="ORG-0001",
		school=None,
		folder_kind="guardian_workspace",
	)

	guardian_profile._validate_folder_kind()
