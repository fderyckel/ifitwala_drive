from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime
from typing import ClassVar


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(
			module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes
		) or module_name.startswith("ifitwala_drive.services.files.derivatives"):
			sys.modules.pop(module_name, None)
	FakeDoc._docs_map = {}
	FakeDoc._insert_counters = {}


class FakeDoc:
	_docs_map: ClassVar[dict[tuple[str, str], "FakeDoc"]] = {}
	_insert_counters: ClassVar[dict[str, int]] = {}

	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.saved = 0

	def get(self, key, default=None):
		return getattr(self, key, default)

	def save(self, ignore_permissions=False):
		self.saved += 1
		if getattr(self, "doctype", None) and getattr(self, "name", None):
			self._docs_map[(self.doctype, self.name)] = self
		return self

	def insert(self, ignore_permissions=False):
		if not getattr(self, "name", None):
			prefix_map = {
				"Drive File Version": "DFV",
				"Drive File Derivative": "DFD",
				"Drive Access Event": "DAE",
				"Drive Processing Job": "DPJ",
				"Drive Erasure Request": "DER",
			}
			prefix = prefix_map.get(getattr(self, "doctype", ""), "DOC")
			next_value = self._insert_counters.get(prefix, 0)
			while True:
				next_value += 1
				candidate = f"{prefix}-{next_value:04d}"
				if (getattr(self, "doctype", ""), candidate) not in self._docs_map:
					self._insert_counters[prefix] = next_value
					self.name = candidate
					break
		self._docs_map[(self.doctype, self.name)] = self
		return self

	def check_permission(self, permission_type=None):
		return None


def _matches(doc, filters: dict[str, object]) -> bool:
	for key, value in filters.items():
		if getattr(doc, key, None) != value:
			return False
	return True


