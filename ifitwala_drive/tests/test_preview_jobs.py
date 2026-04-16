from __future__ import annotations

import importlib
import json
import sys
import types
from datetime import datetime
from typing import ClassVar


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
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
		self.inserted = 0

	def get(self, key, default=None):
		return getattr(self, key, default)

	def save(self, ignore_permissions=False):
		self.saved += 1
		doctype = getattr(self, "doctype", None)
		name = getattr(self, "name", None)
		if doctype and name:
			self._docs_map[(doctype, name)] = self
		return self

	def insert(self, ignore_permissions=False):
		doctype = getattr(self, "doctype", "")
		if not getattr(self, "name", None):
			prefix_map = {
				"Drive File Derivative": "DFD",
				"Drive Processing Job": "DPJ",
			}
			prefix = prefix_map.get(doctype, "DOC")
			next_value = self._insert_counters.get(prefix, 0) + 1
			self._insert_counters[prefix] = next_value
			self.name = f"{prefix}-{next_value:04d}"
		self.inserted += 1
		self._docs_map[(doctype, self.name)] = self
		return self


def _matches(doc, filters: dict[str, object]) -> bool:
	for key, value in filters.items():
		if getattr(doc, key, None) != value:
			return False
	return True


def _install_fake_frappe(*, docs_map=None, now=None):
	docs_map = docs_map or {}
	FakeDoc._docs_map = docs_map
	FakeDoc._insert_counters = {}
	now = now or datetime(2026, 4, 16, 14, 0, 0)
	enqueue_calls: list[dict[str, object]] = []

	class FakeDB:
		def exists(self, doctype, name=None):
			if isinstance(name, dict):
				for candidate_doctype, candidate_name in list(FakeDoc._docs_map):
					if candidate_doctype != doctype:
						continue
					doc = FakeDoc._docs_map[(candidate_doctype, candidate_name)]
					if _matches(doc, name):
						return candidate_name
				return False
			return (doctype, name) in FakeDoc._docs_map

		def get_value(self, doctype, name, fieldname):
			if isinstance(name, dict):
				for candidate_doctype, candidate_name in list(FakeDoc._docs_map):
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

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.db = FakeDB()
	frappe.get_doc = _get_doc
	frappe.DuplicateEntryError = RuntimeError
	frappe.enqueue = lambda method, **kwargs: enqueue_calls.append({"method": method, **kwargs})

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: now

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	return enqueue_calls


def _load_module():
	for module_name in list(sys.modules):
		if module_name == "ifitwala_drive.services.files.derivatives" or module_name.startswith(
			"ifitwala_drive.services.files.derivatives."
		):
			sys.modules.pop(module_name, None)
	return importlib.import_module("ifitwala_drive.services.files.derivatives")


def test_sync_preview_pipeline_enqueues_preview_job_for_supported_image():
	drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0001",
			"file": "FILE-0001",
			"current_version": "DFV-0001",
			"content_hash": "sha256:abc123",
		}
	)
	enqueue_calls = _install_fake_frappe(docs_map={("Drive File", "DF-0001"): drive_file})
	module = _load_module()

	result = module.sync_preview_pipeline_for_current_version(
		drive_file_doc=drive_file,
		mime_type="image/png",
	)

	assert result["preview_status"] == "pending"
	assert result["derivative_ids"] == ["DFD-0001", "DFD-0002"]
	assert result["drive_processing_job_id"] == "DPJ-0001"
	assert enqueue_calls == [
		{
			"method": "ifitwala_drive.services.files.derivatives.run_preview_job",
			"queue": "drive_default",
			"job_id": "drive-preview:DPJ-0001",
			"drive_processing_job_id": "DPJ-0001",
		}
	]

	job_doc = FakeDoc._docs_map[("Drive Processing Job", "DPJ-0001")]
	payload = json.loads(job_doc.payload_json)
	assert payload == {
		"derivative_roles": ["thumb", "viewer_preview"],
		"drive_file_version": "DFV-0001",
		"mime_type": "image/png",
	}


