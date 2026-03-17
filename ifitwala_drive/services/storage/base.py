# ifitwala_drive/ifitwala_drive/services/storage/base.py

from __future__ import annotations

from typing import Any, Dict, Protocol


class StorageBackend(Protocol):
	def create_temporary_upload_target(self, *, session_key: str, filename: str, mime_type: str | None = None) -> Dict[str, Any]:
		...

	def temporary_object_exists(self, *, object_key: str) -> bool:
		...

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> Dict[str, Any]:
		...

	def abort_temporary_object(self, *, object_key: str) -> None:
		...
