# ifitwala_drive/ifitwala_drive/services/storage/base.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

DEFAULT_STORAGE_BACKEND = "local"


class StorageBackend(Protocol):
	backend_name: str

	def create_temporary_upload_target(
		self,
		*,
		session_key: str,
		filename: str,
		mime_type: str | None = None,
		upload_token: str | None = None,
	) -> dict[str, Any]: ...

	def write_temporary_object(self, *, object_key: str, content: bytes) -> dict[str, Any]: ...

	def temporary_object_exists(self, *, object_key: str) -> bool: ...

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> dict[str, Any]: ...

	def abort_temporary_object(self, *, object_key: str) -> None: ...

	def issue_download_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
	) -> dict[str, Any]: ...

	def issue_preview_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
	) -> dict[str, Any]: ...


def get_storage_backend(backend_name: str | None = None) -> StorageBackend:
	if not backend_name:
		try:
			import frappe

			backend_name = getattr(frappe, "conf", {}).get("ifitwala_drive_storage_backend")
		except Exception:
			backend_name = None

	backend_name = (backend_name or DEFAULT_STORAGE_BACKEND).strip().lower()

	if backend_name == "local":
		from ifitwala_drive.services.storage.local import LocalStorageBackend

		return LocalStorageBackend()

	if backend_name == "gcs":
		from ifitwala_drive.services.storage.gcs import GCSStorageBackend

		return GCSStorageBackend()

	raise ValueError(f"Unsupported storage backend: {backend_name}")
