from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path
from typing import ClassVar


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeDoc:
	_insert_counters: ClassVar[dict[str, int]] = {}
	_docs_map: ClassVar[dict[tuple[str, str], "FakeDoc"]] = {}

	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.saved = 0
		self.inserted = 0
		self.meta = types.SimpleNamespace(get_label=lambda fieldname: fieldname)

	def get(self, fieldname, default=None):
		return getattr(self, fieldname, default)

	def save(self, ignore_permissions=False):
		self.saved += 1
		doctype = getattr(self, "doctype", None) or self.__class__.__name__
		name = getattr(self, "name", None)
		if doctype and name:
			self._docs_map[(doctype, name)] = self
		return self

	def insert(self, ignore_permissions=False):
		doctype = getattr(self, "doctype", "")
		if not getattr(self, "name", None):
			prefix_map = {
				"Drive Processing Job": "DPJ",
			}
			prefix = prefix_map.get(doctype, "DOC")
			next_value = self._insert_counters.get(prefix, 0) + 1
			self._insert_counters[prefix] = next_value
			self.name = f"{prefix}-{next_value:04d}"
		self.inserted += 1
		self._docs_map[(doctype, self.name)] = self
		return self


def _match_filter(row: dict[str, object], fieldname: str, condition) -> bool:
	if isinstance(condition, list) and len(condition) == 2:
		operator, value = condition
		current = row.get(fieldname)
		if operator == "like":
			pattern = str(value).rstrip("%")
			return str(current or "").startswith(pattern)
		if operator == "in":
			return current in set(value)
	return row.get(fieldname) == condition


def _install_fake_frappe(
	*, file_rows, drive_rows, settings_doc, site_root: str, existing_job_rows=None, extra_docs=None
):
	existing_job_rows = existing_job_rows or []
	extra_docs = extra_docs or {}
	FakeDoc._insert_counters = {}
	FakeDoc._docs_map = {
		("Drive Storage Settings", "Drive Storage Settings"): settings_doc,
	}
	FakeDoc._docs_map.update(extra_docs)
	for row in drive_rows:
		doc = FakeDoc({"doctype": "Drive File", **row})
		FakeDoc._docs_map[("Drive File", row["name"])] = doc
	for row in file_rows:
		doc = FakeDoc({"doctype": "File", **row})
		FakeDoc._docs_map[("File", row["name"])] = doc
	for row in existing_job_rows:
		doc = FakeDoc({"doctype": "Drive Processing Job", **row})
		FakeDoc._docs_map[("Drive Processing Job", row["name"])] = doc

	enqueue_calls: list[dict[str, object]] = []

	def _throw(message):
		raise RuntimeError(message)

	def _get_doc(arg1, arg2=None):
		if isinstance(arg1, dict):
			return FakeDoc(arg1)
		return FakeDoc._docs_map[(arg1, arg2)]

	def _get_all(doctype, fields=None, filters=None, order_by=None, limit_page_length=None):
		if doctype == "File":
			rows = file_rows
		elif doctype == "Drive File":
			rows = drive_rows
		elif doctype == "Drive Processing Job":
			rows = existing_job_rows + [
				doc.__dict__
				for (candidate_doctype, _), doc in FakeDoc._docs_map.items()
				if candidate_doctype == "Drive Processing Job"
			]
		else:
			rows = []

		results = []
		for row in rows:
			if filters and not all(
				_match_filter(row, fieldname, condition) for fieldname, condition in filters.items()
			):
				continue
			if fields:
				results.append({fieldname: row.get(fieldname) for fieldname in fields})
			else:
				results.append(dict(row))
		if limit_page_length is not None:
			return results[:limit_page_length]
		return results

	class FakeDB:
		def exists(self, doctype, name=None):
			if isinstance(name, dict):
				for (candidate_doctype, candidate_name), doc in FakeDoc._docs_map.items():
					if candidate_doctype != doctype:
						continue
					if all(getattr(doc, fieldname, None) == value for fieldname, value in name.items()):
						return candidate_name
				return False
			return (doctype, name) in FakeDoc._docs_map

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.get_all = _get_all
	frappe.get_doc = _get_doc
	frappe.get_cached_doc = lambda doctype, name=None: (
		settings_doc if doctype == "Drive Storage Settings" else FakeDoc._docs_map[(doctype, name)]
	)
	frappe.get_site_path = lambda *parts: str(Path(site_root, *parts))
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.enqueue = lambda method, **kwargs: enqueue_calls.append({"method": method, **kwargs})
	frappe.db = FakeDB()

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: datetime(2026, 4, 13, 12, 0, 0)

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")
	document.Document = FakeDoc

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return enqueue_calls


