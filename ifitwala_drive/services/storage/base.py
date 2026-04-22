from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

DEFAULT_STORAGE_BACKEND = "local"
_PROFILE_ENV_KEY = "IFITWALA_DRIVE_STORAGE_PROFILE"
_SETTINGS_DOCTYPE = "Drive Storage Settings"


class StorageProfileValidationError(ValueError):
	pass


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
	storage_mode: str | None = None
	bucket_or_container: str | None = None
	base_prefix: str = ""
	region: str | None = None
	endpoint: str | None = None
	project_id: str | None = None
	signing_mode: str | None = None
	quota_scope: str | None = None
	credential_source: str | None = None
	service_account_file_path: str | None = None
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


def _clean_site_name(value: Any) -> str | None:
	text = str(value or "").strip().rstrip("/")
	if not text:
		return None
	return os.path.basename(text) or None


def _get_legacy_conf_value(key: str) -> Any:
	try:
		import frappe

		return getattr(frappe, "conf", {}).get(key)
	except Exception:
		return None


def get_current_site_name() -> str | None:
	try:
		import frappe
	except Exception:
		return None

	local = getattr(frappe, "local", None)
	site_name = _clean_site_name(getattr(local, "site", None))
	if site_name:
		return site_name

	conf = getattr(frappe, "conf", {}) or {}
	return _clean_site_name(conf.get("site_name"))


def _parse_profile_value(profile_value: Any) -> dict[str, Any]:
	if profile_value in (None, ""):
		return {}

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


def _read_env_override_profile() -> dict[str, Any]:
	return _parse_profile_value(os.environ.get(_PROFILE_ENV_KEY))


def _get_settings_doc():
	try:
		import frappe
	except Exception:
		return None

	for loader_name in ("get_cached_doc", "get_single", "get_doc"):
		loader = getattr(frappe, loader_name, None)
		if not callable(loader):
			continue
		try:
			return loader(_SETTINGS_DOCTYPE)
		except TypeError:
			try:
				return loader(_SETTINGS_DOCTYPE, _SETTINGS_DOCTYPE)
			except Exception:
				continue
		except Exception:
			continue

	return None


def _read_settings_profile() -> dict[str, Any] | None:
	doc = _get_settings_doc()
	if not doc:
		return None

	enabled = int(bool(getattr(doc, "enabled", 0) or 0))
	if not enabled:
		return None

	configured_backend = normalize_storage_backend_name(getattr(doc, "backend_name", None) or "local")
	storage_mode = _clean_optional(getattr(doc, "storage_mode", None)) or "local_only"
	if storage_mode == "local_only":
		return {
			"backend_name": "local",
			"provider_family": "local",
			"storage_mode": storage_mode,
		}

	return {
		"backend_name": configured_backend,
		"provider_family": configured_backend,
		"storage_mode": storage_mode,
		"bucket_or_container": getattr(doc, "bucket_or_container", None),
		"base_prefix": getattr(doc, "base_prefix", None),
		"region": getattr(doc, "region", None),
		"endpoint": getattr(doc, "endpoint", None),
		"project_id": getattr(doc, "project_id", None),
		"signing_mode": getattr(doc, "signing_mode", None),
		"credential_source": getattr(doc, "credential_source", None),
		"service_account_file_path": getattr(doc, "service_account_file_path", None),
		"upload_strategy": getattr(doc, "upload_strategy", None),
		"upload_url_base": getattr(doc, "upload_url_base", None),
		"download_url_base": getattr(doc, "download_url_base", None),
		"preview_url_base": getattr(doc, "preview_url_base", None),
		"object_url_base": getattr(doc, "object_url_base", None),
		"probe_url_base": getattr(doc, "probe_url_base", None),
		"local_staging_root": getattr(doc, "local_staging_root", None),
	}


def _read_legacy_profile() -> dict[str, Any]:
	return _parse_profile_value(_get_legacy_conf_value("ifitwala_drive_storage_profile"))


