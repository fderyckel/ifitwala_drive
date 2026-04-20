from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta


class _FakeSessionDoc:
	def __init__(self, name: str, *, status: str, tmp_object_key: str | None, storage_backend: str = "local"):
		self.name = name
		self.status = status
		self.tmp_object_key = tmp_object_key
		self.storage_backend = storage_backend
		self.owner_doctype = "Task Submission"
		self.owner_name = "TSU-0001"
		self.intended_slot = "submission_evidence"
		self.saved = 0

	def save(self, ignore_permissions: bool = False):
		self.saved += 1
		return self


def _purge_modules() -> None:
	for module_name in list(sys.modules):
		if (
			module_name == "frappe"
			or module_name.startswith("frappe.")
			or module_name.startswith("ifitwala_drive.services.uploads.sessions")
		):
			sys.modules.pop(module_name, None)


def _install_fake_environment(*, docs_map: dict[str, _FakeSessionDoc], events: list[tuple[str, dict]]):
	now_value = datetime(2026, 4, 20, 12, 0, 0)

	frappe = types.ModuleType("frappe")
	frappe._ = lambda message: message
	frappe.get_doc = lambda doctype, name=None: docs_map[name]
	frappe.get_all = lambda doctype, **kwargs: [
		{
			"name": doc.name,
			"storage_backend": doc.storage_backend,
			"tmp_object_key": doc.tmp_object_key,
			"owner_doctype": doc.owner_doctype,
			"owner_name": doc.owner_name,
			"intended_slot": doc.intended_slot,
		}
		for doc in docs_map.values()
		if doc.status in {"created", "uploading", "uploaded"}
	]
	frappe.db = types.SimpleNamespace(get_value=lambda *args, **kwargs: None)
	sys.modules["frappe"] = frappe

	frappe_utils = types.ModuleType("frappe.utils")
	frappe_utils.now_datetime = lambda: now_value
	sys.modules["frappe.utils"] = frappe_utils

	class _DriveLock:
		def __enter__(self):
			return None

		def __exit__(self, exc_type, exc, tb):
			return False

	concurrency = types.ModuleType("ifitwala_drive.services.concurrency")
	concurrency.drive_lock = lambda *args, **kwargs: _DriveLock()
	concurrency.is_duplicate_entry_error = lambda exc: False
	sys.modules["ifitwala_drive.services.concurrency"] = concurrency

	bridge = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_bridge")
	bridge.reconcile_upload_session_payload = lambda payload: payload
	sys.modules["ifitwala_drive.services.integration.ifitwala_ed_bridge"] = bridge

	keys = types.ModuleType("ifitwala_drive.services.uploads.keys")
	keys.build_upload_object_key = lambda **kwargs: "tmp/object"
	keys.build_upload_session_key = lambda payload, user=None: "session-key"
	sys.modules["ifitwala_drive.services.uploads.keys"] = keys

	validation = types.ModuleType("ifitwala_drive.services.uploads.validation")
	validation.validate_create_session_payload = lambda payload: None
	sys.modules["ifitwala_drive.services.uploads.validation"] = validation

	logging_module = types.ModuleType("ifitwala_drive.services.logging")
	logging_module.log_drive_event = lambda event, **kwargs: events.append((event, kwargs))
	sys.modules["ifitwala_drive.services.logging"] = logging_module


def test_expire_abandoned_upload_sessions_service_marks_sessions_expired_and_logs_cleanup_failures(
	monkeypatch,
):
	_purge_modules()
	events: list[tuple[str, dict]] = []
	docs_map = {
		"DUS-0001": _FakeSessionDoc("DUS-0001", status="created", tmp_object_key="tmp/one"),
		"DUS-0002": _FakeSessionDoc("DUS-0002", status="uploading", tmp_object_key="tmp/two"),
	}
	_install_fake_environment(docs_map=docs_map, events=events)

	module = importlib.import_module("ifitwala_drive.services.uploads.sessions")

	aborted_keys: list[str] = []

	class _Storage:
		def abort_temporary_object(self, *, object_key):
			aborted_keys.append(object_key)
			if object_key == "tmp/two":
				raise RuntimeError("cannot abort")

	monkeypatch.setattr(module, "get_storage_backend", lambda backend=None: _Storage())

	summary = module.expire_abandoned_upload_sessions_service(limit=50)

	assert summary == {"expired": 2, "cleanup_errors": 1}
	assert docs_map["DUS-0001"].status == "expired"
	assert docs_map["DUS-0002"].status == "expired"
	assert docs_map["DUS-0001"].saved == 1
	assert docs_map["DUS-0002"].saved == 1
	assert aborted_keys == ["tmp/one", "tmp/two"]
	assert [event for event, _payload in events] == [
		"upload_session_expired",
		"upload_session_expire_cleanup_failed",
		"upload_session_expired",
	]
