from __future__ import annotations

from typing import Any

from ifitwala_drive.services.storage.base import build_object_key
from ifitwala_drive.services.storage.remote import ConfiguredRemoteStorageBackend


class GCSStorageBackend(ConfiguredRemoteStorageBackend):
	backend_name = "gcs"
	grant_type = "signed_url"
	default_upload_strategy = "resumable_put"

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
		content_type = mime_type or "application/octet-stream"
		headers: dict[str, Any] = {"Content-Type": content_type}
		if upload_token:
			headers["X-Drive-Upload-Token"] = upload_token
		if expected_size_bytes is not None:
			headers["Content-Length"] = str(expected_size_bytes)

		session_uri = self._build_blob(object_key).create_resumable_upload_session(
			content_type=content_type,
			size=expected_size_bytes,
		)
		return {
			"object_key": object_key,
			"upload_strategy": self.default_upload_strategy,
			"upload_target": {
				"method": "PUT",
				"url": session_uri,
				"headers": headers,
			},
		}

	def temporary_object_exists(self, *, object_key: str) -> bool:
		return self._build_blob(object_key).exists()

	def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
		if max_bytes <= 0:
			return b""
		return self._build_blob(object_key).download_as_bytes(start=0, end=max_bytes - 1)

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> dict[str, Any]:
		bucket = self._get_bucket()
		source_blob = bucket.blob(object_key)
		target_blob = bucket.blob(final_key)

		if object_key == final_key:
			if not target_blob.exists():
				raise FileNotFoundError(final_key)
			return self._artifact_for_key(final_key)

		source_exists = source_blob.exists()
		target_exists = target_blob.exists()
		if not source_exists and target_exists:
			return self._artifact_for_key(final_key)
		if not source_exists:
			raise FileNotFoundError(object_key)

		bucket.copy_blob(source_blob, bucket, final_key)
		source_blob.delete()
		return self._artifact_for_key(final_key)

	def abort_temporary_object(self, *, object_key: str) -> None:
		blob = self._build_blob(object_key)
		if blob.exists():
			blob.delete()

	def delete_object(self, *, object_key: str) -> None:
		self.abort_temporary_object(object_key=object_key)

	def _artifact_for_key(self, object_key: str) -> dict[str, Any]:
		return {
			"object_key": object_key,
			"storage_backend": self.backend_name,
			"file_url": self._build_object_url(object_key),
		}

	def _build_blob(self, object_key: str):
		return self._get_bucket().blob(object_key)

	def _get_bucket(self):
		bucket_name = str(getattr(self.profile, "bucket_or_container", None) or "").strip()
		if not bucket_name:
			raise RuntimeError("GCS storage backend requires bucket_or_container configuration.")
		return self._get_client().bucket(bucket_name)

	def _get_client(self):
		try:
			from google.cloud import storage
		except ImportError as exc:
			raise RuntimeError("GCS storage backend requires google-cloud-storage to be installed.") from exc
		return storage.Client()