def test_run_preview_job_marks_viewer_and_thumb_ready(monkeypatch):
	drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0001",
			"file": "FILE-0001",
			"current_version": "DFV-0001",
			"preview_status": "pending",
			"storage_backend": "local",
			"storage_object_key": "files/original/image.png",
			"content_hash": "sha256:source",
		}
	)
	version = FakeDoc(
		{
			"doctype": "Drive File Version",
			"name": "DFV-0001",
			"drive_file": "DF-0001",
			"storage_object_key": "files/original/image.png",
			"mime_type": "image/png",
			"content_hash": "sha256:source",
		}
	)
	thumb = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0001",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0001",
			"derivative_role": "thumb",
			"status": "pending",
		}
	)
	viewer = FakeDoc(
		{
			"doctype": "Drive File Derivative",
			"name": "DFD-0002",
			"drive_file": "DF-0001",
			"drive_file_version": "DFV-0001",
			"derivative_role": "viewer_preview",
			"status": "pending",
		}
	)
	job = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-0001",
			"job_type": "preview",
			"status": "queued",
			"queue_name": "drive_default",
			"drive_file": "DF-0001",
			"file": "FILE-0001",
			"payload_json": json.dumps(
				{
					"drive_file_version": "DFV-0001",
					"mime_type": "image/png",
					"derivative_roles": ["thumb", "viewer_preview"],
				},
				sort_keys=True,
			),
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0001"): drive_file,
			("Drive File Version", "DFV-0001"): version,
			("Drive File Derivative", "DFD-0001"): thumb,
			("Drive File Derivative", "DFD-0002"): viewer,
			("Drive Processing Job", "DPJ-0001"): job,
		}
	)
	module = _load_module()

	class FakeStorage:
		def __init__(self):
			self.writes: list[dict[str, object]] = []

		def read_final_object(self, *, object_key: str) -> bytes:
			assert object_key == "files/original/image.png"
			return b"source-bytes"

		def write_final_object(self, *, object_key: str, content: bytes, mime_type: str | None = None):
			self.writes.append(
				{
					"object_key": object_key,
					"content": content,
					"mime_type": mime_type,
				}
			)
			return {
				"object_key": object_key,
				"storage_backend": "local",
				"file_url": f"/private/files/ifitwala_drive/{object_key}",
			}

	storage = FakeStorage()
	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: storage)
	monkeypatch.setattr(
		module,
		"_render_image_derivative",
		lambda *, source_content, derivative_role: {
			"content": f"rendered-{derivative_role}".encode(),
			"mime_type": "image/webp",
			"width": 960 if derivative_role == "viewer_preview" else 160,
			"height": 540 if derivative_role == "viewer_preview" else 90,
			"size_bytes": len(f"rendered-{derivative_role}".encode()),
		},
	)

	result = module.run_preview_job(drive_processing_job_id="DPJ-0001")

	assert result["status"] == "completed"
	assert result["preview_status"] == "ready"
	assert result["ready_roles"] == ["viewer_preview", "thumb"]
	assert result["failed_roles"] == []
	assert drive_file.preview_status == "ready"
	assert job.status == "completed"

	assert viewer.status == "ready"
	assert viewer.storage_object_key == "derivatives/DF-0001/DFV-0001/viewer_preview.webp"
	assert viewer.mime_type == "image/webp"
	assert viewer.width == 960
	assert viewer.height == 540
	assert thumb.status == "ready"
	assert thumb.storage_object_key == "derivatives/DF-0001/DFV-0001/thumb.webp"
	assert thumb.width == 160
	assert thumb.height == 90

	assert storage.writes == [
		{
			"object_key": "derivatives/DF-0001/DFV-0001/viewer_preview.webp",
			"content": b"rendered-viewer_preview",
			"mime_type": "image/webp",
		},
		{
			"object_key": "derivatives/DF-0001/DFV-0001/thumb.webp",
			"content": b"rendered-thumb",
			"mime_type": "image/webp",
		},
	]


