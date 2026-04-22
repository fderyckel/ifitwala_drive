from __future__ import annotations

import importlib
import json
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeDoc:
	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.permission_checks: list[str | None] = []

	def check_permission(self, permission_type=None):
		self.permission_checks.append(permission_type)
		return None


def _install_fake_frappe(*, docs_map=None, file_rows=None, drive_rows=None, job_rows=None, site_root=None):
	docs_map = docs_map or {}
	file_rows = file_rows or []
	drive_rows = drive_rows or []
	job_rows = job_rows or []
	site_root = site_root or tempfile.mkdtemp(prefix="ifitwala-drive-legacy-")

	class FakeDB:
		def exists(self, doctype, name=None):
			if isinstance(name, dict):
				for candidate_doctype, candidate_name in docs_map:
					if candidate_doctype != doctype:
						continue
					doc = docs_map[(candidate_doctype, candidate_name)]
					if all(getattr(doc, fieldname, None) == value for fieldname, value in name.items()):
						return candidate_name
				return False
			return (doctype, name) in docs_map

	def _throw(message, exc=None):
		raise RuntimeError(message)

	def _get_doc(doctype, name=None):
		return docs_map[(doctype, name)]

	def _get_all(doctype, fields=None, filters=None, order_by=None, limit_page_length=None):
		rows = {
			"File": file_rows,
			"Drive File": drive_rows,
			"Drive Processing Job": job_rows,
		}.get(doctype, [])
		results = []
		for row in rows:
			if filters and not all(
				_match_filter(row, fieldname, condition) for fieldname, condition in filters.items()
			):
				continue
			results.append({fieldname: row.get(fieldname) for fieldname in fields or row.keys()})
		if limit_page_length is not None:
			return results[:limit_page_length]
		return results

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.db = FakeDB()
	frappe.get_doc = _get_doc
	frappe.get_all = _get_all
	frappe.get_site_path = lambda *parts: str(Path(site_root, *parts))
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.local = types.SimpleNamespace(
		request=types.SimpleNamespace(path="", method="GET"),
		response={},
	)

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: datetime(2026, 4, 13, 12, 0, 0)

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	return frappe


