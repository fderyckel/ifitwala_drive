# ifitwala_drive/ifitwala_drive/services/storage/gcs.py

from __future__ import annotations

from typing import Any, Dict


class GCSStorageBackend:
	"""Stub GCS backend for early implementation.

	Replace placeholder URLs and existence checks with actual GCS calls later.
	"""

	def create_temporary_upload_target(self, *, session_key: str, filename: str, mime_type: str | None = None) -> Dict[str, Any]:
		object_key = f"tmp/{session_key}/{filename}"
		return {
			"object_key": object_key,
			"upload_strategy": "signed_put",
			"upload_target": {
				"method": "PUT",
				"url": f"https://example.invalid/upload/{object_key}",
				"headers": {},
			},
		}

	def temporary_object_exists(self, *, object_key: str) -> bool:
		# Replace with real GCS object existence check.
		return True

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> Dict[str, Any]:
		# Replace with move/copy + finalization logic.
		return {
			"object_key": final_key,
			"storage_backend": "gcs",
		}

	def abort_temporary_object(self, *, object_key: str) -> None:
		# Replace with delete temp object if present.
		return