def _load_module():
	_purge_modules("ifitwala_drive.services.storage.offload")
	return importlib.import_module("ifitwala_drive.services.storage.offload")


def test_dry_run_attachment_offload_classifies_governed_and_legacy(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-offload-")
	Path(site_root, "private", "files", "ifitwala_drive", "files", "aa", "bb").mkdir(parents=True)
	Path(site_root, "private", "files", "legacy").mkdir(parents=True)
	governed_path = Path(site_root, "private", "files", "ifitwala_drive", "files", "aa", "bb", "essay.pdf")
	legacy_path = Path(site_root, "private", "files", "legacy", "report.pdf")
	governed_path.write_bytes(b"governed")
	legacy_path.write_bytes(b"legacy")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_for_new_writes",
			"batch_size": 20,
			"migrate_public_files": 0,
			"migrate_private_files": 1,
		}
	)
	file_rows = [
		{
			"name": "FILE-0001",
			"file_url": "/private/files/ifitwala_drive/files/aa/bb/essay.pdf",
			"is_private": 1,
			"file_name": "essay.pdf",
		},
		{
			"name": "FILE-0002",
			"file_url": "/private/files/legacy/report.pdf",
			"is_private": 1,
			"file_name": "report.pdf",
		},
	]
	drive_rows = [
		{
			"name": "DF-0001",
			"file": "FILE-0001",
			"storage_backend": "local",
			"storage_object_key": "files/aa/bb/essay.pdf",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
		}
	]
	_install_fake_frappe(
		file_rows=file_rows, drive_rows=drive_rows, settings_doc=settings, site_root=site_root
	)
	module = _load_module()
	monkeypatch.setattr(
		module,
		"resolve_storage_runtime_profile",
		lambda: types.SimpleNamespace(
			backend_name="gcs", storage_mode="gcs_for_new_writes", base_prefix="sites/site-a"
		),
	)

	response = module.dry_run_attachment_offload_service(settings_doc=settings)

	assert response["summary"] == {
		"scanned": 2,
		"eligible": 2,
		"already_remote": 0,
		"missing_local_blob": 0,
		"skipped": 0,
		"governed_drive_files": 1,
		"legacy_file_attachments": 1,
		"private_files": 2,
		"public_files": 0,
	}
	assert response["candidates"][0]["attachment_kind"] == "governed_drive_file"
	assert response["candidates"][0]["destination_object_key"] == "files/aa/bb/essay.pdf"
	assert response["candidates"][1]["attachment_kind"] == "legacy_file_attachment"
	assert (
		response["candidates"][1]["destination_object_key"]
		== "sites/site-a/legacy/private/files/legacy/report.pdf"
	)
	assert settings.migration_status == "dry_run_ready"
	assert settings.saved == 1
	assert '"scanned": 2' in settings.migration_summary_json


