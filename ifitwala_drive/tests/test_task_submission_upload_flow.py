# ifitwala_drive/tests/test_task_submission_upload_flow.py

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes) or module_name.startswith(
			"ifitwala_drive.services.folders"
		):
			sys.modules.pop(module_name, None)
	FakeDoc._insert_counters = {}


class FakeDoc:
	_insert_counters = {}

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
		if not getattr(self, "name", None):
			doctype = getattr(self, "doctype", "")
			prefix_map = {
				"Drive Upload Session": "DUS",
				"Drive File": "DF",
				"Drive File Version": "DFV",
				"Drive Binding": "DB",
				"Drive Folder": "DRF",
			}
			prefix = prefix_map.get(doctype, "DOC")
			next_value = self._insert_counters.get(prefix, 0) + 1
			self._insert_counters[prefix] = next_value
			self.name = f"{prefix}-{next_value:04d}"
		self.inserted += 1
		return self


def _install_fake_frappe(
	*,
	exists_map: dict[tuple[str, object], object] | None = None,
	value_map: dict[tuple[str, object, object], object] | None = None,
	docs_map: dict[tuple[str, str], FakeDoc] | None = None,
	now: datetime | None = None,
	forbid_file_doc: bool = False,
):
	exists_map = exists_map or {}
	value_map = value_map or {}
	docs_map = docs_map or {}
	now = now or datetime(2026, 3, 17, 9, 0, 0)
	file_doc_requests: list[dict] = []

	class FakeDB:
		def exists(self, doctype, name=None):
			if isinstance(name, dict):
				key = (doctype, tuple(sorted(name.items())))
				if key in exists_map:
					return exists_map[key]
				return False

			key = (doctype, name)
			if key in exists_map:
				return exists_map[key]

			if isinstance(name, str):
				return (doctype, name) in docs_map

			return False

		def get_value(self, doctype, name, fieldname):
			if isinstance(name, dict):
				key = (doctype, tuple(sorted(name.items())), fieldname)
				if key in value_map:
					return value_map[key]
				return None

			key = (doctype, name, fieldname)
			if key in value_map:
				return value_map[key]

			doc = docs_map.get((doctype, name))
			if doc is None:
				return None

			if isinstance(fieldname, (list, tuple)):
				return [getattr(doc, field, None) for field in fieldname]

			return getattr(doc, fieldname, None)

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
	frappe.log_error = lambda *args, **kwargs: None
	frappe.get_traceback = lambda: "traceback"
	frappe.as_json = lambda value, indent=None: str(value)
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
	frappe.get_site_path = lambda *parts: "/tmp/" + "/".join(parts)

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


def _install_fake_ifitwala_ed(*, dispatcher_recorder: dict):
	dispatcher = types.ModuleType("ifitwala_ed.utilities.file_dispatcher")

	def create_and_classify_file(**kwargs):
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

	utilities = types.ModuleType("ifitwala_ed.utilities")
	utilities.file_dispatcher = dispatcher
	utilities.file_management = file_management

	ifitwala_ed = types.ModuleType("ifitwala_ed")
	ifitwala_ed.utilities = utilities

	sys.modules["ifitwala_ed"] = ifitwala_ed
	sys.modules["ifitwala_ed.utilities"] = utilities
	sys.modules["ifitwala_ed.utilities.file_dispatcher"] = dispatcher
	sys.modules["ifitwala_ed.utilities.file_management"] = file_management


def _load_module(module_name: str):
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


def test_finalize_uses_authoritative_governed_creation_path(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_ed",
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
		},
		value_map={
			("School", "SCH-0001", "organization"): "ORG-0001",
		},
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

	class FakeStorage:
		backend_name = "gcs"

		def temporary_object_exists(self, *, object_key: str) -> bool:
			assert object_key == "tmp/DUS-0001/essay.docx"
			return True

		def finalize_temporary_object(self, *, object_key: str, final_key: str):
			assert object_key == "tmp/DUS-0001/essay.docx"
			assert final_key.startswith("files/")
			assert final_key.endswith(".docx")
			assert len(final_key.split("/")[-1].split(".")[0]) == 64
			return {
				"object_key": final_key,
				"file_url": f"https://storage.ifitwala.invalid/object/{final_key}",
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
		"preview_status": "pending",
		"file_url": None,
	}
	assert session_doc.status == "completed"
	assert session_doc.file == "FILE-0001"
	assert session_doc.drive_file == "DF-0001"
	assert session_doc.drive_file_version == "DFV-0001"
	assert session_doc.canonical_ref == "drv:ORG-0001:DF-0001"
	assert session_doc.content_hash == "sha256:abc123"
	assert dispatcher_recorder["call"]["classification"]["slot"] == "submission"
	assert dispatcher_recorder["call"]["classification"]["primary_subject_type"] == "Student"
	assert dispatcher_recorder["call"]["secondary_subjects"] == [
		{"subject_type": "Student", "subject_id": "STU-0002", "role": "co-owner"}
	]
	assert dispatcher_recorder["call"]["context_override"] == {
		"student": "STU-0001",
		"task_name": "TASK-0001",
		"routing": "task_submission",
	}
	assert file_doc_requests == []


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
