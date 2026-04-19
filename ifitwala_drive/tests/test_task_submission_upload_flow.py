# ifitwala_drive/tests/test_task_submission_upload_flow.py

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from typing import ClassVar


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if (
			any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes)
			or module_name.startswith("ifitwala_drive.services.folders")
			or module_name.startswith("ifitwala_drive.services.integration.ifitwala_ed_")
			or module_name.startswith("ifitwala_ed.integrations.drive")
			or module_name.startswith("ifitwala_ed.utilities.file_")
		):
			sys.modules.pop(module_name, None)
	FakeDoc._insert_counters = {}
	FakeDoc._docs_map = {}
	FakeDoc._duplicate_insert_once = {}
	FakeDoc._duplicate_insert_materialized_docs = {}


def _ensure_ed_repo_on_path() -> None:
	ed_repo_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed"
	if ed_repo_root.exists():
		ed_repo_root_text = str(ed_repo_root)
		if ed_repo_root_text not in sys.path:
			sys.path.insert(0, ed_repo_root_text)


class FakeDoc:
	_insert_counters: ClassVar[dict[str, int]] = {}
	_docs_map: ClassVar[dict[tuple[str, str], "FakeDoc"]] = {}
	_duplicate_insert_once: ClassVar[dict[str, int]] = {}
	_duplicate_insert_materialized_docs: ClassVar[dict[str, object]] = {}

	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.saved = 0
		self.inserted = 0

	def get(self, key, default=None):
		return getattr(self, key, default)

	def save(self, ignore_permissions=False):
		self.saved += 1
		return self

	def insert(self, ignore_permissions=False):
		doctype = getattr(self, "doctype", "")
		remaining_duplicates = self._duplicate_insert_once.get(doctype, 0)
		if remaining_duplicates:
			self._duplicate_insert_once[doctype] = remaining_duplicates - 1
			materialized_docs = self._duplicate_insert_materialized_docs.get(doctype, [])
			if not isinstance(materialized_docs, list):
				materialized_docs = [materialized_docs]
			for doc_data in materialized_docs:
				doc = doc_data if isinstance(doc_data, FakeDoc) else FakeDoc(doc_data)
				self._docs_map[(doc.doctype, doc.name)] = doc
			raise DuplicateEntryError(f"Duplicate entry for {doctype}")

		if not getattr(self, "name", None):
			prefix_map = {
				"Drive Upload Session": "DUS",
				"Drive File": "DF",
				"Drive File Version": "DFV",
				"Drive File Derivative": "DFD",
				"Drive Binding": "DB",
				"Drive Processing Job": "DPJ",
				"Drive Folder": "DRF",
				"File": "FILE",
				"File Classification": "FC",
			}
			prefix = prefix_map.get(doctype, "DOC")
			next_value = self._insert_counters.get(prefix, 0) + 1
			self._insert_counters[prefix] = next_value
			self.name = f"{prefix}-{next_value:04d}"
		self.inserted += 1
		self._docs_map[(doctype, self.name)] = self
		return self


class DuplicateEntryError(Exception):
	pass


