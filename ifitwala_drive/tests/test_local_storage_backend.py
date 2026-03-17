from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe(*, root: str):
	frappe = types.ModuleType("frappe")
	frappe.conf = {"ifitwala_drive_local_storage_root": root}
	frappe.get_site_path = lambda *parts: os.path.join(root, *parts)
	sys.modules["frappe"] = frappe
	return frappe


def _load_local_backend():
	_purge_modules("ifitwala_drive.services.storage.local")
	module = importlib.import_module("ifitwala_drive.services.storage.local")
	return module.LocalStorageBackend


def test_local_storage_backend_round_trip():
	root = tempfile.mkdtemp(prefix="ifitwala-drive-local-")
	_install_fake_frappe(root=root)
	LocalStorageBackend = _load_local_backend()
	backend = LocalStorageBackend()
	target = backend.create_temporary_upload_target(
		session_key="session-1",
		filename="essay.docx",
		mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		upload_token="token-1",
	)

	assert target["upload_strategy"] == "proxy_post"
	assert target["upload_target"]["headers"]["X-Drive-Upload-Token"] == "token-1"

	write_result = backend.write_temporary_object(
		object_key=target["object_key"],
		content=b"hello world",
	)
	assert write_result["size_bytes"] == 11
	assert backend.temporary_object_exists(object_key=target["object_key"]) is True

	artifact = backend.finalize_temporary_object(
		object_key=target["object_key"],
		final_key="files/DUS-0001/essay.docx",
	)
	assert artifact["file_url"] == "/private/files/ifitwala_drive/files/DUS-0001/essay.docx"
	assert os.path.exists(os.path.join(root, "files", "DUS-0001", "essay.docx"))


def test_local_storage_backend_abort_deletes_tmp_file():
	root = tempfile.mkdtemp(prefix="ifitwala-drive-local-")
	_install_fake_frappe(root=root)
	LocalStorageBackend = _load_local_backend()
	backend = LocalStorageBackend()
	object_key = "tmp/session-2/notes.txt"
	backend.write_temporary_object(object_key=object_key, content=b"draft")
	assert backend.temporary_object_exists(object_key=object_key) is True

	backend.abort_temporary_object(object_key=object_key)

	assert backend.temporary_object_exists(object_key=object_key) is False


def test_get_storage_backend_defaults_to_local():
	from ifitwala_drive.services.storage import base

	_install_fake_frappe(root=tempfile.mkdtemp(prefix="ifitwala-drive-local-"))
	base.DEFAULT_STORAGE_BACKEND = "local"

	backend = base.get_storage_backend()
	assert backend.backend_name == "local"
