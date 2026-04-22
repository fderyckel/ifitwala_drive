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
		if (
			any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes)
			or module_name.startswith("ifitwala_drive.services.folders")
			or module_name == "ifitwala_drive.services.integration._ed_delegate"
			or module_name.startswith("ifitwala_drive.services.integration.ifitwala_ed_")
			or module_name == "ifitwala_ed"
			or module_name.startswith("ifitwala_ed.")
		):
			sys.modules.pop(module_name, None)
	FakeDoc._insert_counters = {}


def _ensure_ed_repo_on_path() -> None:
	ed_repo_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed"
	if ed_repo_root.exists():
		ed_repo_root_text = str(ed_repo_root)
		if ed_repo_root_text not in sys.path:
			sys.path.insert(0, ed_repo_root_text)
		return

	if any(
		module_name == "ifitwala_ed" or module_name.startswith("ifitwala_ed.") for module_name in sys.modules
	):
		return

	_install_fake_ifitwala_ed()


def _install_fake_ifitwala_ed():
	import frappe

	ed_package_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed" / "ifitwala_ed"
	integrations_package_root = ed_package_root / "integrations"
	drive_integrations_package_root = integrations_package_root / "drive"

	def _build_task_resource_upload_contract(task_doc, *, row_name: str | None = None) -> dict[str, object]:
		course = getattr(task_doc, "default_course", None)
		school = frappe.db.get_value("Course", course, "school")
		organization = frappe.db.get_value("School", school, "organization")
		resolved_row_name = str(row_name or "row-001")
		return {
			"owner_doctype": "Task",
			"owner_name": task_doc.name,
			"attached_doctype": "Task",
			"attached_name": task_doc.name,
			"organization": organization,
			"school": school,
			"primary_subject_type": "Organization",
			"primary_subject_id": organization,
			"data_class": "academic",
			"purpose": "learning_resource",
			"retention_policy": "until_program_end_plus_1y",
			"slot": f"supporting_material__{resolved_row_name}",
			"row_name": resolved_row_name,
			"course": course,
		}

	def _build_supporting_material_upload_contract(material_doc) -> dict[str, object]:
		course = getattr(material_doc, "course", None)
		school = frappe.db.get_value("Course", course, "school")
		organization = frappe.db.get_value("School", school, "organization")
		return {
			"owner_doctype": "Supporting Material",
			"owner_name": material_doc.name,
			"attached_doctype": "Supporting Material",
			"attached_name": material_doc.name,
			"organization": organization,
			"school": school,
			"primary_subject_type": "Organization",
			"primary_subject_id": organization,
			"data_class": "academic",
			"purpose": "learning_resource",
			"retention_policy": "until_program_end_plus_1y",
			"slot": "material_file",
			"course": course,
		}

	def _run_task_post_finalize(upload_session_doc, created_file) -> dict[str, object]:
		task_doc = frappe.get_doc("Task", upload_session_doc.owner_name)
		row_name = str(getattr(upload_session_doc, "intended_slot", "") or "").split("__", 1)[-1]
		task_doc.append(
			"attachments",
			{
				"name": row_name,
				"file": created_file.file_url,
				"file_name": created_file.file_name,
				"file_size": created_file.file_size,
				"public": 0,
				"section_break_sbex": created_file.file_name,
			},
		)
		task_doc.save(ignore_permissions=True)
		return {"row_name": row_name}

	def _resolve_upload_session_context(
		workflow_id: str, workflow_payload: dict[str, object]
	) -> dict[str, object]:
		if workflow_id == "task.resource":
			context = _build_task_resource_upload_contract(
				frappe.get_doc("Task", workflow_payload.get("task")),
				row_name=workflow_payload.get("row_name"),
			)
			return {
				**context,
				"workflow_id": workflow_id,
				"contract_version": "1",
				"is_private": 1,
			}
		if workflow_id == "supporting_material.file":
			context = _build_supporting_material_upload_contract(
				frappe.get_doc("Supporting Material", workflow_payload.get("material"))
			)
			return {
				**context,
				"workflow_id": workflow_id,
				"contract_version": "1",
				"is_private": 1,
			}
		raise RuntimeError(f"unexpected workflow_id: {workflow_id}")

	tasks = types.ModuleType("ifitwala_ed.integrations.drive.tasks")
	tasks.build_task_resource_upload_contract = _build_task_resource_upload_contract
	tasks.assert_task_resource_upload_access = lambda task, permission_type="write": frappe.get_doc(
		"Task", task
	)
	tasks.run_task_post_finalize = _run_task_post_finalize

	materials = types.ModuleType("ifitwala_ed.integrations.drive.materials")
	materials.build_supporting_material_upload_contract = _build_supporting_material_upload_contract
	materials.assert_supporting_material_upload_access = lambda material, permission_type="write": (
		frappe.get_doc("Supporting Material", material)
	)

	bridge = types.ModuleType("ifitwala_ed.integrations.drive.bridge")
	bridge.resolve_upload_session_context = _resolve_upload_session_context

	integrations = types.ModuleType("ifitwala_ed.integrations")
	integrations.__path__ = [str(integrations_package_root)]
	drive_integrations = types.ModuleType("ifitwala_ed.integrations.drive")
	drive_integrations.__path__ = [str(drive_integrations_package_root)]
	drive_integrations.bridge = bridge
	drive_integrations.tasks = tasks
	drive_integrations.materials = materials
	integrations.drive = drive_integrations

	ifitwala_ed = types.ModuleType("ifitwala_ed")
	ifitwala_ed.__path__ = [str(ed_package_root)]
	ifitwala_ed.integrations = integrations

	sys.modules["ifitwala_ed"] = ifitwala_ed
	sys.modules["ifitwala_ed.integrations"] = integrations
	sys.modules["ifitwala_ed.integrations.drive"] = drive_integrations
	sys.modules["ifitwala_ed.integrations.drive.bridge"] = bridge
	sys.modules["ifitwala_ed.integrations.drive.tasks"] = tasks
	sys.modules["ifitwala_ed.integrations.drive.materials"] = materials


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
	frappe_utils = types.ModuleType("frappe.utils")
	frappe_utils.now_datetime = lambda: None
	sys.modules["frappe.utils"] = frappe_utils