def _install_fake_frappe(
	*,
	exists_map: dict[tuple[str, object], object] | None = None,
	value_map: dict[tuple[str, object, object], object] | None = None,
	docs_map: dict[tuple[str, str], FakeDoc] | None = None,
	now: datetime | None = None,
	forbid_file_doc: bool = False,
	duplicate_insert_once: dict[str, int] | None = None,
	duplicate_insert_materialized_docs: dict[str, object] | None = None,
):
	exists_map = exists_map or {}
	value_map = value_map or {}
	docs_map = docs_map or {}
	duplicate_insert_once = duplicate_insert_once or {}
	duplicate_insert_materialized_docs = duplicate_insert_materialized_docs or {}
	FakeDoc._docs_map = docs_map
	FakeDoc._duplicate_insert_once = dict(duplicate_insert_once)
	FakeDoc._duplicate_insert_materialized_docs = dict(duplicate_insert_materialized_docs)
	now = now or datetime(2026, 3, 17, 9, 0, 0)
	file_doc_requests: list[dict] = []

	class FakeDB:
		def exists(self, doctype, name=None):
			if isinstance(name, dict):
				key = (doctype, tuple(sorted(name.items())))
				if key in exists_map:
					return exists_map[key]
				for candidate_doctype, candidate_name in docs_map:
					if candidate_doctype != doctype:
						continue
					doc = docs_map[(candidate_doctype, candidate_name)]
					if all(getattr(doc, fieldname, None) == value for fieldname, value in name.items()):
						return candidate_name
				return False

			key = (doctype, name)
			if key in exists_map:
				return exists_map[key]

			if isinstance(name, str):
				return (doctype, name) in docs_map

			return False

		def get_value(self, doctype, name, fieldname, as_dict=False):
			if isinstance(name, dict):
				key = (doctype, tuple(sorted(name.items())), fieldname)
				if key in value_map:
					return value_map[key]
				for candidate_doctype, candidate_name in docs_map:
					if candidate_doctype != doctype:
						continue
					doc = docs_map[(candidate_doctype, candidate_name)]
					if all(getattr(doc, filter_field, None) == value for filter_field, value in name.items()):
						if fieldname == "name":
							return candidate_name
						if isinstance(fieldname, (list, tuple)):
							if as_dict:
								return {field: getattr(doc, field, None) for field in fieldname}
							return [getattr(doc, field, None) for field in fieldname]
						return getattr(doc, fieldname, None)
				return None

			key = (doctype, name, fieldname)
			if key in value_map:
				return value_map[key]

			doc = docs_map.get((doctype, name))
			if doc is None:
				return None

			if isinstance(fieldname, (list, tuple)):
				if as_dict:
					return {field: getattr(doc, field, None) for field in fieldname}
				return [getattr(doc, field, None) for field in fieldname]

			return getattr(doc, fieldname, None)

		def set_value(self, doctype, name, fieldname, value=None, update_modified=True):
			doc = docs_map[(doctype, name)]
			if isinstance(fieldname, dict):
				for key, field_value in fieldname.items():
					setattr(doc, key, field_value)
			else:
				setattr(doc, fieldname, value)
			return doc

	def _throw(message):
		raise RuntimeError(message)

	def _identity(message):
		return message

	def _get_doc(arg1, arg2=None):
		if isinstance(arg1, dict):
			if arg1.get("doctype") == "File":
				file_doc_requests.append(arg1)
				if forbid_file_doc:
					raise AssertionError("Direct File.get_doc construction is forbidden in this flow.")
			return FakeDoc(arg1)

		return docs_map[(arg1, arg2)]

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = _identity
	frappe.db = FakeDB()
	frappe.session = types.SimpleNamespace(user="student@example.com")
	frappe.local = types.SimpleNamespace(request_ip="127.0.0.1")
	frappe.generate_hash = lambda length=24: "x" * length
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.conf = {}
	frappe.get_doc = _get_doc
	frappe.get_cached_doc = lambda doctype, name: docs_map[(doctype, name)]
	frappe.get_all = lambda doctype, fields=None, filters=None, pluck=None: [
		candidate_name
		if pluck == "name"
		else (
			getattr(doc, pluck, None)
			if pluck
			else {field: getattr(doc, field, None) for field in (fields or [])}
		)
		for (candidate_doctype, candidate_name), doc in docs_map.items()
		if candidate_doctype == doctype
		and (
			not filters or all(getattr(doc, fieldname, None) == value for fieldname, value in filters.items())
		)
	]
	frappe.DuplicateEntryError = DuplicateEntryError
	frappe.log_error = lambda *args, **kwargs: None
	frappe.get_traceback = lambda: "traceback"
	frappe.as_json = lambda value, indent=None: str(value)
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
	frappe.get_site_path = lambda *parts: "/tmp/" + "/".join(parts)
	frappe.form_dict = {}
	frappe.request = None

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: now
	utils.get_datetime = lambda value: (
		value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
	)
	utils.add_to_date = lambda value, hours=0, as_datetime=False: value + timedelta(hours=hours)

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")
	document.Document = FakeDoc

	frappe.utils = utils

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document

	return file_doc_requests