def test_enqueue_attachment_offload_jobs_creates_jobs_and_skips_existing(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-offload-")
	Path(site_root, "private", "files", "ifitwala_drive", "files", "aa", "bb").mkdir(parents=True)
	Path(site_root, "private", "files", "legacy").mkdir(parents=True)
	Path(site_root, "private", "files", "ifitwala_drive", "files", "aa", "bb", "essay.pdf").write_bytes(
		b"governed"
	)
	Path(site_root, "private", "files", "legacy", "report.pdf").write_bytes(b"legacy")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_for_new_writes",
			"batch_size": 20,
			"migrate_public_files": 0,
			"migrate_private_files": 1,
		}
	)
	file_rows = [
		{
			"name": "FILE-0001",
			"file_url": "/private/files/ifitwala_drive/files/aa/bb/essay.pdf",
			"is_private": 1,
			"file_name": "essay.pdf",
		},
		{
			"name": "FILE-0002",
			"file_url": "/private/files/legacy/report.pdf",
			"is_private": 1,
			"file_name": "report.pdf",
		},
	]
	drive_rows = [
		{
			"name": "DF-0001",
			"file": "FILE-0001",
			"storage_backend": "local",
			"storage_object_key": "files/aa/bb/essay.pdf",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
		}
	]
	existing_job_rows = [
		{
			"name": "DPJ-EXISTING",
			"file": "FILE-0002",
			"job_type": "offload",
			"status": "queued",
		}
	]
	enqueue_calls = _install_fake_frappe(
		file_rows=file_rows,
		drive_rows=drive_rows,
		settings_doc=settings,
		site_root=site_root,
		existing_job_rows=existing_job_rows,
	)
	module = _load_module()
	monkeypatch.setattr(
		module,
		"resolve_storage_runtime_profile",
		lambda: types.SimpleNamespace(
			backend_name="gcs", storage_mode="gcs_for_new_writes", base_prefix="sites/site-a"
		),
	)

	response = module.enqueue_attachment_offload_jobs_service(settings_doc=settings)

	assert response["summary"] == {
		"eligible": 2,
		"queued": 1,
		"skipped_existing": 1,
	}
	assert len(response["queued_jobs"]) == 1
	queued_job = response["queued_jobs"][0]
	assert queued_job["file_id"] == "FILE-0001"
	assert queued_job["drive_file_id"] == "DF-0001"
	assert enqueue_calls == [
		{
			"method": "ifitwala_drive.services.storage.offload.run_offload_job",
			"queue": "long",
			"job_id": "drive-offload:DPJ-0001",
			"drive_processing_job_id": "DPJ-0001",
		}
	]
	assert settings.migration_status == "queued"


def test_run_offload_job_copies_bytes_and_updates_drive_file(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-offload-")
	source_dir = Path(site_root, "private", "files", "ifitwala_drive", "files", "aa", "bb")
	source_dir.mkdir(parents=True)
	source_path = source_dir / "essay.pdf"
	source_path.write_bytes(b"governed-bytes")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_for_new_writes",
		}
	)
	file_rows = [
		{
			"name": "FILE-0001",
			"file_url": "/private/files/ifitwala_drive/files/aa/bb/essay.pdf",
			"is_private": 1,
			"file_name": "essay.pdf",
		}
	]
	drive_rows = [
		{
			"name": "DF-0001",
			"file": "FILE-0001",
			"storage_backend": "local",
			"storage_object_key": "files/aa/bb/essay.pdf",
			"owner_doctype": "Task Submission",
			"owner_name": "TSUB-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
		}
	]
	_install_fake_frappe(
		file_rows=file_rows, drive_rows=drive_rows, settings_doc=settings, site_root=site_root
	)
	job_doc = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-0001",
			"file": "FILE-0001",
			"drive_file": "DF-0001",
			"status": "queued",
			"payload_json": json.dumps(
				{
					"attachment_kind": "governed_drive_file",
					"source_path": str(source_path),
					"destination_object_key": "sites/site-a/files/aa/bb/essay.pdf",
					"delete_local_after_verification": False,
				},
				sort_keys=True,
			),
		}
	)
	FakeDoc._docs_map[("Drive Processing Job", "DPJ-0001")] = job_doc

	writes: list[dict[str, object]] = []

	class FakeStorage:
		def write_final_object(self, *, object_key: str, content: bytes, mime_type: str | None = None):
			writes.append(
				{
					"object_key": object_key,
					"content": content,
					"mime_type": mime_type,
				}
			)
			return {
				"object_key": object_key,
				"storage_backend": "gcs",
				"file_url": f"https://storage.invalid/{object_key}",
			}

	module = _load_module()
	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	result = module.run_offload_job(drive_processing_job_id="DPJ-0001")

	assert result == {
		"attachment_kind": "governed_drive_file",
		"bytes_copied": 14,
		"source_sha256": hashlib.sha256(b"governed-bytes").hexdigest(),
		"storage_backend": "gcs",
		"destination_object_key": "sites/site-a/files/aa/bb/essay.pdf",
		"destination_file_url": "https://storage.invalid/sites/site-a/files/aa/bb/essay.pdf",
		"cleanup_eligible": False,
		"cleanup_performed": False,
		"drive_file_updated": True,
	}
	assert writes == [
		{
			"object_key": "sites/site-a/files/aa/bb/essay.pdf",
			"content": b"governed-bytes",
			"mime_type": "application/pdf",
		}
	]
	drive_file_doc = FakeDoc._docs_map[("Drive File", "DF-0001")]
	assert drive_file_doc.storage_backend == "gcs"
	assert drive_file_doc.storage_object_key == "sites/site-a/files/aa/bb/essay.pdf"
	assert job_doc.status == "completed"


