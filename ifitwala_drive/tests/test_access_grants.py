from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeDoc:
	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def check_permission(self, permission_type=None):
		return None


def _install_fake_frappe(*, exists_map=None, value_map=None, docs_map=None, now=None):
	exists_map = exists_map or {}
	value_map = value_map or {}
	docs_map = docs_map or {}
	now = now or datetime(2026, 3, 19, 10, 0, 0)

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
	_purge_modules("frappe", "ifitwala_drive.services.files.access")
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
		def issue_download_grant(self, *, object_key, file_url, expires_on):
			assert object_key == "files/ab/cd/object.docx"
			assert file_url == "/private/files/ifitwala_drive/files/ab/cd/object.docx"
			return {"grant_type": "private_url", "url": file_url}

		def issue_preview_grant(self, *, object_key, file_url, expires_on):
			raise AssertionError("Preview grant should not be issued in this test.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.issue_download_grant_service({"canonical_ref": "drv:ORG-0001:DF-0001"})

	assert response == {
		"grant_type": "private_url",
		"url": "/private/files/ifitwala_drive/files/ab/cd/object.docx",
		"expires_on": "2026-03-19 10:10:00",
	}


def test_issue_preview_grant_requires_ready_preview(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.access")
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
		def issue_download_grant(self, *, object_key, file_url, expires_on):
			raise AssertionError("Download grant should not be issued in this test.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on):
			raise AssertionError("Preview grant should not be called when preview is pending.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.issue_preview_grant_service({"drive_file_id": "DF-0002"})
	except RuntimeError as exc:
		assert "preview status: pending" in str(exc)
	else:
		raise AssertionError("Expected preview grant issuance to fail for pending preview.")


def test_issue_download_grant_rejects_blocked_file(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.access")
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
		def issue_download_grant(self, *, object_key, file_url, expires_on):
			raise AssertionError("Blocked files must not reach storage grant issuance.")

		def issue_preview_grant(self, *, object_key, file_url, expires_on):
			raise AssertionError("Blocked files must not reach storage grant issuance.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.issue_download_grant_service({"drive_file_id": "DF-0003"})
	except RuntimeError as exc:
		assert "status: blocked" in str(exc)
	else:
		raise AssertionError("Expected blocked file to be rejected for download grant issuance.")
