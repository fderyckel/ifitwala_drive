from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any
from urllib.parse import quote

import frappe


class LocalStorageBackend:
	"""Same-host storage backend for early Phase 1 rollout."""

	backend_name = "local"

	def create_temporary_upload_target(
		self,
		*,
		session_key: str,
		filename: str,
		mime_type: str | None = None,
		upload_token: str | None = None,
	) -> dict[str, Any]:
		object_key = f"tmp/{session_key}/{self._normalize_filename(filename)}"
		headers: dict[str, Any] = {}
		if mime_type:
			headers["Content-Type"] = mime_type
		if upload_token:
			headers["X-Drive-Upload-Token"] = upload_token

		return {
			"object_key": object_key,
			"upload_strategy": "proxy_post",
			"upload_target": {
				"method": "POST",
				"url": self._build_upload_url(session_key),
				"headers": headers,
			},
		}

	def write_temporary_object(self, *, object_key: str, content: bytes) -> dict[str, Any]:
		path = self._absolute_path(object_key)
		self._ensure_parent(path)
		with open(path, "wb") as handle:
			handle.write(content)
		return {
			"object_key": object_key,
			"size_bytes": len(content),
		}

	def temporary_object_exists(self, *, object_key: str) -> bool:
		return os.path.exists(self._absolute_path(object_key))

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> dict[str, Any]:
		source = self._absolute_path(object_key)
		if not os.path.exists(source):
			raise FileNotFoundError(object_key)

		target = self._absolute_path(final_key)
		self._ensure_parent(target)
		shutil.move(source, target)
		self._cleanup_empty_parents(source)

		return {
			"object_key": final_key,
			"storage_backend": self.backend_name,
			"file_url": self._build_private_file_url(final_key),
		}

	def abort_temporary_object(self, *, object_key: str) -> None:
		path = self._absolute_path(object_key)
		if os.path.exists(path):
			os.remove(path)
			self._cleanup_empty_parents(path)

	def _build_upload_url(self, session_key: str) -> str:
		return f"/api/method/ifitwala_drive.api.uploads.upload_session_blob?session_key={quote(session_key)}"

	def _build_private_file_url(self, object_key: str) -> str:
		return f"/private/files/ifitwala_drive/{quote(object_key, safe='/')}"

	def _absolute_path(self, object_key: str) -> str:
		return os.path.join(self._storage_root(), *object_key.split("/"))

	def _storage_root(self) -> str:
		configured = None
		conf = getattr(frappe, "conf", None)
		if conf:
			configured = conf.get("ifitwala_drive_local_storage_root")
		if configured:
			root = configured
		elif hasattr(frappe, "get_site_path"):
			root = frappe.get_site_path("private", "files", "ifitwala_drive")
		else:
			root = os.path.join(tempfile.gettempdir(), "ifitwala_drive")

		os.makedirs(root, exist_ok=True)
		return root

	def _ensure_parent(self, path: str) -> None:
		os.makedirs(os.path.dirname(path), exist_ok=True)

	def _cleanup_empty_parents(self, path: str) -> None:
		root = self._storage_root()
		current = os.path.dirname(path)
		while current.startswith(root) and current != root:
			try:
				os.rmdir(current)
			except OSError:
				break
			current = os.path.dirname(current)

	def _normalize_filename(self, filename: str) -> str:
		filename = (filename or "").strip()
		return filename or "upload.bin"