def _install_fake_ifitwala_ed(*, dispatcher_recorder: dict | None = None, install_dispatcher: bool = True):
	import frappe

	ed_package_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed" / "ifitwala_ed"
	utilities_package_root = ed_package_root / "utilities"
	integrations_package_root = ed_package_root / "integrations"
	drive_integrations_package_root = integrations_package_root / "drive"

	dispatcher = None
	if install_dispatcher:
		dispatcher = types.ModuleType("ifitwala_ed.utilities.file_dispatcher")

		def create_and_classify_file(**kwargs):
			if dispatcher_recorder is not None:
				dispatcher_recorder["call"] = kwargs
			return types.SimpleNamespace(name="FILE-0001")

		dispatcher.create_and_classify_file = create_and_classify_file

	file_management = types.ModuleType("ifitwala_ed.utilities.file_management")
	file_management.get_settings = lambda: object()
	file_management.build_task_submission_context = lambda **kwargs: {
		"student": kwargs["student"],
		"task_name": kwargs["task_name"],
		"routing": "task_submission",
	}

	def _build_task_submission_upload_contract(task_submission_doc) -> dict[str, object]:
		school = getattr(task_submission_doc, "school", None)
		student = getattr(task_submission_doc, "student", None)
		organization = frappe.db.get_value("School", school, "organization")
		return {
			"owner_doctype": "Task Submission",
			"owner_name": task_submission_doc.name,
			"attached_doctype": "Task Submission",
			"attached_name": task_submission_doc.name,
			"organization": organization,
			"school": school,
			"primary_subject_type": "Student",
			"primary_subject_id": student,
			"data_class": "assessment",
			"purpose": "assessment_submission",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": "submission",
		}

	def _reconcile_upload_session_payload(payload: dict[str, object]) -> dict[str, object]:
		if payload.get("owner_doctype") != "Task Submission":
			return payload
		task_submission_doc = frappe.get_doc("Task Submission", payload["owner_name"])
		authoritative = _build_task_submission_upload_contract(task_submission_doc)
		for fieldname, authoritative_value in authoritative.items():
			provided = payload.get(fieldname)
			if provided not in (None, "", authoritative_value):
				frappe.throw(
					"Task Submission upload field '{field_name}' does not match the authoritative owner context.".format(
						field_name=fieldname
					)
				)
		return {**payload, **authoritative}

	def _resolve_finalize_contract(upload_session_doc):
		if getattr(upload_session_doc, "owner_doctype", None) != "Task Submission":
			return {
				"workflow": None,
				"authoritative_context": None,
				"attached_field_override": None,
				"context_override": None,
				"binding_role": None,
			}
		task_submission_doc = frappe.get_doc("Task Submission", upload_session_doc.owner_name)
		authoritative = _build_task_submission_upload_contract(task_submission_doc)
		field_map = {
			"owner_doctype": "owner_doctype",
			"owner_name": "owner_name",
			"attached_doctype": "attached_doctype",
			"attached_name": "attached_name",
			"organization": "organization",
			"school": "school",
			"intended_primary_subject_type": "primary_subject_type",
			"intended_primary_subject_id": "primary_subject_id",
			"intended_data_class": "data_class",
			"intended_purpose": "purpose",
			"intended_retention_policy": "retention_policy",
			"intended_slot": "slot",
		}
		for session_field, authoritative_field in field_map.items():
			if getattr(upload_session_doc, session_field, None) != authoritative[authoritative_field]:
				frappe.throw(
					"Upload session no longer matches the authoritative Task Submission context for field '{field_name}'.".format(
						field_name=session_field
					)
				)
		return {
			"workflow": "task_submission",
			"authoritative_context": authoritative,
			"attached_field_override": None,
			"context_override": file_management.build_task_submission_context(
				student=authoritative["primary_subject_id"],
				task_name=getattr(task_submission_doc, "task", None) or task_submission_doc.name,
				settings=file_management.get_settings(),
			),
			"binding_role": None,
		}

	def _run_post_finalize(upload_session_doc, created_file):
		return {}

	file_classification_contract = types.ModuleType("ifitwala_ed.utilities.file_classification_contract")
	file_classification_contract.LEARNING_RESOURCE_PURPOSE = "learning_resource"

	utilities = types.ModuleType("ifitwala_ed.utilities")
	utilities.__path__ = [str(utilities_package_root)]
	utilities.file_management = file_management
	utilities.file_classification_contract = file_classification_contract
	if dispatcher is not None:
		utilities.file_dispatcher = dispatcher

	integrations = types.ModuleType("ifitwala_ed.integrations")
	integrations.__path__ = [str(integrations_package_root)]
	drive_integrations = types.ModuleType("ifitwala_ed.integrations.drive")
	drive_integrations.__path__ = [str(drive_integrations_package_root)]
	bridge = types.ModuleType("ifitwala_ed.integrations.drive.bridge")
	bridge.reconcile_upload_session_payload = _reconcile_upload_session_payload
	bridge.resolve_finalize_contract = _resolve_finalize_contract
	bridge.run_post_finalize = _run_post_finalize

	ifitwala_ed = types.ModuleType("ifitwala_ed")
	ifitwala_ed.__path__ = [str(ed_package_root)]
	ifitwala_ed.utilities = utilities
	ifitwala_ed.integrations = integrations
	integrations.drive = drive_integrations
	drive_integrations.bridge = bridge

	sys.modules["ifitwala_ed"] = ifitwala_ed
	sys.modules["ifitwala_ed.utilities"] = utilities
	sys.modules["ifitwala_ed.utilities.file_management"] = file_management
	sys.modules["ifitwala_ed.utilities.file_classification_contract"] = file_classification_contract
	sys.modules["ifitwala_ed.integrations"] = integrations
	sys.modules["ifitwala_ed.integrations.drive"] = drive_integrations
	sys.modules["ifitwala_ed.integrations.drive.bridge"] = bridge
	if dispatcher is not None:
		sys.modules["ifitwala_ed.utilities.file_dispatcher"] = dispatcher


def _load_module(module_name: str):
	_ensure_ed_repo_on_path()
	return importlib.import_module(module_name)