def _read_raw_profile() -> dict[str, Any]:
	env_profile = _read_env_override_profile()
	if env_profile:
		return env_profile

	settings_profile = _read_settings_profile()
	if settings_profile is not None:
		return settings_profile

	return _read_legacy_profile()


def validate_remote_storage_namespace(
	*, bucket_or_container: Any, base_prefix: Any, site_name: str | None = None
) -> str:
	bucket = _clean_optional(bucket_or_container)
	if not bucket:
		raise StorageProfileValidationError("Bucket / Container is required when remote storage is enabled.")

	prefix = _clean_prefix(base_prefix)
	if not prefix:
		raise StorageProfileValidationError(
			"Base Prefix is required when remote storage is enabled and must use the site-scoped shape sites/<site_name>."
		)

	segments = [segment for segment in prefix.split("/") if segment]
	if any(segment in {".", ".."} for segment in segments):
		raise StorageProfileValidationError("Base Prefix cannot contain '.' or '..' path segments.")

	if len(segments) != 2 or segments[0] != "sites":
		raise StorageProfileValidationError("Base Prefix must use the site-scoped shape sites/<site_name>.")

	if site_name and segments[1] != site_name:
		raise StorageProfileValidationError(
			f"Base Prefix must match the current site and use sites/{site_name}."
		)

	return prefix


def _validate_runtime_profile(profile: StorageRuntimeProfile) -> StorageRuntimeProfile:
	if profile.backend_name == "local" or profile.storage_mode == "local_only":
		return profile

	base_prefix = validate_remote_storage_namespace(
		bucket_or_container=profile.bucket_or_container,
		base_prefix=profile.base_prefix,
		site_name=get_current_site_name(),
	)
	return StorageRuntimeProfile(
		backend_name=profile.backend_name,
		provider_family=profile.provider_family,
		storage_mode=profile.storage_mode,
		bucket_or_container=profile.bucket_or_container,
		base_prefix=base_prefix,
		region=profile.region,
		endpoint=profile.endpoint,
		project_id=profile.project_id,
		signing_mode=profile.signing_mode,
		quota_scope=profile.quota_scope,
		credential_source=profile.credential_source,
		service_account_file_path=profile.service_account_file_path,
		upload_strategy=profile.upload_strategy,
		upload_url_base=profile.upload_url_base,
		download_url_base=profile.download_url_base,
		preview_url_base=profile.preview_url_base,
		object_url_base=profile.object_url_base,
		probe_url_base=profile.probe_url_base,
		local_staging_root=profile.local_staging_root,
		extra_headers=profile.extra_headers,
	)


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

	profile = StorageRuntimeProfile(
		backend_name=configured_backend,
		provider_family=provider_family,
		storage_mode=_clean_optional(raw.get("storage_mode")),
		bucket_or_container=_clean_optional(raw.get("bucket_or_container") or raw.get("bucket")),
		base_prefix=_clean_prefix(raw.get("base_prefix")),
		region=_clean_optional(raw.get("region")),
		endpoint=_clean_optional(raw.get("endpoint")),
		project_id=_clean_optional(raw.get("project_id")),
		signing_mode=_clean_optional(raw.get("signing_mode")),
		quota_scope=_clean_optional(raw.get("quota_scope")),
		credential_source=_clean_optional(raw.get("credential_source")),
		service_account_file_path=_clean_optional(raw.get("service_account_file_path")),
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
	return _validate_runtime_profile(profile)


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

	def write_final_object(
		self,
		*,
		object_key: str,
		content: bytes,
		mime_type: str | None = None,
	) -> dict[str, Any]: ...

	def build_public_object_url(self, *, object_key: str) -> str | None: ...

	def read_object_metadata(self, *, object_key: str) -> dict[str, Any]: ...

	def read_final_object(self, *, object_key: str) -> bytes: ...

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