def test_dry_run_local_prune_blocks_public_and_allows_private(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-prune-")
	private_dir = Path(site_root, "private", "files", "legacy")
	public_dir = Path(site_root, "public", "files", "legacy")
	private_dir.mkdir(parents=True)
	public_dir.mkdir(parents=True)
	(private_dir / "report.pdf").write_bytes(b"private-bytes")
	(public_dir / "cover.jpg").write_bytes(b"public-bytes")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_primary_with_local_fallback",
			"batch_size": 20,
			"migrate_public_files": 1,
			"migrate_private_files": 1,
		}
	)
	file_rows = [
		{
			"name": "FILE-1001",
			"file_url": "/private/files/legacy/report.pdf",
			"is_private": 1,
			"file_name": "report.pdf",
			"attached_to_doctype": "Task Submission",
			"attached_to_name": "TSUB-1001",
		},
		{
			"name": "FILE-1002",
			"file_url": "/files/legacy/cover.jpg",
			"is_private": 0,
			"file_name": "cover.jpg",
			"attached_to_doctype": "Task Submission",
			"attached_to_name": "TSUB-1002",
		},
	]
	existing_job_rows = [
		{
			"name": "DPJ-OFFLOAD-1",
			"file": "FILE-1001",
			"job_type": "offload",
			"status": "completed",
			"payload_json": json.dumps(
				{
					"source_path": str(private_dir / "report.pdf"),
					"destination_object_key": "sites/site-a/legacy/private/files/legacy/report.pdf",
				},
				sort_keys=True,
			),
			"result_json": json.dumps({"storage_backend": "gcs", "bytes_copied": 13}, sort_keys=True),
		},
		{
			"name": "DPJ-OFFLOAD-2",
			"file": "FILE-1002",
			"job_type": "offload",
			"status": "completed",
			"payload_json": json.dumps(
				{
					"source_path": str(public_dir / "cover.jpg"),
					"destination_object_key": "sites/site-a/legacy/public/files/legacy/cover.jpg",
				},
				sort_keys=True,
			),
			"result_json": json.dumps({"storage_backend": "gcs", "bytes_copied": 12}, sort_keys=True),
		},
	]
	_install_fake_frappe(
		file_rows=file_rows,
		drive_rows=[],
		settings_doc=settings,
		site_root=site_root,
		existing_job_rows=existing_job_rows,
		extra_docs={
			("Task Submission", "TSUB-1001"): FakeDoc({"doctype": "Task Submission", "name": "TSUB-1001"}),
			("Task Submission", "TSUB-1002"): FakeDoc({"doctype": "Task Submission", "name": "TSUB-1002"}),
		},
	)
	module = _load_module()
	monkeypatch.setattr(
		module,
		"resolve_storage_runtime_profile",
		lambda: types.SimpleNamespace(
			backend_name="gcs", storage_mode="gcs_primary_with_local_fallback", base_prefix="sites/site-a"
		),
	)
	monkeypatch.setattr(
		module,
		"build_canonical_public_file_url",
		lambda *, file_id, storage_backend, object_key: (
			f"/api/method/ifitwala_drive.api.access.redirect_public_file?file_id={file_id}"
		),
	)

	class FakeStorage:
		def read_object_metadata(self, *, object_key: str):
			return {
				"exists": True,
				"size_bytes": 13 if object_key.endswith("report.pdf") else 12,
				"checksum": None,
				"verifiable": True,
			}

		def build_public_object_url(self, *, object_key: str):
			return None

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.dry_run_local_prune_service(settings_doc=settings)

	assert response["summary"] == {
		"scanned": 2,
		"eligible": 2,
		"blocked": 0,
		"private_files": 1,
		"public_files": 1,
	}
	assert response["candidates"][0]["status"] == "eligible"
	assert response["candidates"][1]["status"] == "eligible"
	assert (
		response["candidates"][1]["canonical_file_url"]
		== "/api/method/ifitwala_drive.api.access.redirect_public_file?file_id=FILE-1002"
	)