def test_task_submission_upload_session_creates_correctly(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.sessions",
		"ifitwala_drive.services.uploads.validation",
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Task Submission", "TSUB-0001"): True,
		},
		value_map={
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={
			("Task Submission", "TSUB-0001"): task_submission,
		},
	)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_tasks")
	sessions_module = _load_module("ifitwala_drive.services.uploads.sessions")
	captured: dict[str, dict] = {}

	def _fake_create_upload_session_service(payload):
		captured["payload"] = payload
		return {
			"upload_session_id": "DUS-0001",
			"status": "created",
		}

	monkeypatch.setattr(
		sessions_module,
		"create_upload_session_service",
		_fake_create_upload_session_service,
	)

	response = module.upload_task_submission_artifact_service(
		{
			"task_submission": "TSUB-0001",
			"student": "STU-0001",
			"filename_original": "essay.docx",
			"mime_type_hint": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"expected_size_bytes": 543210,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert captured["payload"] == {
		"owner_doctype": "Task Submission",
		"owner_name": "TSUB-0001",
		"attached_doctype": "Task Submission",
		"attached_name": "TSUB-0001",
		"organization": "ORG-0001",
		"school": "SCH-0001",
		"primary_subject_type": "Student",
		"primary_subject_id": "STU-0001",
		"data_class": "assessment",
		"purpose": "assessment_submission",
		"retention_policy": "until_school_exit_plus_6m",
		"slot": "submission",
		"folder": "DRF-0005",
		"filename_original": "essay.docx",
		"mime_type_hint": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		"expected_size_bytes": 543210,
		"is_private": 1,
		"upload_source": "SPA",
		"secondary_subjects": [],
	}


def test_task_submission_create_session_rejects_context_drift():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.validation",
		"ifitwala_drive.services.uploads.sessions",
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Task Submission", "TSUB-0001"): True,
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
		},
		value_map={
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={
			("Task Submission", "TSUB-0001"): task_submission,
		},
	)
	module = _load_module("ifitwala_drive.services.uploads.sessions")

	try:
		module.create_upload_session_service(
			{
				"owner_doctype": "Task Submission",
				"owner_name": "TSUB-0001",
				"attached_doctype": "Task Submission",
				"attached_name": "TSUB-0001",
				"organization": "ORG-0001",
				"school": "SCH-0001",
				"primary_subject_type": "Student",
				"primary_subject_id": "STU-9999",
				"data_class": "assessment",
				"purpose": "assessment_submission",
				"retention_policy": "until_school_exit_plus_6m",
				"slot": "submission",
				"filename_original": "essay.docx",
			}
		)
	except RuntimeError as exc:
		assert "does not match the authoritative owner context" in str(exc)
	else:
		raise AssertionError("Expected create_upload_session_service to reject mismatched student context.")


def test_create_upload_session_reuses_idempotent_request():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.validation",
		"ifitwala_drive.services.uploads.sessions",
		"ifitwala_drive.services.storage.base",
		"ifitwala_drive.services.storage.local",
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Task Submission", "TSUB-0001"): True,
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
		},
		value_map={
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={
			("Task Submission", "TSUB-0001"): task_submission,
		},
	)
	module = _load_module("ifitwala_drive.services.uploads.sessions")

	payload = {
		"owner_doctype": "Task Submission",
		"owner_name": "TSUB-0001",
		"attached_doctype": "Task Submission",
		"attached_name": "TSUB-0001",
		"organization": "ORG-0001",
		"school": "SCH-0001",
		"primary_subject_type": "Student",
		"primary_subject_id": "STU-0001",
		"data_class": "assessment",
		"purpose": "assessment_submission",
		"retention_policy": "until_school_exit_plus_6m",
		"slot": "submission",
		"filename_original": "essay.docx",
		"idempotency_key": "retry-001",
	}

	first = module.create_upload_session_service(dict(payload))
	second = module.create_upload_session_service(dict(payload))

	assert first["upload_session_id"] == "DUS-0001"
	assert second["upload_session_id"] == "DUS-0001"
	assert first["session_key"] == second["session_key"]
	assert first["upload_target"] == second["upload_target"]
	assert FakeDoc._docs_map[("Drive Upload Session", "DUS-0001")].upload_contract_json