def _install_fake_frappe(*, docs_map=None, now=None):
	docs_map = docs_map or {}
	FakeDoc._docs_map = docs_map
	FakeDoc._insert_counters = {}
	now = now or datetime(2026, 4, 15, 10, 0, 0)

	class FakeDB:
		def exists(self, doctype, name=None):
			if isinstance(name, dict):
				for candidate_doctype, candidate_name in FakeDoc._docs_map:
					if candidate_doctype != doctype:
						continue
					if _matches(FakeDoc._docs_map[(candidate_doctype, candidate_name)], name):
						return candidate_name
				return False
			return (doctype, name) in FakeDoc._docs_map

		def get_value(self, doctype, name, fieldname):
			if isinstance(name, dict):
				for candidate_doctype, candidate_name in FakeDoc._docs_map:
					if candidate_doctype != doctype:
						continue
					doc = FakeDoc._docs_map[(candidate_doctype, candidate_name)]
					if _matches(doc, name):
						if fieldname == "name":
							return candidate_name
						return getattr(doc, fieldname, None)
				return None

			doc = FakeDoc._docs_map.get((doctype, name))
			if doc is None:
				return None
			return getattr(doc, fieldname, None)

	def _throw(message, exc=None):
		raise RuntimeError(message)

	def _get_doc(arg1, arg2=None):
		if isinstance(arg1, dict):
			return FakeDoc(arg1)
		return FakeDoc._docs_map[(arg1, arg2)]

	def _get_all(doctype, filters=None, fields=None):
		filters = filters or {}
		fields = fields or ["name"]
		rows = []
		for candidate_doctype, candidate_name in list(FakeDoc._docs_map):
			if candidate_doctype != doctype:
				continue
			doc = FakeDoc._docs_map[(candidate_doctype, candidate_name)]
			if not _matches(doc, filters):
				continue
			row = {}
			for fieldname in fields:
				row[fieldname] = candidate_name if fieldname == "name" else getattr(doc, fieldname, None)
			rows.append(row)
		return rows

	def _delete_doc(doctype, name, ignore_permissions=False):
		FakeDoc._docs_map.pop((doctype, name), None)

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.db = FakeDB()
	frappe.get_doc = _get_doc
	frappe.get_all = _get_all
	frappe.delete_doc = _delete_doc
	frappe.session = types.SimpleNamespace(user="manager@example.com")
	frappe.local = types.SimpleNamespace(request_ip="127.0.0.1")
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None)
	frappe.as_json = lambda value, indent=None: str(value)

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: now

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def test_replace_drive_file_version_creates_new_current_version(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.versions",
	)
	drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0001",
			"file": "FILE-0001",
			"display_name": "essay.docx",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"status": "active",
			"preview_status": "ready",
			"storage_object_key": "files/original.docx",
			"content_hash": "sha256:old",
			"current_version": "DFV-0001",
			"current_version_no": 1,
			"erasure_state": "active",
			"legal_hold": 0,
		}
	)
	current_version = FakeDoc(
		{
			"doctype": "Drive File Version",
			"name": "DFV-0001",
			"drive_file": "DF-0001",
			"version_no": 1,
			"file": "FILE-0001",
			"is_current": 1,
			"storage_object_key": "files/original.docx",
		}
	)
	binding = FakeDoc(
		{
			"doctype": "Drive Binding",
			"name": "DB-0001",
			"drive_file": "DF-0001",
			"file": "FILE-0001",
			"status": "active",
		}
	)
	task_submission = FakeDoc({"doctype": "Task Submission", "name": "TSUB-0001"})
	old_thumb = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0001",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0001",
			"derivative_role": "thumb",
			"status": "ready",
		}
	)
	old_viewer = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0002",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0001",
			"derivative_role": "viewer_preview",
			"status": "ready",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0001"): drive_file,
			("Drive File Version", "DFV-0001"): current_version,
			("Drive File Derivative", "DFD-0001"): old_thumb,
			("Drive File Derivative", "DFD-0002"): old_viewer,
			("Drive Binding", "DB-0001"): binding,
			("Task Submission", "TSUB-0001"): task_submission,
		}
	)
	module = _load_module("ifitwala_drive.services.files.versions")

	response = module.replace_drive_file_version_service(
		{
			"drive_file_id": "DF-0001",
			"new_file_artifact": {
				"file_id": "FILE-0002",
				"filename_original": "essay_v2.png",
				"storage_object_key": "files/replaced.png",
				"mime_type": "image/png",
				"size_bytes": 545000,
				"content_hash": "sha256:new",
			},
			"reason": "replace",
		}
	)

	assert response == {
		"drive_file_id": "DF-0001",
		"drive_file_version_id": "DFV-0002",
		"current_version_no": 2,
		"status": "active",
	}
	assert drive_file.file == "FILE-0002"
	assert drive_file.display_name == "essay_v2.png"
	assert drive_file.storage_object_key == "files/replaced.png"
	assert drive_file.content_hash == "sha256:new"
	assert drive_file.current_version == "DFV-0002"
	assert drive_file.current_version_no == 2
	assert drive_file.preview_status == "pending"
	assert current_version.is_current == 0
	assert binding.file == "FILE-0002"
	assert old_thumb.status == "stale"
	assert old_viewer.status == "stale"

	new_version = FakeDoc._docs_map[("Drive File Version", "DFV-0002")]
	assert new_version.source_version == "DFV-0001"
	assert new_version.source_file == "FILE-0001"
	assert new_version.version_reason == "replace"

	new_thumb = FakeDoc._docs_map[("Drive File Derivative", "DFD-0003")]
	new_viewer = FakeDoc._docs_map[("Drive File Derivative", "DFD-0004")]
	assert new_thumb.derivative_role == "thumb"
	assert new_thumb.status == "pending"
	assert new_thumb.drive_file_version == "DFV-0002"
	assert new_viewer.derivative_role == "viewer_preview"
	assert new_viewer.status == "pending"
	assert new_viewer.drive_file_version == "DFV-0002"

	preview_job = FakeDoc._docs_map[("Drive Processing Job", "DPJ-0001")]
	assert preview_job.job_type == "preview"
	assert preview_job.status == "queued"
	assert preview_job.file == "FILE-0002"

	access_event = FakeDoc._docs_map[("Drive Access Event", "DAE-0001")]
	assert access_event.event_type == "replace"