def test_enqueue_local_prune_jobs_creates_jobs_and_skips_existing(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-prune-")
	private_dir = Path(site_root, "private", "files", "legacy")
	private_dir.mkdir(parents=True)
	(private_dir / "report-a.pdf").write_bytes(b"private-a")
	(private_dir / "report-b.pdf").write_bytes(b"private-b")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_primary_with_local_fallback",
			"batch_size": 20,
			"migrate_public_files": 0,
			"migrate_private_files": 1,
		}
	)
	file_rows = [
		{
			"name": "FILE-2001",
			"file_url": "/private/files/legacy/report-a.pdf",
			"is_private": 1,
			"file_name": "report-a.pdf",
			"attached_to_doctype": "Task Submission",
			"attached_to_name": "TSUB-2001",
		},
		{
			"name": "FILE-2002",
			"file_url": "/private/files/legacy/report-b.pdf",
			"is_private": 1,
			"file_name": "report-b.pdf",
			"attached_to_doctype": "Task Submission",
			"attached_to_name": "TSUB-2002",
		},
	]
	existing_job_rows = [
		{
			"name": "DPJ-OFFLOAD-2001",
			"file": "FILE-2001",
			"job_type": "offload",
			"status": "completed",
			"payload_json": json.dumps(
				{
					"source_path": str(private_dir / "report-a.pdf"),
					"destination_object_key": "sites/site-a/legacy/private/files/legacy/report-a.pdf",
				},
				sort_keys=True,
			),
			"result_json": json.dumps({"storage_backend": "gcs", "bytes_copied": 9}, sort_keys=True),
		},
		{
			"name": "DPJ-OFFLOAD-2002",
			"file": "FILE-2002",
			"job_type": "offload",
			"status": "completed",
			"payload_json": json.dumps(
				{
					"source_path": str(private_dir / "report-b.pdf"),
					"destination_object_key": "sites/site-a/legacy/private/files/legacy/report-b.pdf",
				},
				sort_keys=True,
			),
			"result_json": json.dumps({"storage_backend": "gcs", "bytes_copied": 9}, sort_keys=True),
		},
		{
			"name": "DPJ-PRUNE-EXISTING",
			"file": "FILE-2002",
			"job_type": "prune_local",
			"status": "queued",
		},
	]
	enqueue_calls = _install_fake_frappe(
		file_rows=file_rows,
		drive_rows=[],
		settings_doc=settings,
		site_root=site_root,
		existing_job_rows=existing_job_rows,
		extra_docs={
			("Task Submission", "TSUB-2001"): FakeDoc({"doctype": "Task Submission", "name": "TSUB-2001"}),
			("Task Submission", "TSUB-2002"): FakeDoc({"doctype": "Task Submission", "name": "TSUB-2002"}),
		},
	)
	module = _load_module()
	monkeypatch.setattr(
		module,
		"resolve_storage_runtime_profile",
		lambda: types.SimpleNamespace(
			backend_name="gcs", storage_mode="gcs_primary_with_local_fallback", base_prefix="sites/site-a"
		),
	)

	class FakeStorage:
		def read_object_metadata(self, *, object_key: str):
			return {
				"exists": True,
				"size_bytes": 9,
				"checksum": None,
				"verifiable": True,
			}

		def build_public_object_url(self, *, object_key: str):
			return None

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	response = module.enqueue_local_prune_jobs_service(settings_doc=settings)

	assert response["summary"] == {
		"eligible": 2,
		"queued": 1,
		"skipped_existing": 1,
	}
	assert response["queued_jobs"][0]["file_id"] == "FILE-2001"
	assert enqueue_calls == [
		{
			"method": "ifitwala_drive.services.storage.offload.run_prune_job",
			"queue": "long",
			"job_id": "drive-prune:DPJ-0001",
			"drive_processing_job_id": "DPJ-0001",
		}
	]


