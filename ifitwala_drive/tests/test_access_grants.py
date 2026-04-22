from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime
from typing import ClassVar


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if (
			any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes)
			or module_name.startswith("ifitwala_drive.services.files.derivatives")
			or module_name.startswith("ifitwala_drive.services.files.versions")
		):
			sys.modules.pop(module_name, None)


class FakeDoc:
	_insert_counters: ClassVar[dict[str, int]] = {}

	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.saved = 0
		self.inserted = 0

	def check_permission(self, permission_type=None):
		return None

	def save(self, ignore_permissions=False):
		self.saved += 1
		doctype = getattr(self, "doctype", None)
		name = getattr(self, "name", None)
		if doctype and name:
			_install_fake_frappe._docs_map[(doctype, name)] = self
		return self

	def insert(self, ignore_permissions=False):
		doctype = getattr(self, "doctype", "")
		if not getattr(self, "name", None):
			prefix_map = {
				"Drive File Version": "DFV",
				"Drive File Derivative": "DFD",
				"Drive Processing Job": "DPJ",
			}
			prefix = prefix_map.get(doctype, "DOC")
			next_value = self._insert_counters.get(prefix, 0) + 1
			self._insert_counters[prefix] = next_value
			self.name = f"{prefix}-{next_value:04d}"
		self.inserted += 1
		_install_fake_frappe._docs_map[(doctype, self.name)] = self
		return self