def test_execute_drive_erasure_request_erases_all_versions_and_deactivates_bindings(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.erasure",
		"ifitwala_drive.services.audit.events",
	)
	drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0001",
			"primary_subject_type": "Student",
			"primary_subject_id": "STU-0001",
			"status": "active",
			"erasure_state": "active",
			"legal_hold": 0,
			"slot": "submission",
			"file": "FILE-0002",
			"storage_backend": "local",
			"storage_object_key": "files/current.docx",
			"current_version": "DFV-0002",
			"preview_status": "pending",
		}
	)
	version_one = FakeDoc(
		{
			"doctype": "Drive File Version",
			"name": "DFV-0001",
			"drive_file": "DF-0001",
			"file": "FILE-0001",
			"storage_object_key": "files/original.docx",
		}
	)
	version_two = FakeDoc(
		{
			"doctype": "Drive File Version",
			"name": "DFV-0002",
			"drive_file": "DF-0001",
			"file": "FILE-0002",
			"storage_object_key": "files/current.docx",
		}
	)
	binding = FakeDoc(
		{
			"doctype": "Drive Binding",
			"name": "DB-0001",
			"drive_file": "DF-0001",
			"file": "FILE-0002",
			"status": "active",
		}
	)
	thumb = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0001",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0002",
			"status": "ready",
			"storage_backend": "local",
			"storage_object_key": "derivatives/current-thumb.webp",
		}
	)
	stale_viewer = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0002",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0001",
			"status": "stale",
			"storage_backend": "local",
			"storage_object_key": "derivatives/stale-viewer.webp",
		}
	)
	file_one = FakeDoc({"doctype": "File", "name": "FILE-0001", "file_url": "/private/files/original.docx"})
	file_two = FakeDoc({"doctype": "File", "name": "FILE-0002", "file_url": "/private/files/current.docx"})
	request = FakeDoc(
		{
			"doctype": "Drive Erasure Request",
			"name": "DER-0001",
			"data_subject_type": "Student",
			"data_subject_id": "STU-0001",
			"scope": "files_only",
			"status": "approved",
			"result_deleted_count": 0,
			"result_blocked_count": 0,
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0001"): drive_file,
			("Drive File Version", "DFV-0001"): version_one,
			("Drive File Version", "DFV-0002"): version_two,
			("Drive Binding", "DB-0001"): binding,
			("Drive File Derivative", "DFD-0001"): thumb,
			("Drive File Derivative", "DFD-0002"): stale_viewer,
			("File", "FILE-0001"): file_one,
			("File", "FILE-0002"): file_two,
			("Drive Erasure Request", "DER-0001"): request,
		}
	)
	module = _load_module("ifitwala_drive.services.audit.erasure")
	derivatives_module = _load_module("ifitwala_drive.services.files.derivatives")

	deleted_object_keys: list[str] = []

	class FakeStorage:
		def delete_object(self, *, object_key: str) -> None:
			deleted_object_keys.append(object_key)

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())
	monkeypatch.setattr(derivatives_module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.execute_drive_erasure_request_service({"erasure_request_id": "DER-0001"})

	assert response["erasure_request_id"] == "DER-0001"
	assert response["status"] == "completed"
	assert response["deleted_count"] == 1
	assert response["blocked_count"] == 0
	assert response["retained_count"] == 0
	assert response["skipped_count"] == 0
	assert response["slots_touched"] == ["submission"]
	assert response["metadata_filters"] == {}
	assert [item["drive_file_id"] for item in response["erased"]] == ["DF-0001"]
	assert response["erased"][0]["reason"] == "approved_subject_erasure"
	assert response["retained"] == []
	assert response["skipped"] == []
	assert sorted(deleted_object_keys) == [
		"derivatives/current-thumb.webp",
		"derivatives/stale-viewer.webp",
		"files/current.docx",
		"files/original.docx",
	]
	assert drive_file.status == "erased"
	assert drive_file.preview_status == "not_applicable"
	assert drive_file.erasure_state == "erased"
	assert binding.status == "inactive"
	assert file_one.file_url is None
	assert file_two.file_url is None
	assert ("Drive File Derivative", "DFD-0001") not in FakeDoc._docs_map
	assert ("Drive File Derivative", "DFD-0002") not in FakeDoc._docs_map
	assert request.result_deleted_count == 1
	assert request.result_blocked_count == 0
	assert request.status == "completed"

	access_event = FakeDoc._docs_map[("Drive Access Event", "DAE-0001")]
	assert access_event.event_type == "erase"


def test_execute_drive_erasure_request_uses_metadata_filters_and_ed_decision_audit(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.erasure",
		"ifitwala_drive.services.audit.events",
	)
	erase_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-ERASE",
			"primary_subject_type": "Student",
			"primary_subject_id": "STU-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"attached_doctype": "Task Submission",
			"attached_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"data_class": "assessment",
			"purpose": "assessment_submission",
			"retention_policy": "until_school_exit_plus_6m",
			"status": "active",
			"erasure_state": "active",
			"legal_hold": 0,
			"slot": "submission",
			"file": "FILE-ERASE",
			"storage_backend": "local",
			"storage_object_key": "files/erase.docx",
			"current_version": "DFV-ERASE",
			"preview_status": "ready",
		}
	)
	retain_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-RETAIN",
			"primary_subject_type": "Student",
			"primary_subject_id": "STU-0001",
			"owner_doctype": "Student Log",
			"owner_name": "SLOG-0001",
			"attached_doctype": "Student Log",
			"attached_name": "SLOG-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"data_class": "safeguarding",
			"purpose": "safeguarding_evidence",
			"retention_policy": "fixed_7y",
			"status": "active",
			"erasure_state": "active",
			"legal_hold": 0,
			"slot": "student_log_evidence__row_0001",
			"file": "FILE-RETAIN",
			"storage_backend": "local",
			"storage_object_key": "files/retain.pdf",
			"current_version": "DFV-RETAIN",
			"preview_status": "ready",
		}
	)
	hold_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-HOLD",
			"primary_subject_type": "Student",
			"primary_subject_id": "STU-0001",
			"owner_doctype": "Student",
			"owner_name": "STU-0001",
			"attached_doctype": "Student Patient",
			"attached_name": "SPAT-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
			"data_class": "safeguarding",
			"purpose": "medical_record",
			"retention_policy": "until_school_exit_plus_6m",
			"status": "active",
			"erasure_state": "active",
			"legal_hold": 1,
			"slot": "health_vaccination_proof_mmr",
			"file": "FILE-HOLD",
			"storage_backend": "local",
			"storage_object_key": "files/hold.pdf",
			"current_version": "DFV-HOLD",
			"preview_status": "ready",
		}
	)
	out_of_scope_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-OTHER-SCHOOL",
			"primary_subject_type": "Student",
			"primary_subject_id": "STU-0001",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0002",
			"organization": "ORG-0001",
			"school": "SCH-9999",
			"purpose": "assessment_submission",
			"retention_policy": "until_school_exit_plus_6m",
			"status": "active",
			"erasure_state": "active",
			"legal_hold": 0,
			"slot": "submission",
			"file": "FILE-OTHER-SCHOOL",
			"storage_backend": "local",
			"storage_object_key": "files/other.docx",
			"current_version": "DFV-OTHER-SCHOOL",
			"preview_status": "ready",
		}
	)
	request = FakeDoc(
		{
			"doctype": "Drive Erasure Request",
			"name": "DER-0002",
			"data_subject_type": "Student",
			"data_subject_id": "STU-0001",
			"scope": "files_only",
			"status": "approved",
			"result_deleted_count": 0,
			"result_blocked_count": 0,
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-ERASE"): erase_file,
			("Drive File", "DF-RETAIN"): retain_file,
			("Drive File", "DF-HOLD"): hold_file,
			("Drive File", "DF-OTHER-SCHOOL"): out_of_scope_file,
			("File", "FILE-ERASE"): FakeDoc({"doctype": "File", "name": "FILE-ERASE"}),
			("Drive Erasure Request", "DER-0002"): request,
		}
	)
	module = _load_module("ifitwala_drive.services.audit.erasure")
	deleted_object_keys: list[str] = []

	class FakeStorage:
		def delete_object(self, *, object_key: str) -> None:
			deleted_object_keys.append(object_key)

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())
	monkeypatch.setattr(
		module,
		"delete_derivative_artifacts_for_drive_file",
		lambda drive_file_id: deleted_object_keys.append(f"derivatives/{drive_file_id}"),
	)

	response = module.execute_drive_erasure_request_service(
		{
			"erasure_request_id": "DER-0002",
			"metadata_filters": {"organization": "ORG-0001", "school": "SCH-0001"},
			"decision_items": [
				{"drive_file_id": "DF-ERASE", "decision": "erase", "reason": "expired_retention"},
				{"drive_file_id": "DF-RETAIN", "decision": "retain", "reason": "school_policy_fixed_7y"},
				{"drive_file_id": "DF-HOLD", "decision": "erase", "reason": "subject_request"},
			],
		}
	)

	assert response["status"] == "blocked"
	assert response["metadata_filters"] == {"organization": "ORG-0001", "school": "SCH-0001"}
	assert response["deleted_count"] == 1
	assert response["blocked_count"] == 1
	assert response["retained_count"] == 2
	assert response["skipped_count"] == 0
	assert [item["drive_file_id"] for item in response["erased"]] == ["DF-ERASE"]
	assert response["erased"][0]["reason"] == "expired_retention"
	assert {(item["drive_file_id"], item["decision"], item["reason"]) for item in response["retained"]} == {
		("DF-RETAIN", "retain", "school_policy_fixed_7y"),
		("DF-HOLD", "retain", "legal_hold"),
	}
	assert "files/erase.docx" in deleted_object_keys
	assert "derivatives/DF-ERASE" in deleted_object_keys
	assert "files/other.docx" not in deleted_object_keys
	assert erase_file.status == "erased"
	assert retain_file.status == "active"
	assert hold_file.erasure_state == "blocked_legal"
	assert out_of_scope_file.status == "active"
	assert request.result_deleted_count == 1
	assert request.result_blocked_count == 1