def test_run_prune_job_deletes_local_file_after_remote_verification(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-prune-")
	private_dir = Path(site_root, "private", "files", "legacy")
	private_dir.mkdir(parents=True)
	source_path = private_dir / "report.pdf"
	source_path.write_bytes(b"private-bytes")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_primary_with_local_fallback",
		}
	)
	file_rows = [
		{
			"name": "FILE-3001",
			"file_url": "/private/files/legacy/report.pdf",
			"is_private": 1,
			"file_name": "report.pdf",
			"attached_to_doctype": "Task Submission",
			"attached_to_name": "TSUB-3001",
		}
	]
	_install_fake_frappe(
		file_rows=file_rows,
		drive_rows=[],
		settings_doc=settings,
		site_root=site_root,
		extra_docs={
			("Task Submission", "TSUB-3001"): FakeDoc({"doctype": "Task Submission", "name": "TSUB-3001"})
		},
	)
	job_doc = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-3001",
			"file": "FILE-3001",
			"status": "queued",
			"payload_json": json.dumps(
				{
					"source_path": str(source_path),
					"destination_object_key": "sites/site-a/legacy/private/files/legacy/report.pdf",
					"storage_backend": "gcs",
					"verified_remote_size_bytes": 13,
				},
				sort_keys=True,
			),
		}
	)
	FakeDoc._docs_map[("Drive Processing Job", "DPJ-3001")] = job_doc
	module = _load_module()

	class FakeStorage:
		def read_object_metadata(self, *, object_key: str):
			return {
				"exists": True,
				"size_bytes": 13,
				"checksum": None,
				"verifiable": True,
			}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	result = module.run_prune_job(drive_processing_job_id="DPJ-3001")

	assert result["cleanup_performed"] is True
	assert result["cleanup_blocked_reason"] is None
	assert not source_path.exists()
	assert job_doc.status == "completed"