def _install_fake_frappe(*, exists_map=None, value_map=None, docs_map=None, now=None):
	exists_map = exists_map or {}
	value_map = value_map or {}
	docs_map = docs_map or {}
	now = now or datetime(2026, 3, 19, 10, 0, 0)
	_install_fake_frappe._docs_map = docs_map
	FakeDoc._insert_counters = {}

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
			return (doctype, name) in docs_map

		def get_value(self, doctype, name, fieldname):
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
						return getattr(doc, fieldname, None)
				return None

			key = (doctype, name, fieldname)
			if key in value_map:
				return value_map[key]
			doc = docs_map.get((doctype, name))
			if doc is None:
				return None
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
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: now

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def test_issue_download_grant_supports_canonical_ref(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.audit.events", "ifitwala_drive.services.files.access")
	drive_file = FakeDoc(
		{
			"name": "DF-0001",
			"canonical_ref": "drv:ORG-0001:DF-0001",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0001",
			"storage_backend": "local",
			"storage_object_key": "files/ab/cd/object.docx",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	file_doc = FakeDoc(
		{"name": "FILE-0001", "file_url": "/private/files/ifitwala_drive/files/ab/cd/object.docx"}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0001"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("File", "FILE-0001"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "files/ab/cd/object.docx"
			assert file_url == "/private/files/ifitwala_drive/files/ab/cd/object.docx"
			assert filename is None
			return {"grant_type": "private_url", "url": file_url}

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Preview grant should not be issued in this test.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_download_grant_service({"canonical_ref": "drv:ORG-0001:DF-0001"})

	assert response == {
		"grant_type": "private_url",
		"url": "/private/files/ifitwala_drive/files/ab/cd/object.docx",
		"expires_on": "2026-03-19 10:10:00",
	}


def test_issue_preview_grant_requires_ready_preview(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0002",
			"status": "active",
			"preview_status": "pending",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0002",
			"storage_backend": "gcs",
			"storage_object_key": "files/ef/gh/object.pdf",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	file_doc = FakeDoc(
		{"name": "FILE-0002", "file_url": "https://storage.ifitwala.invalid/object/files/ef/gh/object.pdf"}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0002"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("File", "FILE-0002"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Preview grant should not be called when preview is pending.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.issue_preview_grant_service({"drive_file_id": "DF-0002"})
	except RuntimeError as exc:
		assert "preview status: pending" in str(exc)
	else:
		raise AssertionError("Expected preview grant issuance to fail for pending preview.")


def test_issue_download_grant_rejects_blocked_file(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0003",
			"status": "blocked",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0003",
			"storage_backend": "gcs",
			"storage_object_key": "files/ij/kl/object.pdf",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	file_doc = FakeDoc(
		{"name": "FILE-0003", "file_url": "https://storage.ifitwala.invalid/object/files/ij/kl/object.pdf"}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0003"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("File", "FILE-0003"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Blocked files must not reach storage grant issuance.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Blocked files must not reach storage grant issuance.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.issue_download_grant_service({"drive_file_id": "DF-0003"})
	except RuntimeError as exc:
		assert "status: blocked" in str(exc)
	else:
		raise AssertionError("Expected blocked file to be rejected for download grant issuance.")


def test_issue_preview_grant_uses_ready_derivative_when_present(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0004",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0004",
			"current_version": "DFV-0004",
			"display_name": "policy.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.png",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0004",
			"drive_file": "DF-0004",
			"mime_type": "image/png",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0004", "file_url": "https://storage.ifitwala.invalid/original/policy.png"}
	)
	derivative_doc = FakeDoc(
		{
			"name": "DFD-0001",
			"drive_file": "DF-0004",
			"drive_file_version": "DFV-0004",
			"derivative_role": "viewer_preview",
			"status": "ready",
			"storage_backend": "gcs",
			"storage_object_key": "derivatives/policy/viewer-preview.webp",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0004"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0004"): version_doc,
			("File", "FILE-0004"): file_doc,
			("Drive File Derivative", "DFD-0001"): derivative_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "derivatives/policy/viewer-preview.webp"
			assert file_url is None
			assert filename == "policy.png"
			return {"grant_type": "signed_url", "url": "https://preview.invalid/policy.webp"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_preview_grant_service({"drive_file_id": "DF-0004"})

	assert response == {
		"grant_type": "signed_url",
		"url": "https://preview.invalid/policy.webp",
		"expires_on": "2026-03-19 10:10:00",
		"preview_status": "ready",
	}


def test_issue_preview_grant_uses_explicit_thumbnail_derivative_when_requested(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0004",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0004",
			"current_version": "DFV-0004",
			"display_name": "policy.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.png",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0004",
			"drive_file": "DF-0004",
			"mime_type": "image/png",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0004", "file_url": "https://storage.ifitwala.invalid/original/policy.png"}
	)
	thumb_doc = FakeDoc(
		{
			"name": "DFD-0002",
			"drive_file": "DF-0004",
			"drive_file_version": "DFV-0004",
			"derivative_role": "thumb",
			"status": "ready",
			"storage_backend": "gcs",
			"storage_object_key": "derivatives/policy/thumb.webp",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0004"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0004"): version_doc,
			("File", "FILE-0004"): file_doc,
			("Drive File Derivative", "DFD-0002"): thumb_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "derivatives/policy/thumb.webp"
			assert file_url is None
			assert filename == "policy.png"
			return {"grant_type": "signed_url", "url": "https://preview.invalid/policy-thumb.webp"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_preview_grant_service({"drive_file_id": "DF-0004", "derivative_role": "thumb"})

	assert response == {
		"grant_type": "signed_url",
		"url": "https://preview.invalid/policy-thumb.webp",
		"expires_on": "2026-03-19 10:10:00",
		"preview_status": "ready",
	}


def test_issue_preview_grant_rejects_stale_explicit_thumbnail_derivative(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0004",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0004",
			"current_version": "DFV-0004",
			"display_name": "policy.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.png",
			"content_hash": "sha256:image-source",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0004",
			"drive_file": "DF-0004",
			"mime_type": "image/png",
			"content_hash": "sha256:image-source",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0004", "file_url": "https://storage.ifitwala.invalid/original/policy.png"}
	)
	thumb_doc = FakeDoc(
		{
			"name": "DFD-0002",
			"drive_file": "DF-0004",
			"drive_file_version": "DFV-0004",
			"derivative_role": "thumb",
			"status": "ready",
			"storage_backend": "gcs",
			"storage_object_key": "derivatives/policy/thumb.webp",
			"source_hash": "sha256:legacy-thumb-spec",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0004"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0004"): version_doc,
			("File", "FILE-0004"): file_doc,
			("Drive File Derivative", "DFD-0002"): thumb_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Preview grant should not be issued when the thumb is stale.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.issue_preview_grant_service({"drive_file_id": "DF-0004", "derivative_role": "thumb"})
	except RuntimeError as exc:
		assert "ready derivative: thumb" in str(exc)
	else:
		raise AssertionError("Expected stale thumbnail derivative preview grant issuance to fail.")


def test_issue_preview_grant_requeues_missing_explicit_thumbnail_derivative(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0009",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0009",
			"file": "FILE-0009",
			"current_version": "DFV-0009",
			"display_name": "avatar.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/avatar.png",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0009"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0009",
			"drive_file": "DF-0009",
			"mime_type": "image/png",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0009", "file_url": "https://storage.ifitwala.invalid/original/avatar.png"}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0009"): drive_file,
			("Task Submission", "TSUB-0009"): task_submission,
			("Drive File Version", "DFV-0009"): version_doc,
			("File", "FILE-0009"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")
	sync_calls = []

	monkeypatch.setattr(
		module,
		"sync_preview_pipeline_for_current_version",
		lambda *, drive_file_doc, mime_type: (
			sync_calls.append((drive_file_doc.name, mime_type))
			or {"preview_status": "ready", "derivative_ids": [], "drive_processing_job_id": "DPJ-0099"}
		),
	)

	try:
		module.issue_preview_grant_service({"drive_file_id": "DF-0009", "derivative_role": "thumb"})
	except RuntimeError as exc:
		assert "ready derivative: thumb" in str(exc)
	else:
		raise AssertionError("Expected missing explicit thumbnail derivative preview grant issuance to fail.")

	assert sync_calls == [("DF-0009", "image/png")]


def test_request_preview_derivatives_repairs_missing_current_version_before_sync(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0011",
			"status": "active",
			"preview_status": "pending",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0011",
			"file": "FILE-0011",
			"current_version": None,
			"display_name": "avatar.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/avatar.png",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0011"})
	file_doc = FakeDoc(
		{"name": "FILE-0011", "file_url": "https://storage.ifitwala.invalid/original/avatar.png"}
	)
	version_doc = FakeDoc(
		{
			"name": "DFV-0011",
			"drive_file": "DF-0011",
			"mime_type": "image/png",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0011"): drive_file,
			("Task Submission", "TSUB-0011"): task_submission,
			("Drive File Version", "DFV-0011"): version_doc,
			("File", "FILE-0011"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")
	sync_calls = []
	repair_calls = []

	monkeypatch.setattr(
		module,
		"ensure_current_drive_file_version",
		lambda *, drive_file_doc: (
			repair_calls.append(drive_file_doc.name)
			or setattr(drive_file_doc, "current_version", "DFV-0011")
			or "DFV-0011"
		),
	)
	monkeypatch.setattr(
		module,
		"sync_preview_pipeline_for_current_version",
		lambda *, drive_file_doc, mime_type: (
			sync_calls.append((drive_file_doc.name, mime_type))
			or {"preview_status": "pending", "derivative_ids": [], "drive_processing_job_id": "DPJ-0011"}
		),
	)

	response = module.request_preview_derivatives_for_doc(
		doc=drive_file,
		payload={"derivative_roles": ["thumb"]},
	)

	assert repair_calls == ["DF-0011"]
	assert sync_calls == [("DF-0011", "image/png")]
	assert response == {
		"drive_file_id": "DF-0011",
		"current_version": "DFV-0011",
		"preview_status": "pending",
		"requested": True,
		"derivative_roles": ["thumb"],
	}


def test_issue_preview_grant_allows_ready_explicit_derivative_while_primary_preview_is_pending(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0010",
			"status": "active",
			"preview_status": "pending",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0010",
			"file": "FILE-0010",
			"current_version": "DFV-0010",
			"display_name": "avatar.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/avatar.png",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0010"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0010",
			"drive_file": "DF-0010",
			"mime_type": "image/png",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0010", "file_url": "https://storage.ifitwala.invalid/original/avatar.png"}
	)
	card_doc = FakeDoc(
		{
			"name": "DFD-0010",
			"drive_file": "DF-0010",
			"drive_file_version": "DFV-0010",
			"derivative_role": "card",
			"status": "ready",
			"storage_backend": "gcs",
			"storage_object_key": "derivatives/avatar/card.webp",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0010"): drive_file,
			("Task Submission", "TSUB-0010"): task_submission,
			("Drive File Version", "DFV-0010"): version_doc,
			("File", "FILE-0010"): file_doc,
			("Drive File Derivative", "DFD-0010"): card_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")
	sync_calls = []
	ready_card = {
		"name": "DFD-0010",
		"derivative_role": "card",
		"status": "ready",
		"storage_backend": "gcs",
		"storage_object_key": "derivatives/avatar/card.webp",
		"mime_type": "image/webp",
	}

	monkeypatch.setattr(
		module,
		"sync_preview_pipeline_for_current_version",
		lambda *, drive_file_doc, mime_type: (
			sync_calls.append((drive_file_doc.name, mime_type))
			or {
				"preview_status": "pending",
				"derivative_ids": ["DFD-0010"],
				"drive_processing_job_id": "DPJ-0010",
			}
		),
	)
	monkeypatch.setattr(module, "resolve_ready_preview_derivative", lambda **kwargs: ready_card)
	monkeypatch.setattr(
		module,
		"resolve_ready_preview_derivative_state",
		lambda **kwargs: {
			"state": "ready",
			"derivative": ready_card,
			"expected_source_hash": None,
			"resolved_source_hash": None,
		},
	)

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "derivatives/avatar/card.webp"
			assert file_url is None
			assert filename == "avatar.png"
			return {"grant_type": "signed_url", "url": "https://preview.invalid/avatar-card.webp"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_preview_grant_service({"drive_file_id": "DF-0010", "derivative_role": "card"})

	assert sync_calls == [("DF-0010", "image/png")]
	assert response == {
		"grant_type": "signed_url",
		"url": "https://preview.invalid/avatar-card.webp",
		"expires_on": "2026-03-19 10:10:00",
		"preview_status": "pending",
	}


def test_issue_preview_grant_uses_ready_pdf_first_page_derivative(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0006",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0006",
			"current_version": "DFV-0006",
			"display_name": "policy.pdf",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.pdf",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0006",
			"drive_file": "DF-0006",
			"mime_type": "application/pdf",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0006", "file_url": "https://storage.ifitwala.invalid/original/policy.pdf"}
	)
	derivative_doc = FakeDoc(
		{
			"name": "DFD-0006",
			"drive_file": "DF-0006",
			"drive_file_version": "DFV-0006",
			"derivative_role": "pdf_page_1",
			"status": "ready",
			"storage_backend": "gcs",
			"storage_object_key": "derivatives/policy/pdf-page-1.jpg",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0006"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0006"): version_doc,
			("File", "FILE-0006"): file_doc,
			("Drive File Derivative", "DFD-0006"): derivative_doc,
		}
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "derivatives/policy/pdf-page-1.jpg"
			assert file_url is None
			assert filename == "policy.pdf"
			return {"grant_type": "signed_url", "url": "https://preview.invalid/policy-page-1.jpg"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_preview_grant_service({"drive_file_id": "DF-0006"})

	assert response == {
		"grant_type": "signed_url",
		"url": "https://preview.invalid/policy-page-1.jpg",
		"expires_on": "2026-03-19 10:10:00",
		"preview_status": "ready",
	}


def test_issue_preview_grant_uses_explicit_pdf_card_derivative_when_requested(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0008",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0008",
			"current_version": "DFV-0008",
			"display_name": "policy.pdf",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.pdf",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0008",
			"drive_file": "DF-0008",
			"mime_type": "application/pdf",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0008", "file_url": "https://storage.ifitwala.invalid/original/policy.pdf"}
	)
	derivative_doc = FakeDoc(
		{
			"name": "DFD-0008",
			"drive_file": "DF-0008",
			"drive_file_version": "DFV-0008",
			"derivative_role": "pdf_card",
			"status": "ready",
			"storage_backend": "gcs",
			"storage_object_key": "derivatives/policy/pdf-card.jpg",
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0008"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0008"): version_doc,
			("File", "FILE-0008"): file_doc,
			("Drive File Derivative", "DFD-0008"): derivative_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "derivatives/policy/pdf-card.jpg"
			assert file_url is None
			assert filename == "policy.pdf"
			return {"grant_type": "signed_url", "url": "https://preview.invalid/policy-card.jpg"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_preview_grant_service({"drive_file_id": "DF-0008", "derivative_role": "pdf_card"})

	assert response == {
		"grant_type": "signed_url",
		"url": "https://preview.invalid/policy-card.jpg",
		"expires_on": "2026-03-19 10:10:00",
		"preview_status": "ready",
	}


def test_issue_preview_grant_falls_back_to_original_object_for_unsupported_preview_mime(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0005",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0005",
			"current_version": "DFV-0005",
			"display_name": "policy.txt",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.txt",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0005",
			"drive_file": "DF-0005",
			"mime_type": "text/plain",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0005", "file_url": "https://storage.ifitwala.invalid/original/policy.txt"}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0005"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0005"): version_doc,
			("File", "FILE-0005"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "files/original/policy.txt"
			assert file_url == "https://storage.ifitwala.invalid/original/policy.txt"
			assert filename == "policy.txt"
			return {"grant_type": "signed_url", "url": "https://preview.invalid/original.txt"}

	monkeypatch.setattr(module, "_ensure_preview_pipeline_requested", lambda *, doc, payload=None: False)
	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_preview_grant_service({"drive_file_id": "DF-0005"})

	assert response == {
		"grant_type": "signed_url",
		"url": "https://preview.invalid/original.txt",
		"expires_on": "2026-03-19 10:10:00",
		"preview_status": "ready",
	}


def test_issue_preview_grant_rejects_missing_explicit_derivative(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.audit.events",
		"ifitwala_drive.services.files.derivatives",
		"ifitwala_drive.services.files.access",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-0007",
			"status": "active",
			"preview_status": "ready",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"file": "FILE-0007",
			"current_version": "DFV-0007",
			"display_name": "policy.png",
			"storage_backend": "gcs",
			"storage_object_key": "files/original/policy.png",
		}
	)
	task_submission = FakeDoc({"name": "TSUB-0001"})
	version_doc = FakeDoc(
		{
			"name": "DFV-0007",
			"drive_file": "DF-0007",
			"mime_type": "image/png",
		}
	)
	file_doc = FakeDoc(
		{"name": "FILE-0007", "file_url": "https://storage.ifitwala.invalid/original/policy.png"}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0007"): drive_file,
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive File Version", "DFV-0007"): version_doc,
			("File", "FILE-0007"): file_doc,
		},
	)
	module = _load_module("ifitwala_drive.services.files.access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Preview grant should not be issued without a ready derivative.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.issue_preview_grant_service({"drive_file_id": "DF-0007", "derivative_role": "thumb"})
	except RuntimeError as exc:
		assert "ready derivative: thumb" in str(exc)
	else:
		raise AssertionError("Expected explicit derivative preview grant issuance to fail.")
