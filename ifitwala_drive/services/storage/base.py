from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

DEFAULT_STORAGE_BACKEND = "local"
_PROFILE_ENV_KEY = "IFITWALA_DRIVE_STORAGE_PROFILE"


def normalize_storage_backend_name(backend_name: str | None) -> str:
	value = str(backend_name or "").strip()
	if not value:
		return DEFAULT_STORAGE_BACKEND

	normalized = value.lower().replace("-", "_").replace(" ", "_")
	aliases = {
		"local_temporary": "local",
		"s3": "s3_compatible",
		"s3compatible": "s3_compatible",
		"google_cloud_storage": "gcs",
	}
	return aliases.get(normalized, normalized)


@dataclass(frozen=True)
class StorageRuntimeProfile:
	backend_name: str
	provider_family: str
	bucket_or_container: str | None = None
	base_prefix: str = ""
	region: str | None = None
	endpoint: str | None = None
	signing_mode: str | None = None
	quota_scope: str | None = None
	credential_source: str | None = None
	upload_strategy: str | None = None
	upload_url_base: str | None = None
	download_url_base: str | None = None
	preview_url_base: str | None = None
	object_url_base: str | None = None
	probe_url_base: str | None = None
	local_staging_root: str | None = None
	extra_headers: dict[str, Any] = field(default_factory=dict)


def _clean_optional(value: Any) -> str | None:
	text = str(value or "").strip()
	return text or None


def _clean_prefix(value: Any) -> str:
	return str(value or "").strip().strip("/")


def _get_legacy_conf_value(key: str) -> Any:
	try:
		import frappe

		return getattr(frappe, "conf", {}).get(key)
	except Exception:
		return None


def _read_raw_profile() -> dict[str, Any]:
	profile_value: Any = _get_legacy_conf_value("ifitwala_drive_storage_profile")
	if profile_value in (None, ""):
		env_value = os.environ.get(_PROFILE_ENV_KEY)
		if env_value:
			profile_value = env_value

	if isinstance(profile_value, str):
		profile_value = profile_value.strip()
		if not profile_value:
			return {}
		try:
			parsed = json.loads(profile_value)
		except json.JSONDecodeError:
			return {}
		return parsed if isinstance(parsed, dict) else {}

	if isinstance(profile_value, dict):
		return dict(profile_value)

	return {}


def resolve_storage_runtime_profile(backend_name: str | None = None) -> StorageRuntimeProfile:
	raw = _read_raw_profile()
	configured_backend = normalize_storage_backend_name(
		backend_name
		or raw.get("backend_name")
		or raw.get("provider_family")
		or _get_legacy_conf_value("ifitwala_drive_storage_backend")
	)
	provider_family = normalize_storage_backend_name(raw.get("provider_family") or configured_backend)
	extra_headers = raw.get("extra_headers")
	if not isinstance(extra_headers, dict):
		extra_headers = {}

	return StorageRuntimeProfile(
		backend_name=configured_backend,
		provider_family=provider_family,
		bucket_or_container=_clean_optional(raw.get("bucket_or_container") or raw.get("bucket")),
		base_prefix=_clean_prefix(raw.get("base_prefix")),
		region=_clean_optional(raw.get("region")),
		endpoint=_clean_optional(raw.get("endpoint")),
		signing_mode=_clean_optional(raw.get("signing_mode")),
		quota_scope=_clean_optional(raw.get("quota_scope")),
		credential_source=_clean_optional(raw.get("credential_source")),
		upload_strategy=_clean_optional(raw.get("upload_strategy")),
		upload_url_base=_clean_optional(raw.get("upload_url_base")),
		download_url_base=_clean_optional(raw.get("download_url_base")),
		preview_url_base=_clean_optional(raw.get("preview_url_base")),
		object_url_base=_clean_optional(raw.get("object_url_base")),
		probe_url_base=_clean_optional(raw.get("probe_url_base")),
		local_staging_root=_clean_optional(
			raw.get("local_staging_root") or _get_legacy_conf_value("ifitwala_drive_local_storage_root")
		),
		extra_headers=extra_headers,
	)


def build_object_key(*parts: str | None, base_prefix: str | None = None) -> str:
	segments = [str(part or "").strip().strip("/") for part in parts if str(part or "").strip()]
	prefix = str(base_prefix or "").strip().strip("/")
	if prefix:
		segments.insert(0, prefix)
	return "/".join(segments)


class StorageBackend(Protocol):
	backend_name: str

	def create_temporary_upload_target(
		self,
		*,
		session_key: str,
		filename: str,
		mime_type: str | None = None,
		upload_token: str | None = None,
		expected_size_bytes: int | None = None,
		object_key_hint: str | None = None,
	) -> dict[str, Any]: ...

	def write_temporary_object(self, *, object_key: str, content: bytes) -> dict[str, Any]: ...

	def temporary_object_exists(self, *, object_key: str) -> bool: ...

	def read_temporary_object_head(self, *, object_key: str, max_bytes: int) -> bytes: ...

	def finalize_temporary_object(self, *, object_key: str, final_key: str) -> dict[str, Any]: ...

	def abort_temporary_object(self, *, object_key: str) -> None: ...

	def issue_download_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
		filename: str | None = None,
	) -> dict[str, Any]: ...

	def issue_preview_grant(
		self,
		*,
		object_key: str,
		file_url: str | None,
		expires_on: datetime,
		filename: str | None = None,
	) -> dict[str, Any]: ...

	def delete_object(self, *, object_key: str) -> None: ...


def get_storage_backend(backend_name: str | None = None) -> StorageBackend:
	profile = resolve_storage_runtime_profile(backend_name)
	backend_name = normalize_storage_backend_name(profile.backend_name)

	if backend_name == "local":
		from ifitwala_drive.services.storage.local import LocalStorageBackend

		return LocalStorageBackend(profile=profile)

	if backend_name == "gcs":
		from ifitwala_drive.services.storage.gcs import GCSStorageBackend

		return GCSStorageBackend(profile=profile)

	if backend_name == "s3_compatible":
		from ifitwala_drive.services.storage.s3_compatible import S3CompatibleStorageBackend

		return S3CompatibleStorageBackend(profile=profile)

	raise ValueError(f"Unsupported storage backend: {backend_name}")