def test_prune_stale_derivatives_service_removes_expired_rows(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.derivatives",
	)
	stale_old = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0001",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0001",
			"status": "stale",
			"storage_backend": "local",
			"storage_object_key": "derivatives/stale-old.webp",
			"modified": "2026-03-01 08:00:00",
		}
	)
	stale_recent = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0002",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0002",
			"status": "stale",
			"storage_backend": "local",
			"storage_object_key": "derivatives/stale-recent.webp",
			"modified": "2026-04-14 08:00:00",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File Derivative", "DFD-0001"): stale_old,
			("Drive File Derivative", "DFD-0002"): stale_recent,
		},
		now=datetime(2026, 4, 15, 10, 0, 0),
	)
	module = _load_module("ifitwala_drive.services.files.derivatives")

	deleted_object_keys: list[str] = []

	class FakeStorage:
		def delete_object(self, *, object_key: str) -> None:
			deleted_object_keys.append(object_key)

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.prune_stale_derivatives_service(grace_days=30)

	assert response == {
		"status": "completed",
		"grace_days": 30,
		"pruned_count": 1,
		"cutoff": "2026-03-16 10:00:00",
	}
	assert deleted_object_keys == ["derivatives/stale-old.webp"]
	assert ("Drive File Derivative", "DFD-0001") not in FakeDoc._docs_map
	assert ("Drive File Derivative", "DFD-0002") in FakeDoc._docs_map
