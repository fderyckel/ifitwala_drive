from __future__ import annotations

from typing import Any
from urllib.parse import quote

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

	def write_final_object(
		self,
		*,
		object_key: str,
		content: bytes,
		mime_type: str | None = None,
	) -> dict[str, Any]:
		self._build_blob(object_key).upload_from_string(
			content,
			content_type=mime_type or "application/octet-stream",
		)
		return self._artifact_for_key(object_key)

	def read_object_metadata(self, *, object_key: str) -> dict[str, Any]:
		blob = self._build_blob(object_key)
		if not blob.exists():
			return {
				"exists": False,
				"size_bytes": None,
				"checksum": None,
				"verifiable": True,
			}
		if hasattr(blob, "reload"):
			blob.reload()
		return {
			"exists": True,
			"size_bytes": getattr(blob, "size", None),
			"checksum": getattr(blob, "md5_hash", None),
			"verifiable": True,
		}

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

	def issue_download_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on,
		filename: str | None = None,
	) -> dict[str, Any]:
		if self._use_signed_read_urls():
			return {
				"grant_type": self.grant_type,
				"url": self._build_signed_read_url(
					object_key=object_key,
					expires_on=expires_on,
					filename=filename,
					disposition="attachment",
				),
			}

		return super().issue_download_grant(
			object_key=object_key,
			file_url=file_url,
			expires_on=expires_on,
			filename=filename,
		)

	def issue_preview_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on,
		filename: str | None = None,
	) -> dict[str, Any]:
		if self._use_signed_read_urls():
			return {
				"grant_type": self.grant_type,
				"url": self._build_signed_read_url(
					object_key=object_key,
					expires_on=expires_on,
					filename=filename,
					disposition="inline",
				),
			}

		return super().issue_preview_grant(
			object_key=object_key,
			file_url=file_url,
			expires_on=expires_on,
			filename=filename,
		)

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
		project = getattr(self.profile, "project_id", None)
		credential_source = str(getattr(self.profile, "credential_source", None) or "").strip()
		if credential_source == "service_account_file":
			file_path = str(getattr(self.profile, "service_account_file_path", None) or "").strip()
			if not file_path:
				raise RuntimeError(
					"GCS storage backend requires service_account_file_path when credential_source is service_account_file."
				)
			try:
				from google.oauth2 import service_account
			except ImportError as exc:
				raise RuntimeError(
					"GCS storage backend requires google-auth service account support."
				) from exc

			credentials = service_account.Credentials.from_service_account_file(file_path)
			return storage.Client(
				project=project or getattr(credentials, "project_id", None), credentials=credentials
			)

		return storage.Client(project=project or None)

	def _use_signed_read_urls(self) -> bool:
		signing_mode = str(getattr(self.profile, "signing_mode", None) or "").strip().lower()
		if signing_mode in {"configured_urls", "configured_url_bases"}:
			return False
		if signing_mode in {"signed_url", "gcs_signed_url"}:
			return True

		return not bool(
			getattr(self.profile, "download_url_base", None)
			or getattr(self.profile, "preview_url_base", None)
			or getattr(self.profile, "object_url_base", None)
		)

	def _build_signed_read_url(
		self,
		*,
		object_key: str,
		expires_on,
		filename: str | None,
		disposition: str,
	) -> str:
		response_disposition = None
		normalized_filename = str(filename or "").strip()
		if normalized_filename:
			safe_filename = normalized_filename.replace("\\", "_").replace('"', "_")
			response_disposition = (
				f"{disposition}; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(safe_filename)}"
			)

		return self._build_blob(object_key).generate_signed_url(
			version="v4",
			expiration=expires_on,
			method="GET",
			response_disposition=response_disposition,
		)