def _match_filter(row: dict[str, object], fieldname: str, condition) -> bool:
	if isinstance(condition, list) and len(condition) == 2:
		operator, value = condition
		current = row.get(fieldname)
		if operator == "in":
			return current in set(value)
		if operator == "like":
			pattern = str(value).rstrip("%")
			return str(current or "").startswith(pattern)
	return row.get(fieldname) == condition


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def test_resolve_legacy_file_grant_uses_completed_offload_job_for_private_file(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-legacy-")
	owner_doc = FakeDoc({"name": "TSUB-0001"})
	frappe = _install_fake_frappe(
		docs_map={("Task Submission", "TSUB-0001"): owner_doc},
		file_rows=[
			{
				"name": "FILE-0001",
				"file_url": "/private/files/legacy/report.pdf",
				"file_name": "report.pdf",
				"is_private": 1,
				"attached_to_doctype": "Task Submission",
				"attached_to_name": "TSUB-0001",
			}
		],
		job_rows=[
			{
				"name": "DPJ-0001",
				"file": "FILE-0001",
				"job_type": "offload",
				"status": "completed",
				"payload_json": json.dumps(
					{"destination_object_key": "sites/site-a/legacy/private/files/legacy/report.pdf"},
					sort_keys=True,
				),
				"result_json": json.dumps({"storage_backend": "gcs"}, sort_keys=True),
			}
		],
		site_root=site_root,
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "sites/site-a/legacy/private/files/legacy/report.pdf"
			assert file_url is None
			assert filename == "report.pdf"
			return {"grant_type": "signed_url", "url": "https://signed.invalid/report.pdf"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.resolve_legacy_file_grant("/private/files/legacy/report.pdf")

	assert response == {
		"file_id": "FILE-0001",
		"file_url": "/private/files/legacy/report.pdf",
		"is_private": True,
		"grant_type": "signed_url",
		"url": "https://signed.invalid/report.pdf",
		"expires_on": "2026-04-13 12:10:00",
		"storage_backend": "gcs",
		"object_key": "sites/site-a/legacy/private/files/legacy/report.pdf",
		"source": "offload_job",
	}
	assert owner_doc.permission_checks == ["read"]
	assert not Path(site_root, "private", "files", "legacy", "report.pdf").exists()
	assert frappe.local.response == {}


def test_resolve_legacy_file_grant_prefers_drive_file_metadata(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-legacy-")
	owner_doc = FakeDoc({"name": "TSUB-0002"})
	_install_fake_frappe(
		docs_map={("Task Submission", "TSUB-0002"): owner_doc},
		file_rows=[
			{
				"name": "FILE-0002",
				"file_url": "/private/files/ifitwala_drive/files/aa/bb/essay.pdf",
				"file_name": "essay.pdf",
				"is_private": 1,
				"attached_to_doctype": "Task Submission",
				"attached_to_name": "TSUB-0002",
			}
		],
		drive_rows=[
			{
				"name": "DF-0002",
				"file": "FILE-0002",
				"storage_backend": "gcs",
				"storage_object_key": "sites/site-a/files/aa/bb/essay.pdf",
			}
		],
		site_root=site_root,
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert object_key == "sites/site-a/files/aa/bb/essay.pdf"
			return {"grant_type": "signed_url", "url": "https://signed.invalid/essay.pdf"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.resolve_legacy_file_grant("/private/files/ifitwala_drive/files/aa/bb/essay.pdf")

	assert response["source"] == "drive_file"
	assert response["object_key"] == "sites/site-a/files/aa/bb/essay.pdf"
	assert owner_doc.permission_checks == ["read"]


def test_resolve_legacy_file_grant_returns_none_when_local_blob_still_exists(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-legacy-")
	local_path = Path(site_root, "private", "files", "legacy")
	local_path.mkdir(parents=True)
	(local_path / "report.pdf").write_bytes(b"still-local")
	_install_fake_frappe(
		docs_map={("Task Submission", "TSUB-0003"): FakeDoc({"name": "TSUB-0003"})},
		file_rows=[
			{
				"name": "FILE-0003",
				"file_url": "/private/files/legacy/report.pdf",
				"file_name": "report.pdf",
				"is_private": 1,
				"attached_to_doctype": "Task Submission",
				"attached_to_name": "TSUB-0003",
			}
		],
		site_root=site_root,
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")
	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: None)

	assert module.resolve_legacy_file_grant("/private/files/legacy/report.pdf") is None


def test_resolve_legacy_file_grant_fails_closed_without_owner_document(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	_install_fake_frappe(
		file_rows=[
			{
				"name": "FILE-0004",
				"file_url": "/private/files/legacy/report.pdf",
				"file_name": "report.pdf",
				"is_private": 1,
				"attached_to_doctype": "",
				"attached_to_name": "",
			}
		],
		job_rows=[
			{
				"name": "DPJ-0004",
				"file": "FILE-0004",
				"job_type": "offload",
				"status": "completed",
				"payload_json": json.dumps(
					{"destination_object_key": "sites/site-a/legacy/private/files/legacy/report.pdf"},
					sort_keys=True,
				),
				"result_json": json.dumps({"storage_backend": "gcs"}, sort_keys=True),
			}
		],
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")
	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: None)

	try:
		module.resolve_legacy_file_grant("/private/files/legacy/report.pdf")
	except RuntimeError as exc:
		assert "authorized owning document" in str(exc)
	else:
		raise AssertionError("Expected private migrated file without owner context to fail closed.")


def test_resolve_legacy_file_grant_rejects_local_style_redirects_from_remote_backend(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	_install_fake_frappe(
		docs_map={("Task Submission", "TSUB-0005"): FakeDoc({"name": "TSUB-0005"})},
		file_rows=[
			{
				"name": "FILE-0005",
				"file_url": "/private/files/legacy/report.pdf",
				"file_name": "report.pdf",
				"is_private": 1,
				"attached_to_doctype": "Task Submission",
				"attached_to_name": "TSUB-0005",
			}
		],
		job_rows=[
			{
				"name": "DPJ-0005",
				"file": "FILE-0005",
				"job_type": "offload",
				"status": "completed",
				"payload_json": json.dumps(
					{"destination_object_key": "sites/site-a/legacy/private/files/legacy/report.pdf"},
					sort_keys=True,
				),
				"result_json": json.dumps({"storage_backend": "gcs"}, sort_keys=True),
			}
		],
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")

	class FakeStorage:
		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			return {
				"grant_type": "private_url",
				"url": "/private/files/ifitwala_drive/sites/site-a/legacy/private/files/legacy/report.pdf",
			}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	try:
		module.resolve_legacy_file_grant("/private/files/legacy/report.pdf")
	except RuntimeError as exc:
		assert "cannot issue a remote read grant" in str(exc)
	else:
		raise AssertionError("Expected local-style remote redirect to be rejected.")


def test_before_request_hook_redirects_to_remote_grant(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.request_hooks", "ifitwala_drive.services.files.legacy_access")
	frappe = _install_fake_frappe()
	frappe.local.request.path = "/private/files/legacy/report.pdf"
	frappe.local.request.method = "GET"
	module = _load_module("ifitwala_drive.request_hooks")
	monkeypatch.setattr(
		module,
		"resolve_legacy_file_grant",
		lambda path: {"url": "https://signed.invalid/report.pdf"},
	)

	module.redirect_migrated_legacy_file_requests()

	assert frappe.local.response == {
		"type": "redirect",
		"location": "https://signed.invalid/report.pdf",
		"http_status_code": 302,
	}


def test_resolve_public_file_redirect_prefers_direct_public_object_url(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	_install_fake_frappe(
		file_rows=[
			{
				"name": "FILE-PUB-1",
				"file_url": "/files/legacy/cover.jpg",
				"file_name": "cover.jpg",
				"is_private": 0,
				"attached_to_doctype": "",
				"attached_to_name": "",
			}
		],
		job_rows=[
			{
				"name": "DPJ-PUB-1",
				"file": "FILE-PUB-1",
				"job_type": "offload",
				"status": "completed",
				"payload_json": json.dumps(
					{"destination_object_key": "sites/site-a/legacy/public/files/legacy/cover.jpg"},
					sort_keys=True,
				),
				"result_json": json.dumps({"storage_backend": "gcs"}, sort_keys=True),
			}
		],
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")

	class FakeStorage:
		def build_public_object_url(self, *, object_key: str):
			assert object_key == "sites/site-a/legacy/public/files/legacy/cover.jpg"
			return "https://cdn.invalid/legacy/cover.jpg"

		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			raise AssertionError("Direct public URL should be preferred.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.resolve_public_file_redirect(file_id="FILE-PUB-1")

	assert response == {
		"file_id": "FILE-PUB-1",
		"file_url": "/files/legacy/cover.jpg",
		"url": "https://cdn.invalid/legacy/cover.jpg",
		"grant_type": "public_url",
		"storage_backend": "gcs",
		"object_key": "sites/site-a/legacy/public/files/legacy/cover.jpg",
		"source": "offload_job",
	}


def test_resolve_public_file_redirect_falls_back_to_download_grant(monkeypatch):
	_purge_modules("frappe", "ifitwala_drive.services.files.legacy_access")
	_install_fake_frappe(
		file_rows=[
			{
				"name": "FILE-PUB-2",
				"file_url": "/files/legacy/cover.jpg",
				"file_name": "cover.jpg",
				"is_private": 0,
				"attached_to_doctype": "",
				"attached_to_name": "",
			}
		],
		job_rows=[
			{
				"name": "DPJ-PUB-2",
				"file": "FILE-PUB-2",
				"job_type": "offload",
				"status": "completed",
				"payload_json": json.dumps(
					{"destination_object_key": "sites/site-a/legacy/public/files/legacy/cover.jpg"},
					sort_keys=True,
				),
				"result_json": json.dumps({"storage_backend": "gcs"}, sort_keys=True),
			}
		],
	)
	module = _load_module("ifitwala_drive.services.files.legacy_access")

	class FakeStorage:
		def build_public_object_url(self, *, object_key: str):
			return None

		def issue_download_grant(self, *, object_key, file_url, expires_on, filename=None):
			assert filename == "cover.jpg"
			return {"grant_type": "signed_url", "url": "https://signed.invalid/legacy/cover.jpg"}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.resolve_public_file_redirect(file_id="FILE-PUB-2")

	assert response["url"] == "https://signed.invalid/legacy/cover.jpg"
	assert response["grant_type"] == "signed_url"
	assert response["expires_on"] == "2026-04-13 12:10:00"


def test_api_redirect_public_file_sets_redirect_response(monkeypatch):
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.access",
		"ifitwala_drive.services.files.access",
		"ifitwala_drive.services.files.legacy_access",
	)
	frappe = _install_fake_frappe()
	module = _load_module("ifitwala_drive.api.access")
	monkeypatch.setattr(
		module,
		"resolve_public_file_redirect",
		lambda file_id=None, file_url=None: {"url": "https://cdn.invalid/legacy/cover.jpg"},
	)

	response = module.redirect_public_file(file_id="FILE-PUB-3")

	assert response is None
	assert frappe.local.response == {
		"type": "redirect",
		"location": "https://cdn.invalid/legacy/cover.jpg",
		"http_status_code": 302,
	}