def test_finalize_uses_authoritative_governed_creation_path(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"magic",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.sessions",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"session_key": "sess-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/essay.docx",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.docx",
			"mime_type_hint": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [
				types.SimpleNamespace(subject_type="Student", subject_id="STU-0002", role="co-owner")
			],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	file_doc_requests = _install_fake_frappe(
		exists_map={
			("Task Submission", "TSUB-0001"): True,
			("File", "Home/Attachments"): True,
		},
		value_map={
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	_install_fake_ifitwala_ed(install_dispatcher=False)
	module = _load_module("ifitwala_drive.services.uploads.finalize")
	sys.modules["magic"] = types.SimpleNamespace(
		from_buffer=lambda content,
		mime=True: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	)
	finalized_artifact: dict[str, str] = {}

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			assert object_key == "tmp/DUS-0001/essay.docx"
			return True

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			assert object_key == "tmp/DUS-0001/essay.docx"
			assert max_bytes == 2048
			return b"PK\x03\x04word"

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			assert object_key == "tmp/DUS-0001/essay.docx"
			assert final_key.startswith("files/")
			assert final_key.endswith(".docx")
			assert len(final_key.split("/")[-1].split(".")[0]) == 64
			finalized_artifact["file_url"] = f"https://storage.ifitwala.invalid/object/{final_key}"
			return {
				"object_key": final_key,
				"file_url": finalized_artifact["file_url"],
			}

		def abort_temporary_object(self, *, object_key: str) -> None:
			raise AssertionError("abort_temporary_object should not be called during finalize.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.finalize_upload_session_service(
		{
			"upload_session_id": "DUS-0001",
			"received_size_bytes": 543210,
			"content_hash": "sha256:abc123",
		}
	)

	assert response == {
		"drive_file_id": "DF-0001",
		"drive_file_version_id": "DFV-0001",
		"file_id": "FILE-0001",
		"canonical_ref": "drv:ORG-0001:DF-0001",
		"status": "completed",
		"preview_status": "not_applicable",
		"file_url": finalized_artifact["file_url"],
	}
	assert session_doc.status == "completed"
	assert session_doc.file == "FILE-0001"
	assert session_doc.drive_file == "DF-0001"
	assert session_doc.drive_file_version == "DFV-0001"
	assert session_doc.canonical_ref == "drv:ORG-0001:DF-0001"
	assert session_doc.content_hash == "sha256:abc123"
	assert len(file_doc_requests) == 1
	assert file_doc_requests[0] == {
		"doctype": "File",
		"attached_to_doctype": "Task Submission",
		"attached_to_name": "TSUB-0001",
		"is_private": 1,
		"file_name": "essay.docx",
		"file_url": finalized_artifact["file_url"],
		"folder": "Home/Attachments",
		"file_size": 543210,
	}
	created_file = FakeDoc._docs_map[("File", "FILE-0001")]
	assert getattr(created_file.flags, "governed_upload", False) is True
	assert getattr(created_file.flags, "drive_compat_projection", False) is True
	classification_doc = FakeDoc._docs_map[("File Classification", "FC-0001")]
	assert classification_doc.file == "FILE-0001"
	assert classification_doc.slot == "submission"
	assert classification_doc.primary_subject_type == "Student"
	assert classification_doc.primary_subject_id == "STU-0001"
	assert classification_doc.is_current_version == 1
	assert classification_doc.secondary_subjects == [
		{"subject_type": "Student", "subject_id": "STU-0002", "role": "co-owner"}
	]


def test_finalize_rejects_task_submission_context_drift(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/essay.docx",
			"storage_backend": "local",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.docx",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-9999",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Task Submission", "TSUB-0001"): True,
		},
		value_map={
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	module = _load_module("ifitwala_drive.services.uploads.finalize")

	class FakeStorage:
		backend_name = "local"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			raise AssertionError(
				"temporary_object_exists should not be called after authority drift is detected."
			)

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError(
				"finalize_temporary_object should not be called after authority drift is detected."
			)

		def abort_temporary_object(self, *, object_key: str) -> None:
			raise AssertionError("abort_temporary_object should not be called during finalize.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "no longer matches the authoritative Task Submission context" in str(exc)
	else:
		raise AssertionError("Expected finalize_upload_session_service to reject drifted session context.")


def test_finalize_rejects_missing_temporary_object(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/essay.pdf",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.pdf",
			"mime_type_hint": "application/pdf",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	module = _load_module("ifitwala_drive.services.uploads.finalize")

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			return False

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			raise AssertionError("read_temporary_object_head should not run when the temp object is missing.")

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError("finalize_temporary_object should not run when the temp object is missing.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "Temporary uploaded object was not found" in str(exc)
	else:
		raise AssertionError("Expected finalize_upload_session_service to reject missing temp objects.")


def test_finalize_rejects_empty_uploaded_object(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/essay.pdf",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.pdf",
			"mime_type_hint": "application/pdf",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	module = _load_module("ifitwala_drive.services.uploads.finalize")

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			return True

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			return b""

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError("finalize_temporary_object should not run for unreadable uploads.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "empty or unreadable" in str(exc)
	else:
		raise AssertionError("Expected finalize_upload_session_service to reject unreadable uploads.")


def test_finalize_rejects_dangerous_detected_mime(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"magic",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/essay.pdf",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.pdf",
			"mime_type_hint": "application/pdf",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	sys.modules["magic"] = types.SimpleNamespace(
		from_buffer=lambda content, mime=True: "application/x-dosexec"
	)
	module = _load_module("ifitwala_drive.services.uploads.finalize")

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			return True

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			return b"MZdanger"

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError("finalize_temporary_object should not run for dangerous MIME.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "not allowed for governed files" in str(exc)
	else:
		raise AssertionError("Expected finalize_upload_session_service to reject dangerous MIME types.")


def test_finalize_rejects_mime_hint_mismatch(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"magic",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/essay.pdf",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.pdf",
			"mime_type_hint": "application/pdf",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	sys.modules["magic"] = types.SimpleNamespace(from_buffer=lambda content, mime=True: "text/plain")
	module = _load_module("ifitwala_drive.services.uploads.finalize")

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			return True

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			return b"hello world"

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError("finalize_temporary_object should not run for MIME mismatch.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "does not match the claimed MIME type" in str(exc)
	else:
		raise AssertionError("Expected finalize_upload_session_service to reject MIME mismatch.")


def test_finalize_requires_python_magic_runtime_dependency(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"magic",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.inspection",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/guardian.jpg",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "upload.bin",
			"mime_type_hint": "application/octet-stream",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
		forbid_file_doc=True,
	)
	dispatcher_recorder: dict[str, dict] = {}
	_install_fake_ifitwala_ed(dispatcher_recorder=dispatcher_recorder)
	module = _load_module("ifitwala_drive.services.uploads.finalize")
	inspection_module = _load_module("ifitwala_drive.services.uploads.inspection")

	def _raise_missing_magic():
		raise ImportError("magic is unavailable")

	monkeypatch.setattr(inspection_module, "_load_magic_module", _raise_missing_magic)

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			return True

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			return b"opaque-upload"

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError("finalize_temporary_object should not run without python-magic.")

		def abort_temporary_object(self, *, object_key: str) -> None:
			raise AssertionError("abort_temporary_object should not be called during finalize.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "python-magic and libmagic" in str(exc)
	else:
		raise AssertionError("Expected finalize_upload_session_service to require python-magic.")


def test_finalize_rejects_unknown_detected_mime(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"magic",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.inspection",
		"ifitwala_drive.services.uploads.validation",
	)
	now = datetime(2026, 3, 17, 9, 0, 0)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"status": "created",
			"expires_on": now + timedelta(hours=2),
			"tmp_object_key": "tmp/DUS-0001/upload.bin",
			"storage_backend": "gcs",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "upload.bin",
			"mime_type_hint": "application/octet-stream",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
			"secondary_subjects": [],
		}
	)
	task_submission = FakeDoc(
		{
			"name": "TSUB-0001",
			"student": "STU-0001",
			"school": "SCH-0001",
			"task": "TASK-0001",
			"check_permission": lambda permission_type=None: None,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={
			("Drive Upload Session", "DUS-0001"): session_doc,
			("Task Submission", "TSUB-0001"): task_submission,
		},
		now=now,
	)
	_install_fake_ifitwala_ed(dispatcher_recorder={})
	module = _load_module("ifitwala_drive.services.uploads.finalize")
	sys.modules["magic"] = types.SimpleNamespace(from_buffer=lambda content, mime=True: "")

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			return True

		def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
			return b"mystery-content"

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			raise AssertionError("finalize_temporary_object should not run for unknown detected MIME.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.finalize_upload_session_service({"upload_session_id": "DUS-0001"})
	except RuntimeError as exc:
		assert "could not be determined" in str(exc)
	else:
		raise AssertionError(
			"Expected finalize_upload_session_service to fail closed on unknown detected MIME."
		)


def test_upload_session_blob_accepts_proxy_post(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.uploads",
		"ifitwala_drive.services.uploads.sessions",
	)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"session_key": "sess-0001",
			"status": "created",
			"tmp_object_key": "tmp/DUS-0001/essay.txt",
			"storage_backend": "local",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"intended_slot": "submission",
			"upload_contract_json": '{"upload_strategy":"proxy_post","upload_target":{"method":"POST","url":"/proxy","headers":{}}}',
		}
	)
	_install_fake_frappe(docs_map={("Drive Upload Session", "DUS-0001"): session_doc})
	import frappe

	frappe.request = types.SimpleNamespace(files={}, get_data=lambda: b"hello")
	module = _load_module("ifitwala_drive.api.uploads")
	writes: list[tuple[str, bytes]] = []

	class FakeStorage:
		def write_temporary_object(self, *, object_key: str, content: bytes):
			writes.append((object_key, content))
			return {"object_key": object_key, "size_bytes": len(content)}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.upload_session_blob(upload_session_id="DUS-0001")

	assert response == {
		"upload_session_id": "DUS-0001",
		"status": "uploaded",
		"received_size_bytes": 5,
	}
	assert writes == [("tmp/DUS-0001/essay.txt", b"hello")]


def test_upload_session_blob_rejects_non_proxy_strategy():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.uploads",
		"ifitwala_drive.services.uploads.sessions",
	)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"session_key": "sess-0001",
			"status": "created",
			"tmp_object_key": "tmp/DUS-0001/essay.txt",
			"storage_backend": "gcs",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"intended_slot": "submission",
			"upload_contract_json": '{"upload_strategy":"resumable_put","upload_target":{"method":"PUT","url":"https://upload.invalid/session","headers":{}}}',
		}
	)
	_install_fake_frappe(docs_map={("Drive Upload Session", "DUS-0001"): session_doc})
	module = _load_module("ifitwala_drive.api.uploads")

	try:
		module.upload_session_blob(upload_session_id="DUS-0001")
	except RuntimeError as exc:
		assert "only allowed for proxy_post sessions" in str(exc)
	else:
		raise AssertionError("Expected upload_session_blob to reject non-proxy strategies.")


def test_ingest_upload_session_content_uses_upload_target_for_non_proxy(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.uploads",
		"ifitwala_drive.services.uploads.sessions",
	)
	session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"session_key": "sess-0001",
			"status": "created",
			"tmp_object_key": "tmp/DUS-0001/essay.txt",
			"storage_backend": "gcs",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"intended_slot": "submission",
			"upload_contract_json": '{"upload_strategy":"resumable_put","upload_target":{"method":"PUT","url":"https://upload.invalid/session","headers":{"Content-Type":"text/plain"}}}',
		}
	)
	_install_fake_frappe(docs_map={("Drive Upload Session", "DUS-0001"): session_doc})
	module = _load_module("ifitwala_drive.api.uploads")
	uploads: list[tuple[dict[str, object], bytes]] = []

	def _fake_upload_bytes_to_target(*, upload_target: dict[str, object], content: bytes):
		uploads.append((upload_target, content))

	monkeypatch.setattr(module, "_upload_bytes_to_target", _fake_upload_bytes_to_target)

	response = module.ingest_upload_session_content(
		upload_session_id="DUS-0001",
		content=b"hello",
	)

	assert response == {
		"upload_session_id": "DUS-0001",
		"status": "uploaded",
		"received_size_bytes": 5,
	}
	assert uploads == [
		(
			{
				"method": "PUT",
				"url": "https://upload.invalid/session",
				"headers": {"Content-Type": "text/plain"},
			},
			b"hello",
		)
	]
	assert session_doc.status == "uploaded"
	assert session_doc.received_size_bytes == 5


def test_create_drive_file_artifacts_recovers_from_duplicate_inserts():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.creation",
	)
	existing_drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0099",
			"source_upload_session": "DUS-0001",
			"canonical_ref": "drv:ORG-0001:DF-0099",
			"current_version": "DFV-0099",
		}
	)
	_install_fake_frappe(
		docs_map={},
		duplicate_insert_once={
			"Drive File": 1,
		},
		duplicate_insert_materialized_docs={
			"Drive File": existing_drive_file,
		},
	)
	module = _load_module("ifitwala_drive.services.files.creation")
	upload_session_doc = FakeDoc(
		{
			"name": "DUS-0001",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.docx",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
		}
	)

	response = module.create_drive_file_artifacts(
		upload_session_doc=upload_session_doc,
		file_id="FILE-0001",
		storage_artifact={
			"storage_backend": "gcs",
			"object_key": "files/ab/cd/object.docx",
		},
	)

	assert response == {
		"drive_file_id": "DF-0099",
		"drive_file_version_id": "DFV-0099",
		"canonical_ref": "drv:ORG-0001:DF-0099",
		"drive_binding_id": None,
	}


def test_create_drive_file_artifacts_creates_primary_binding_when_ed_requests_one():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.creation",
	)
	_install_fake_frappe(docs_map={})
	module = _load_module("ifitwala_drive.services.files.creation")
	upload_session_doc = FakeDoc(
		{
			"name": "DUS-0002",
			"attached_doctype": "Organization",
			"attached_name": "ORG-0001",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"organization": "ORG-0001",
			"school": None,
			"upload_source": "Desk",
			"filename_original": "logo.png",
			"is_private": 0,
			"intended_primary_subject_type": "Organization",
			"intended_primary_subject_id": "ORG-0001",
			"intended_data_class": "branding",
			"intended_purpose": "organization_logo_display",
			"intended_retention_policy": "until_replaced",
			"intended_slot": "organization_logo__main",
		}
	)

	response = module.create_drive_file_artifacts(
		upload_session_doc=upload_session_doc,
		file_id="FILE-0002",
		storage_artifact={
			"storage_backend": "gcs",
			"object_key": "files/aa/bb/object.png",
		},
		binding_role="organization_media",
	)

	assert response["drive_file_id"] == "DF-0001"
	assert response["drive_file_version_id"] == "DFV-0001"
	assert response["canonical_ref"] == "drv:ORG-0001:DF-0001"
	assert response["drive_binding_id"] == "DB-0001"


def test_create_drive_file_artifacts_creates_pending_image_derivatives_and_preview_job():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.creation",
		"ifitwala_drive.services.files.derivatives",
	)
	_install_fake_frappe(docs_map={})
	module = _load_module("ifitwala_drive.services.files.creation")
	upload_session_doc = FakeDoc(
		{
			"name": "DUS-0003",
			"attached_doctype": "Organization",
			"attached_name": "ORG-0001",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"organization": "ORG-0001",
			"school": None,
			"upload_source": "Desk",
			"filename_original": "cover.png",
			"is_private": 0,
			"intended_primary_subject_type": "Organization",
			"intended_primary_subject_id": "ORG-0001",
			"intended_data_class": "branding",
			"intended_purpose": "organization_public_media",
			"intended_retention_policy": "until_replaced",
			"intended_slot": "organization_media__cover",
		}
	)

	response = module.create_drive_file_artifacts(
		upload_session_doc=upload_session_doc,
		file_id="FILE-0003",
		storage_artifact={
			"storage_backend": "gcs",
			"object_key": "files/cc/dd/object.png",
			"mime_type": "image/png",
		},
	)

	assert response["drive_file_id"] == "DF-0001"
	drive_file = FakeDoc._docs_map[("Drive File", "DF-0001")]
	assert drive_file.preview_status == "pending"

	thumb = FakeDoc._docs_map[("Drive File Derivative", "DFD-0001")]
	viewer = FakeDoc._docs_map[("Drive File Derivative", "DFD-0002")]
	assert thumb.derivative_role == "thumb"
	assert thumb.status == "pending"
	assert thumb.drive_file_version == "DFV-0001"
	assert viewer.derivative_role == "viewer_preview"
	assert viewer.status == "pending"
	assert viewer.drive_file_version == "DFV-0001"

	job = FakeDoc._docs_map[("Drive Processing Job", "DPJ-0001")]
	assert job.job_type == "preview"
	assert job.status == "queued"
	assert job.drive_file == "DF-0001"
	assert job.file == "FILE-0003"


def test_create_drive_file_artifacts_creates_pending_pdf_derivative_and_preview_job():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.creation",
		"ifitwala_drive.services.files.derivatives",
	)
	_install_fake_frappe(docs_map={})
	module = _load_module("ifitwala_drive.services.files.creation")
	upload_session_doc = FakeDoc(
		{
			"name": "DUS-0005",
			"attached_doctype": "Org Communication",
			"attached_name": "COMM-0001",
			"owner_doctype": "Org Communication",
			"owner_name": "COMM-0001",
			"organization": "ORG-0001",
			"school": None,
			"upload_source": "SPA",
			"filename_original": "announcement.pdf",
			"is_private": 1,
			"intended_primary_subject_type": "Organization",
			"intended_primary_subject_id": "ORG-0001",
			"intended_data_class": "administrative",
			"intended_purpose": "administrative",
			"intended_retention_policy": "fixed_7y",
			"intended_slot": "communication_attachment__row-001",
		}
	)

	response = module.create_drive_file_artifacts(
		upload_session_doc=upload_session_doc,
		file_id="FILE-0005",
		storage_artifact={
			"storage_backend": "gcs",
			"object_key": "files/pdf/object.pdf",
			"mime_type": "application/pdf",
		},
	)

	assert response["drive_file_id"] == "DF-0001"
	drive_file = FakeDoc._docs_map[("Drive File", "DF-0001")]
	assert drive_file.preview_status == "pending"

	pdf_page = FakeDoc._docs_map[("Drive File Derivative", "DFD-0001")]
	assert pdf_page.derivative_role == "pdf_page_1"
	assert pdf_page.status == "pending"
	assert pdf_page.drive_file_version == "DFV-0001"

	job = FakeDoc._docs_map[("Drive Processing Job", "DPJ-0001")]
	assert job.job_type == "preview"
	assert job.status == "queued"
	assert job.drive_file == "DF-0001"
	assert job.file == "FILE-0005"


def test_create_drive_file_artifacts_marks_unsupported_preview_not_applicable():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.creation",
		"ifitwala_drive.services.files.derivatives",
	)
	_install_fake_frappe(docs_map={})
	module = _load_module("ifitwala_drive.services.files.creation")
	upload_session_doc = FakeDoc(
		{
			"name": "DUS-0004",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"upload_source": "SPA",
			"filename_original": "essay.docx",
			"is_private": 1,
			"intended_primary_subject_type": "Student",
			"intended_primary_subject_id": "STU-0001",
			"intended_data_class": "assessment",
			"intended_purpose": "assessment_submission",
			"intended_retention_policy": "until_school_exit_plus_6m",
			"intended_slot": "submission",
		}
	)

	response = module.create_drive_file_artifacts(
		upload_session_doc=upload_session_doc,
		file_id="FILE-0004",
		storage_artifact={
			"storage_backend": "gcs",
			"object_key": "files/ee/ff/object.docx",
			"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		},
	)

	assert response["drive_file_id"] == "DF-0001"
	drive_file = FakeDoc._docs_map[("Drive File", "DF-0001")]
	assert drive_file.preview_status == "not_applicable"
	assert not any(doctype == "Drive File Derivative" for doctype, _name in FakeDoc._docs_map)
	assert not any(doctype == "Drive Processing Job" for doctype, _name in FakeDoc._docs_map)


def test_folder_resolution_recovers_from_duplicate_folder_insert():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.folders.resolution",
	)
	_install_fake_frappe(
		docs_map={},
		duplicate_insert_once={"Drive Folder": 1},
		duplicate_insert_materialized_docs={
			"Drive Folder": FakeDoc(
				{
					"doctype": "Drive Folder",
					"name": "DRF-9001",
					"title": "Student",
					"owner_doctype": "Organization",
					"owner_name": "ORG-0001",
					"organization": "ORG-0001",
					"school": None,
					"folder_kind": "system_bound",
					"system_key": "ORG-0001|no-school|Organization|ORG-0001|root|system_bound|student",
				}
			),
		},
	)
	module = _load_module("ifitwala_drive.services.folders.resolution")

	folder_id = module.resolve_student_image_folder(
		student="STU-0001",
		organization="ORG-0001",
		school="SCH-0001",
	)

	assert folder_id == "DRF-0003"
