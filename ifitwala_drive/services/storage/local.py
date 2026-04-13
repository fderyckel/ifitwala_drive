from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from typing import Any
from urllib.parse import quote

import frappe

from ifitwala_drive.services.storage.base import StorageRuntimeProfile, build_object_key


class LocalStorageBackend:
	"""Filesystem-backed storage backend used for local and proxy-upload environments."""

	backend_name = "local"

	def __init__(self, *, profile: StorageRuntimeProfile | None = None):
		self.profile = profile

	def create_temporary_upload_target(
		self,
		*,
		session_key: str,
		filename: str,
		mime_type: str | None = None,
		upload_token: str | None = None,
		expected_size_bytes: int | None = None,
		object_key_hint: str | None = None,
	) -> dict[str, Any]:
		object_key = object_key_hint or build_object_key(
			"tmp",
			session_key,
			self._normalize_filename(filename),
			base_prefix=self._base_prefix(),
		)
		headers: dict[str, Any] = {}
		if mime_type:
			headers["Content-Type"] = mime_type
		if upload_token:
			headers["X-Drive-Upload-Token"] = upload_token
		if expected_size_bytes is not None:
			headers["X-Drive-Expected-Size"] = expected_size_bytes

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

	def write_final_object(
		self,
		*,
		object_key: str,
		content: bytes,
		mime_type: str | None = None,
	) -> dict[str, Any]:
		path = self._absolute_path(object_key)
		self._ensure_parent(path)
		with open(path, "wb") as handle:
			handle.write(content)
		return self._artifact_for_key(object_key)

	def build_public_object_url(self, *, object_key: str) -> str | None:
		return None

	def read_object_metadata(self, *, object_key: str) -> dict[str, Any]:
		path = self._absolute_path(object_key)
		if not os.path.exists(path):
			return {
				"exists": False,
				"size_bytes": None,
				"checksum": None,
				"verifiable": True,
			}
		return {
			"exists": True,
			"size_bytes": os.path.getsize(path),
			"checksum": None,
			"verifiable": True,
		}

	def temporary_object_exists(self, *, object_key: str) -> bool:
		return os.path.exists(self._absolute_path(object_key))

	def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
		path = self._absolute_path(object_key)
		with open(path, "rb") as handle:
			return handle.read(max(0, int(max_bytes)))

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> dict[str, Any]:
		source = self._absolute_path(object_key)
		target = self._absolute_path(final_key)
		if object_key == final_key:
			if not os.path.exists(target):
				raise FileNotFoundError(final_key)
			return self._artifact_for_key(final_key)

		if os.path.exists(target) and not os.path.exists(source):
			return self._artifact_for_key(final_key)

		if not os.path.exists(source):
			raise FileNotFoundError(object_key)

		self._ensure_parent(target)
		shutil.move(source, target)
		self._cleanup_empty_parents(source)
		return self._artifact_for_key(final_key)

	def abort_temporary_object(self, *, object_key: str) -> None:
		path = self._absolute_path(object_key)
		if os.path.exists(path):
			os.remove(path)
			self._cleanup_empty_parents(path)

	def issue_download_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
		filename: str | None = None,
	) -> dict[str, Any]:
		url = file_url or self._build_private_file_url(object_key)
		return {
			"grant_type": "private_url",
			"url": url,
		}

	def issue_preview_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
		filename: str | None = None,
	) -> dict[str, Any]:
		url = file_url or self._build_private_file_url(object_key)
		return {
			"grant_type": "private_url",
			"url": url,
		}

	def delete_object(self, *, object_key: str) -> None:
		self.abort_temporary_object(object_key=object_key)

	def _artifact_for_key(self, object_key: str) -> dict[str, Any]:
		return {
			"object_key": object_key,
			"storage_backend": self.backend_name,
			"file_url": self._build_private_file_url(object_key),
		}

	def _build_upload_url(self, session_key: str) -> str:
		return f"/api/method/ifitwala_drive.api.uploads.upload_session_blob?session_key={quote(session_key)}"

	def _build_private_file_url(self, object_key: str) -> str:
		return f"/private/files/ifitwala_drive/{quote(object_key, safe='/')}"

	def _absolute_path(self, object_key: str) -> str:
		return os.path.join(self._storage_root(), *object_key.split("/"))

	def _storage_root(self) -> str:
		configured = getattr(self.profile, "local_staging_root", None)
		if not configured:
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

	def _base_prefix(self) -> str:
		return getattr(self.profile, "base_prefix", "") if self.profile else ""

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
