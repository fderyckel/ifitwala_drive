from __future__ import annotations

import importlib
import sys
import types
from typing import ClassVar


class FakeDoc:
	_insert_counters: ClassVar[dict[str, int]] = {}

	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.saved = 0

	def check_permission(self, permission_type=None):
		return None

	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def append(self, fieldname, row):
		rows = getattr(self, fieldname, None)
		if rows is None:
			rows = []
			setattr(self, fieldname, rows)
		child = types.SimpleNamespace(**row)
		rows.append(child)
		return child

	def save(self, ignore_permissions=False):
		self.saved += 1
		return self

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
		if any(
			module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes
		) or module_name.startswith("ifitwala_drive.services.folders"):
			sys.modules.pop(module_name, None)
	FakeDoc._insert_counters = {}


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
	return importlib.import_module(module_name)


def test_upload_task_resource_uses_task_contract_and_course_folder():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.sessions",
	)
	task = FakeDoc({"name": "TASK-0001", "default_course": "COURSE-0001", "attachments": []})
	_install_fake_frappe(
		exists_map={
			("Task", "TASK-0001"): True,
		},
		value_map={
			("Course", "COURSE-0001", "school"): "SCH-0001",
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={("Task", "TASK-0001"): task},
	)
	recorder = {}
	_install_fake_sessions(recorder)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_tasks")

	response = module.upload_task_resource_service(
		{
			"task": "TASK-0001",
			"filename_original": "worksheet.pdf",
			"mime_type_hint": "application/pdf",
			"expected_size_bytes": 1234,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert response["row_name"]
	assert recorder["payload"]["owner_doctype"] == "Task"
	assert recorder["payload"]["attached_doctype"] == "Task"
	assert recorder["payload"]["attached_name"] == "TASK-0001"
	assert recorder["payload"]["primary_subject_type"] == "Organization"
	assert recorder["payload"]["primary_subject_id"] == "ORG-0001"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["school"] == "SCH-0001"
	assert recorder["payload"]["slot"].startswith("supporting_material__")
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


def test_run_task_post_finalize_appends_compatibility_attachment_row():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
	)
	task = FakeDoc({"name": "TASK-0001", "default_course": "COURSE-0001", "attachments": []})
	_install_fake_frappe(
		exists_map={("Task", "TASK-0001"): True},
		docs_map={("Task", "TASK-0001"): task},
	)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_tasks")

	response = module.run_task_post_finalize(
		types.SimpleNamespace(
			owner_doctype="Task",
			owner_name="TASK-0001",
			intended_slot="supporting_material__row-001",
		),
		types.SimpleNamespace(
			name="FILE-0001",
			file_url="/private/files/worksheet.pdf",
			file_name="worksheet.pdf",
			file_size=1024,
		),
	)

	assert response["row_name"] == "row-001"
	assert len(task.attachments) == 1
	row = task.attachments[0]
	assert row.name == "row-001"
	assert row.file == "/private/files/worksheet.pdf"
	assert row.file_name == "worksheet.pdf"
	assert row.file_size == 1024
	assert row.public == 0
	assert row.section_break_sbex == "worksheet.pdf"
	assert task.saved == 1