def test_run_prune_job_rewrites_public_file_url_before_delete(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-prune-")
	public_dir = Path(site_root, "public", "files", "legacy")
	public_dir.mkdir(parents=True)
	source_path = public_dir / "cover.jpg"
	source_path.write_bytes(b"public-bytes")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_primary_with_local_fallback",
		}
	)
	file_rows = [
		{
			"name": "FILE-3501",
			"file_url": "/files/legacy/cover.jpg",
			"is_private": 0,
			"file_name": "cover.jpg",
		}
	]
	_install_fake_frappe(
		file_rows=file_rows,
		drive_rows=[],
		settings_doc=settings,
		site_root=site_root,
	)
	job_doc = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-3501",
			"file": "FILE-3501",
			"status": "queued",
			"payload_json": json.dumps(
				{
					"source_path": str(source_path),
					"destination_object_key": "sites/site-a/legacy/public/files/legacy/cover.jpg",
					"storage_backend": "gcs",
					"verified_remote_size_bytes": 12,
				},
				sort_keys=True,
			),
		}
	)
	FakeDoc._docs_map[("Drive Processing Job", "DPJ-3501")] = job_doc
	module = _load_module()

	class FakeStorage:
		def read_object_metadata(self, *, object_key: str):
			return {
				"exists": True,
				"size_bytes": 12,
				"checksum": None,
				"verifiable": True,
			}

		def build_public_object_url(self, *, object_key: str):
			return "https://cdn.invalid/legacy/cover.jpg"

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())
	monkeypatch.setattr(
		module,
		"build_canonical_public_file_url",
		lambda *, file_id, storage_backend, object_key: "https://cdn.invalid/legacy/cover.jpg",
	)

	result = module.run_prune_job(drive_processing_job_id="DPJ-3501")

	assert result["cleanup_performed"] is True
	assert result["cleanup_blocked_reason"] is None
	assert not source_path.exists()
	file_doc = FakeDoc._docs_map[("File", "FILE-3501")]
	assert file_doc.file_url == "https://cdn.invalid/legacy/cover.jpg"
	assert job_doc.status == "completed"


def test_run_offload_job_prunes_private_local_file_when_enabled(monkeypatch):
	site_root = tempfile.mkdtemp(prefix="ifitwala-drive-offload-")
	source_dir = Path(site_root, "private", "files", "legacy")
	source_dir.mkdir(parents=True)
	source_path = source_dir / "report.pdf"
	source_path.write_bytes(b"private-bytes")

	settings = FakeDoc(
		{
			"doctype": "Drive Storage Settings",
			"name": "Drive Storage Settings",
			"enabled": 1,
			"backend_name": "gcs",
			"storage_mode": "gcs_primary_with_local_fallback",
		}
	)
	file_rows = [
		{
			"name": "FILE-4001",
			"file_url": "/private/files/legacy/report.pdf",
			"is_private": 1,
			"file_name": "report.pdf",
			"attached_to_doctype": "Task Submission",
			"attached_to_name": "TSUB-4001",
		}
	]
	_install_fake_frappe(
		file_rows=file_rows,
		drive_rows=[],
		settings_doc=settings,
		site_root=site_root,
		extra_docs={
			("Task Submission", "TSUB-4001"): FakeDoc({"doctype": "Task Submission", "name": "TSUB-4001"})
		},
	)
	job_doc = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-4001",
			"file": "FILE-4001",
			"status": "queued",
			"payload_json": json.dumps(
				{
					"attachment_kind": "legacy_file_attachment",
					"source_path": str(source_path),
					"destination_object_key": "sites/site-a/legacy/private/files/legacy/report.pdf",
					"delete_local_after_verification": True,
				},
				sort_keys=True,
			),
		}
	)
	FakeDoc._docs_map[("Drive Processing Job", "DPJ-4001")] = job_doc
	module = _load_module()

	class FakeStorage:
		def write_final_object(self, *, object_key: str, content: bytes, mime_type: str | None = None):
			return {
				"object_key": object_key,
				"storage_backend": "gcs",
				"file_url": f"https://storage.invalid/{object_key}",
			}

		def read_object_metadata(self, *, object_key: str):
			return {
				"exists": True,
				"size_bytes": 13,
				"checksum": None,
				"verifiable": True,
			}

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())

	result = module.run_offload_job(drive_processing_job_id="DPJ-4001")

	assert result["cleanup_eligible"] is True
	assert result["cleanup_performed"] is True
	assert result["cleanup_blocked_reason"] is None
	assert not source_path.exists()