def test_run_preview_job_blocks_stale_version_jobs():
	drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0001",
			"file": "FILE-0001",
			"current_version": "DFV-0002",
			"preview_status": "pending",
			"storage_backend": "local",
			"storage_object_key": "files/original/image.png",
		}
	)
	job = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-0001",
			"job_type": "preview",
			"status": "queued",
			"queue_name": "drive_default",
			"drive_file": "DF-0001",
			"file": "FILE-0001",
			"payload_json": json.dumps(
				{
					"drive_file_version": "DFV-0001",
					"mime_type": "image/png",
					"derivative_roles": ["viewer_preview"],
				},
				sort_keys=True,
			),
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0001"): drive_file,
			("Drive Processing Job", "DPJ-0001"): job,
		}
	)
	module = _load_module()

	result = module.run_preview_job(drive_processing_job_id="DPJ-0001")

	assert result == {
		"status": "blocked",
		"reason": "stale_version",
		"requested_version": "DFV-0001",
		"current_version": "DFV-0002",
	}
	assert job.status == "blocked"
	assert drive_file.preview_status == "pending"


def test_run_preview_job_marks_failed_when_renderer_unavailable(monkeypatch):
	drive_file = FakeDoc(
		{
			"doctype": "Drive File",
			"name": "DF-0001",
			"file": "FILE-0001",
			"current_version": "DFV-0001",
			"preview_status": "pending",
			"storage_backend": "local",
			"storage_object_key": "files/original/image.png",
			"content_hash": "sha256:source",
		}
	)
	version = FakeDoc(
		{
			"doctype": "Drive File Version",
			"name": "DFV-0001",
			"drive_file": "DF-0001",
			"storage_object_key": "files/original/image.png",
			"mime_type": "image/png",
			"content_hash": "sha256:source",
		}
	)
	job = FakeDoc(
		{
			"doctype": "Drive Processing Job",
			"name": "DPJ-0001",
			"job_type": "preview",
			"status": "queued",
			"queue_name": "drive_default",
			"drive_file": "DF-0001",
			"file": "FILE-0001",
			"payload_json": json.dumps(
				{
					"drive_file_version": "DFV-0001",
					"mime_type": "image/png",
					"derivative_roles": ["thumb", "viewer_preview"],
				},
				sort_keys=True,
			),
		}
	)
	_install_fake_frappe(
		docs_map={
			("Drive File", "DF-0001"): drive_file,
			("Drive File Version", "DFV-0001"): version,
			("Drive Processing Job", "DPJ-0001"): job,
		}
	)
	module = _load_module()

	class FakeStorage:
		def read_final_object(self, *, object_key: str) -> bytes:
			return b"source-bytes"

		def write_final_object(self, *, object_key: str, content: bytes, mime_type: str | None = None):
			raise AssertionError("No derivative should be written when renderer is unavailable.")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend_name=None: FakeStorage())
	monkeypatch.setattr(
		module,
		"_render_image_derivative",
		lambda *, source_content, derivative_role: (_ for _ in ()).throw(
			RuntimeError("Drive preview generation requires Pillow for image derivatives.")
		),
	)

	result = module.run_preview_job(drive_processing_job_id="DPJ-0001")

	assert result["status"] == "failed"
	assert result["preview_status"] == "failed"
	assert drive_file.preview_status == "failed"
	assert job.status == "failed"

	thumb = FakeDoc._docs_map[("Drive File Derivative", "DFD-0001")]
	viewer = FakeDoc._docs_map[("Drive File Derivative", "DFD-0002")]
	assert thumb.status == "failed"
	assert thumb.error_code == "preview_runtime_missing"
	assert viewer.status == "failed"
	assert viewer.error_code == "preview_runtime_missing"
