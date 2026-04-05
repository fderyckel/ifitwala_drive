from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import ClassVar


class FakeDoc:
	_insert_counters: ClassVar[dict[str, int]] = {}

	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def check_permission(self, permission_type=None):
		return None

	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def insert(self, ignore_permissions=False):
		doctype = getattr(self, "doctype", "DocType")
		prefix_map = {
			"Drive Folder": "DRF",
		}
		prefix = prefix_map.get(doctype, "DOC")
		next_value = self._insert_counters.get(prefix, 0) + 1
		self._insert_counters[prefix] = next_value
		if not getattr(self, "name", None):
			self.name = f"{prefix}-{next_value:04d}"
		return self


def _normalize_key_part(value):
	if isinstance(value, dict):
		return tuple(sorted((key, _normalize_key_part(item)) for key, item in value.items()))
	if isinstance(value, list):
		return tuple(_normalize_key_part(item) for item in value)
	if isinstance(value, tuple):
		return tuple(_normalize_key_part(item) for item in value)
	return value


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if (
			any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes)
			or module_name.startswith("ifitwala_drive.services.folders")
			or module_name.startswith("ifitwala_drive.services.integration.ifitwala_ed_")
			or module_name.startswith("ifitwala_ed.integrations.drive")
		):
			sys.modules.pop(module_name, None)
	FakeDoc._insert_counters = {}


def _ensure_ed_repo_on_path() -> None:
	ed_repo_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed"
	if ed_repo_root.exists():
		ed_repo_root_text = str(ed_repo_root)
		if ed_repo_root_text not in sys.path:
			sys.path.insert(0, ed_repo_root_text)


def _install_fake_frappe(*, exists_map=None, value_map=None, docs_map=None):
	exists_map = exists_map or {}
	value_map = value_map or {}
	docs_map = docs_map or {}

	class FakeDB:
		def exists(self, doctype, name=None):
			key = (doctype, _normalize_key_part(name))
			if key in exists_map:
				return exists_map[key]
			if isinstance(name, dict):
				return exists_map.get((doctype, _normalize_key_part(name)), False)
			return (doctype, name) in docs_map

		def get_value(self, doctype, name, fieldname=None, as_dict=False):
			key = (
				doctype,
				_normalize_key_part(name),
				_normalize_key_part(fieldname),
				as_dict,
			)
			if key in value_map:
				return value_map[key]
			key = (
				doctype,
				_normalize_key_part(name),
				_normalize_key_part(fieldname),
			)
			if key in value_map:
				return value_map[key]
			if isinstance(name, dict):
				return None
			doc = docs_map.get((doctype, name))
			if doc is None:
				return None
			if isinstance(fieldname, (list, tuple)):
				if as_dict:
					return {field: getattr(doc, field, None) for field in fieldname}
				return [getattr(doc, field, None) for field in fieldname]
			return getattr(doc, fieldname, None)

	def _throw(message, exc=None):
		raise RuntimeError(message)

	def _get_doc(doctype, name=None):
		if isinstance(doctype, dict):
			return FakeDoc(doctype)
		return docs_map[(doctype, name)]

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.db = FakeDB()
	frappe.get_doc = _get_doc
	frappe.session = types.SimpleNamespace(user="tester@example.com")
	frappe.generate_hash = lambda length=10: "x" * length
	frappe.scrub = lambda value: str(value or "").strip().lower().replace(" ", "_")
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None)
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn

	sys.modules["frappe"] = frappe


def _install_fake_sessions(recorder):
	module = types.ModuleType("ifitwala_drive.services.uploads.sessions")

	def create_upload_session_service(payload):
		recorder["payload"] = payload
		return {"upload_session_id": "DUS-0001", "status": "created"}

	module.create_upload_session_service = create_upload_session_service
	sys.modules["ifitwala_drive.services.uploads.sessions"] = module


def _load_module(module_name: str):
	_ensure_ed_repo_on_path()
	return importlib.import_module(module_name)


def test_upload_org_communication_attachment_uses_class_context_folder():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_org_communications",
		"ifitwala_drive.services.uploads.sessions",
	)
	org_communication = FakeDoc({"name": "COMM-0001", "organization": "ORG-0001", "school": "SCH-0001"})
	_install_fake_frappe(
		exists_map={
			("Org Communication", "COMM-0001"): True,
			("Course", "COURSE-0001"): True,
			("Student Group", "SG-0001"): True,
		},
		value_map={
			("Student Group", "SG-0001", ("course", "school"), True): {
				"course": "COURSE-0001",
				"school": "SCH-0001",
			},
		},
		docs_map={("Org Communication", "COMM-0001"): org_communication},
	)
	recorder = {}
	_install_fake_sessions(recorder)
	_ensure_ed_repo_on_path()
	importlib.import_module("ifitwala_ed")
	importlib.import_module("ifitwala_ed.integrations")
	importlib.import_module("ifitwala_ed.integrations.drive")
	delegate = types.ModuleType("ifitwala_ed.integrations.drive.org_communications")
	delegate.assert_org_communication_upload_access = (
		lambda org_communication_name, permission_type="write": org_communication
	)
	delegate.build_org_communication_upload_contract = lambda doc, row_name=None: {
		"owner_doctype": "Org Communication",
		"owner_name": doc.name,
		"attached_doctype": "Org Communication",
		"attached_name": doc.name,
		"organization": "ORG-0001",
		"school": "SCH-0001",
		"primary_subject_type": "Organization",
		"primary_subject_id": "ORG-0001",
		"data_class": "administrative",
		"purpose": "administrative",
		"retention_policy": "fixed_7y",
		"slot": "communication_attachment__row-001",
		"row_name": "row-001",
		"course": "COURSE-0001",
		"student_group": "SG-0001",
	}
	sys.modules["ifitwala_ed.integrations.drive.org_communications"] = delegate

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_org_communications")
	response = module.upload_org_communication_attachment_service(
		{
			"org_communication": "COMM-0001",
			"filename_original": "announcement.pdf",
			"mime_type_hint": "application/pdf",
			"expected_size_bytes": 4321,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert response["row_name"] == "row-001"
	assert recorder["payload"]["owner_doctype"] == "Org Communication"
	assert recorder["payload"]["attached_doctype"] == "Org Communication"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["school"] == "SCH-0001"
	assert recorder["payload"]["primary_subject_type"] == "Organization"
	assert recorder["payload"]["primary_subject_id"] == "ORG-0001"
	assert recorder["payload"]["slot"] == "communication_attachment__row-001"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")