def _install_fake_sessions(recorder):
	module = types.ModuleType("ifitwala_drive.services.uploads.sessions")

	def create_upload_session_service(payload):
		recorder["payload"] = payload
		return {
			"upload_session_id": "DUS-0001",
			"status": "created",
			"workflow_result": payload.get("workflow_result") or {},
		}

	module.create_upload_session_service = create_upload_session_service
	sys.modules["ifitwala_drive.services.uploads.sessions"] = module


def _load_module(module_name: str):
	_ensure_ed_repo_on_path()
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
	assert response["workflow_result"]["row_name"]
	assert recorder["payload"]["owner_doctype"] == "Task"
	assert recorder["payload"]["attached_doctype"] == "Task"
	assert recorder["payload"]["attached_name"] == "TASK-0001"
	assert recorder["payload"]["primary_subject_type"] == "Organization"
	assert recorder["payload"]["primary_subject_id"] == "ORG-0001"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["school"] == "SCH-0001"
	assert recorder["payload"]["slot"].startswith("supporting_material__")
	assert recorder["payload"]["purpose"] == "learning_resource"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


def test_upload_supporting_material_uses_material_contract_and_course_folder():
	_purge_modules(
		"frappe",
		"ifitwala_ed.integrations.drive.materials",
		"ifitwala_drive.services.integration.ifitwala_ed_materials",
		"ifitwala_drive.services.uploads.sessions",
	)
	material = FakeDoc({"name": "MAT-0001", "course": "COURSE-0001"})
	_install_fake_frappe(
		exists_map={
			("Supporting Material", "MAT-0001"): True,
		},
		value_map={
			("Course", "COURSE-0001", "school"): "SCH-0001",
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={("Supporting Material", "MAT-0001"): material},
	)
	recorder = {}
	_install_fake_sessions(recorder)
	_ensure_ed_repo_on_path()
	importlib.import_module("ifitwala_ed")
	importlib.import_module("ifitwala_ed.integrations")
	importlib.import_module("ifitwala_ed.integrations.drive")
	materials_delegate = types.ModuleType("ifitwala_ed.integrations.drive.materials")
	materials_delegate.assert_supporting_material_upload_access = (
		lambda material_name, permission_type="write": material
	)
	materials_delegate.build_supporting_material_upload_contract = lambda material_doc: {
		"owner_doctype": "Supporting Material",
		"owner_name": material_doc.name,
		"attached_doctype": "Supporting Material",
		"attached_name": material_doc.name,
		"organization": "ORG-0001",
		"school": "SCH-0001",
		"primary_subject_type": "Organization",
		"primary_subject_id": "ORG-0001",
		"data_class": "academic",
		"purpose": "learning_resource",
		"retention_policy": "until_program_end_plus_1y",
		"slot": "material_file",
		"course": material_doc.course,
	}
	sys.modules["ifitwala_ed.integrations.drive.materials"] = materials_delegate
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_materials")

	response = module.upload_supporting_material_service(
		{
			"material": "MAT-0001",
			"filename_original": "worksheet.pdf",
			"mime_type_hint": "application/pdf",
			"expected_size_bytes": 1234,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert recorder["payload"]["owner_doctype"] == "Supporting Material"
	assert recorder["payload"]["owner_name"] == "MAT-0001"
	assert recorder["payload"]["attached_doctype"] == "Supporting Material"
	assert recorder["payload"]["attached_name"] == "MAT-0001"
	assert recorder["payload"]["primary_subject_type"] == "Organization"
	assert recorder["payload"]["primary_subject_id"] == "ORG-0001"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["school"] == "SCH-0001"
	assert recorder["payload"]["slot"] == "material_file"
	assert recorder["payload"]["purpose"] == "learning_resource"
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


def test_material_grant_services_use_authorized_delegate_context(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_materials",
	)
	_install_fake_frappe(
		exists_map={("Drive File", "DF-0001"): True},
		docs_map={
			("Drive File", "DF-0001"): FakeDoc(
				{
					"name": "DF-0001",
					"owner_doctype": "Supporting Material",
					"owner_name": "MAT-0001",
					"status": "active",
					"preview_status": "ready",
				}
			),
		},
	)
	_ensure_ed_repo_on_path()
	importlib.import_module("ifitwala_ed")
	importlib.import_module("ifitwala_ed.integrations")
	importlib.import_module("ifitwala_ed.integrations.drive")
	delegate_calls = []
	delegate = types.ModuleType("ifitwala_ed.integrations.drive.materials")
	delegate.assert_supporting_material_read_access = lambda material, placement=None, drive_file_id=None: (
		delegate_calls.append((material, placement, drive_file_id))
		or {
			"material": "MAT-0001",
			"placement": placement,
			"drive_file_id": "DF-0001",
			"file_id": "FILE-0001",
		}
	)
	sys.modules["ifitwala_ed.integrations.drive.materials"] = delegate

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_materials")
	preview_docs = []
	download_docs = []
	grant_calls = []

	monkeypatch.setattr(module, "_assert_can_issue_preview", lambda doc: preview_docs.append(doc.name))
	monkeypatch.setattr(module, "_assert_can_issue_download", lambda doc: download_docs.append(doc.name))

	def _fake_issue_grant(*, doc, grant_kind, payload=None):
		grant_calls.append({"doc": doc.name, "grant_kind": grant_kind, "payload": payload})
		return {"url": f"https://{grant_kind}.example.com/{doc.name}"}

	monkeypatch.setattr(module, "_issue_grant", _fake_issue_grant)

	preview_response = module.issue_supporting_material_preview_grant_service(
		{
			"material": "MAT-0001",
			"placement": "MAT-PLC-1",
			"derivative_role": "thumb",
		}
	)
	download_response = module.issue_supporting_material_download_grant_service(
		{
			"material": "MAT-0001",
			"placement": "MAT-PLC-1",
		}
	)

	assert delegate_calls == [
		("MAT-0001", "MAT-PLC-1", None),
		("MAT-0001", "MAT-PLC-1", None),
	]
	assert preview_docs == ["DF-0001"]
	assert download_docs == ["DF-0001"]
	assert preview_response == {"url": "https://preview.example.com/DF-0001"}
	assert download_response == {"url": "https://download.example.com/DF-0001"}
	assert grant_calls == [
		{
			"doc": "DF-0001",
			"grant_kind": "preview",
			"payload": {
				"material": "MAT-0001",
				"placement": "MAT-PLC-1",
				"derivative_role": "thumb",
			},
		},
		{
			"doc": "DF-0001",
			"grant_kind": "download",
			"payload": None,
		},
	]
