# ifitwala_drive/ifitwala_drive/services/storage/base.py

from __future__ import annotations

from typing import Any, Dict, Protocol


DEFAULT_STORAGE_BACKEND = "gcs"


class StorageBackend(Protocol):
	backend_name: str

	def create_temporary_upload_target(self, *, session_key: str, filename: str, mime_type: str | None = None) -> Dict[str, Any]:
		...

	def temporary_object_exists(self, *, object_key: str) -> bool:
		...

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> Dict[str, Any]:
		...

	def abort_temporary_object(self, *, object_key: str) -> None:
		...


def get_storage_backend(backend_name: str | None = None) -> StorageBackend:
	backend_name = (backend_name or DEFAULT_STORAGE_BACKEND).strip().lower()

	if backend_name == "gcs":
		from ifitwala_drive.services.storage.gcs import GCSStorageBackend

		return GCSStorageBackend()

	raise ValueError(f"Unsupported storage backend: {backend_name}")
