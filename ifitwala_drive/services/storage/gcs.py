# ifitwala_drive/ifitwala_drive/services/storage/gcs.py

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote


class GCSStorageBackend:
	"""Stub GCS backend for early implementation.

	Replace placeholder URLs and existence checks with actual GCS calls later.
	"""

	backend_name = "gcs"

	def create_temporary_upload_target(self, *, session_key: str, filename: str, mime_type: str | None = None) -> Dict[str, Any]:
		object_key = f"tmp/{session_key}/{self._normalize_filename(filename)}"
		return {
			"object_key": object_key,
			"upload_strategy": "signed_put",
			"upload_target": {
				"method": "PUT",
				"url": self._build_upload_url(object_key),
				"headers": self._build_upload_headers(mime_type),
			},
		}

	def temporary_object_exists(self, *, object_key: str) -> bool:
		# Replace with real GCS object existence check.
		return True

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> Dict[str, Any]:
		# Replace with move/copy + finalization logic.
		return {
			"object_key": final_key,
			"storage_backend": self.backend_name,
			"file_url": self._build_private_object_url(final_key),
		}

	def abort_temporary_object(self, *, object_key: str) -> None:
		# Replace with delete temp object if present.
		return

	def _build_upload_headers(self, mime_type: str | None) -> Dict[str, Any]:
		if not mime_type:
			return {}

		return {
			"Content-Type": mime_type,
		}

	def _build_upload_url(self, object_key: str) -> str:
		return f"https://storage.ifitwala.invalid/upload/{quote(object_key, safe='/')}"

	def _build_private_object_url(self, object_key: str) -> str:
		return f"https://storage.ifitwala.invalid/object/{quote(object_key, safe='/')}"

	def _normalize_filename(self, filename: str) -> str:
		filename = (filename or "").strip()
		return filename or "upload.bin"
