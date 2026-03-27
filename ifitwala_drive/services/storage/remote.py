from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from ifitwala_drive.services.storage.base import StorageRuntimeProfile, build_object_key
from ifitwala_drive.services.storage.local import LocalStorageBackend


class ConfiguredRemoteStorageBackend(LocalStorageBackend):
	"""Config-driven remote backend with local proxy fallback.

	This keeps request-path behavior provider-neutral:
	- when runtime config provides direct upload/object URLs, the backend behaves like signed object storage
	- when it does not, the backend falls back to proxy upload with local staging
	"""

	grant_type = "signed_url"
	default_upload_strategy = "signed_put"

	def __init__(self, *, profile: StorageRuntimeProfile):
		super().__init__(profile=profile)

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
		if not self._remote_upload_enabled():
			return super().create_temporary_upload_target(
				session_key=session_key,
				filename=filename,
				mime_type=mime_type,
				upload_token=upload_token,
				expected_size_bytes=expected_size_bytes,
				object_key_hint=object_key,
			)

		headers = dict(getattr(self.profile, "extra_headers", {}) or {})
		if mime_type:
			headers["Content-Type"] = mime_type
		if upload_token:
			headers["X-Drive-Upload-Token"] = upload_token
		if expected_size_bytes is not None:
			headers["Content-Length"] = str(expected_size_bytes)

		upload_strategy = getattr(self.profile, "upload_strategy", None) or self.default_upload_strategy
		return {
			"object_key": object_key,
			"upload_strategy": upload_strategy,
			"upload_target": {
				"method": "PUT" if upload_strategy == "signed_put" else "POST",
				"url": self._build_remote_upload_url(object_key),
				"headers": headers,
			},
		}

	def temporary_object_exists(self, *, object_key: str) -> bool:
		return super().temporary_object_exists(object_key=object_key)

	def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes:
		return super().read_temporary_object_head(object_key=object_key, max_bytes=max_bytes)

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> dict[str, Any]:
		if super().temporary_object_exists(object_key=object_key):
			artifact = super().finalize_temporary_object(object_key=object_key, final_key=final_key)
			artifact["storage_backend"] = self.backend_name
			artifact["file_url"] = self._build_object_url(final_key)
			return artifact

		if object_key != final_key and not self._remote_upload_enabled():
			return super().finalize_temporary_object(object_key=object_key, final_key=final_key)

		return {
			"object_key": final_key,
			"storage_backend": self.backend_name,
			"file_url": self._build_object_url(final_key),
		}

	def issue_download_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
		filename: str | None = None,
	) -> dict[str, Any]:
		if not self._remote_upload_enabled():
			return super().issue_download_grant(
				object_key=object_key,
				file_url=file_url,
				expires_on=expires_on,
				filename=filename,
			)

		return {
			"grant_type": self.grant_type,
			"url": self._build_download_url(object_key),
		}

	def issue_preview_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
		filename: str | None = None,
	) -> dict[str, Any]:
		if not self._remote_upload_enabled():
			return super().issue_preview_grant(
				object_key=object_key,
				file_url=file_url,
				expires_on=expires_on,
				filename=filename,
			)

		return {
			"grant_type": self.grant_type,
			"url": self._build_preview_url(object_key),
		}

	def _remote_upload_enabled(self) -> bool:
		return bool(
			getattr(self.profile, "upload_url_base", None) or getattr(self.profile, "object_url_base", None)
		)

	def _build_remote_upload_url(self, object_key: str) -> str:
		base = getattr(self.profile, "upload_url_base", None) or getattr(
			self.profile, "object_url_base", None
		)
		return self._build_url(base, object_key)

	def _build_download_url(self, object_key: str) -> str:
		base = (
			getattr(self.profile, "download_url_base", None)
			or getattr(self.profile, "object_url_base", None)
			or getattr(self.profile, "endpoint", None)
		)
		return self._build_url(base, object_key)

	def _build_preview_url(self, object_key: str) -> str:
		base = (
			getattr(self.profile, "preview_url_base", None)
			or getattr(self.profile, "download_url_base", None)
			or getattr(self.profile, "object_url_base", None)
			or getattr(self.profile, "endpoint", None)
		)
		return self._build_url(base, object_key)

	def _build_object_url(self, object_key: str) -> str:
		base = getattr(self.profile, "object_url_base", None) or getattr(
			self.profile, "download_url_base", None
		)
		if base:
			return self._build_url(base, object_key)
		return super()._build_private_file_url(object_key)

	def _build_url(self, base_url: str | None, object_key: str) -> str:
		encoded = quote(object_key, safe="/")
		if base_url:
			return f"{str(base_url).rstrip('/')}/{encoded}"

		endpoint = str(getattr(self.profile, "endpoint", None) or "").strip().rstrip("/")
		bucket = str(getattr(self.profile, "bucket_or_container", None) or "").strip().strip("/")
		if endpoint and bucket:
			return f"{endpoint}/{quote(bucket, safe='')}/{encoded}"
		if endpoint:
			return f"{endpoint}/{encoded}"
		return super()._build_private_file_url(object_key)
