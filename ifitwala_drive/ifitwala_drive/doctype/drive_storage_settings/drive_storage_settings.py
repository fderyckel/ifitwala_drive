# ifitwala_drive/ifitwala_drive/doctype/drive_storage_settings/drive_storage_settings.py

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_BACKENDS = {"local", "gcs"}
_ALLOWED_STORAGE_MODES = {
	"local_only",
	"gcs_for_new_writes",
	"gcs_primary_with_local_fallback",
}
_ALLOWED_CREDENTIAL_SOURCES = {
	"adc_or_workload_identity",
	"service_account_file",
}
_ALLOWED_SIGNING_MODES = {
	"gcs_signed_url",
	"configured_urls",
}
_ALLOWED_MIGRATION_STATUSES = {
	"idle",
	"dry_run_ready",
	"queued",
}


class DriveStorageSettings(Document):
	def validate(self) -> None:
		self._set_defaults()
		self._validate_backend_name()
		self._validate_storage_mode()
		self._validate_credential_source()
		self._validate_signing_mode()
		self._validate_migration_status()
		self._validate_gcs_requirements()
		self._validate_url_fields()
		self._validate_batch_size()

	def _set_defaults(self) -> None:
		if not self.backend_name:
			self.backend_name = "local"

		if not self.storage_mode:
			self.storage_mode = "local_only"

		if not self.credential_source:
			self.credential_source = "adc_or_workload_identity"

		if not self.signing_mode:
			self.signing_mode = "gcs_signed_url"

		if not self.migration_status:
			self.migration_status = "idle"

		if self.batch_size is None:
			self.batch_size = 100

	def _validate_backend_name(self) -> None:
		if self.backend_name not in _ALLOWED_BACKENDS:
			frappe.throw(_("Invalid storage backend: {0}").format(self.backend_name))

	def _validate_storage_mode(self) -> None:
		if self.storage_mode not in _ALLOWED_STORAGE_MODES:
			frappe.throw(_("Invalid storage mode: {0}").format(self.storage_mode))

	def _validate_credential_source(self) -> None:
		if self.credential_source not in _ALLOWED_CREDENTIAL_SOURCES:
			frappe.throw(_("Invalid credential source: {0}").format(self.credential_source))

	def _validate_signing_mode(self) -> None:
		if self.signing_mode not in _ALLOWED_SIGNING_MODES:
			frappe.throw(_("Invalid signing mode: {0}").format(self.signing_mode))

	def _validate_migration_status(self) -> None:
		if self.migration_status not in _ALLOWED_MIGRATION_STATUSES:
			frappe.throw(_("Invalid migration status: {0}").format(self.migration_status))

	def _validate_gcs_requirements(self) -> None:
		if not int(bool(self.enabled or 0)):
			return

		if self.backend_name == "local":
			if self.storage_mode != "local_only":
				frappe.throw(_("Local storage backend only supports storage_mode = local_only."))
			return

		if self.backend_name != "gcs" or self.storage_mode == "local_only":
			return

		if not str(self.bucket_or_container or "").strip():
			frappe.throw(_("Bucket / Container is required when GCS storage is enabled."))

		if (
			self.credential_source == "service_account_file"
			and not str(self.service_account_file_path or "").strip()
		):
			frappe.throw(
				_("Service Account File Path is required when credential source is service_account_file.")
			)

	def _validate_url_fields(self) -> None:
		for fieldname in (
			"endpoint",
			"upload_url_base",
			"download_url_base",
			"preview_url_base",
			"object_url_base",
			"probe_url_base",
		):
			value = str(self.get(fieldname) or "").strip()
			if not value:
				continue
			if not value.startswith(("http://", "https://")):
				frappe.throw(
					_("{0} must start with http:// or https://").format(self.meta.get_label(fieldname))
				)

	def _validate_batch_size(self) -> None:
		if self.batch_size is None:
			return
		if int(self.batch_size) < 1:
			frappe.throw(_("Batch Size must be at least 1."))


@frappe.whitelist()
def test_storage_connection() -> dict[str, Any]:
	settings = frappe.get_cached_doc("Drive Storage Settings")
	if hasattr(settings, "check_permission"):
		settings.check_permission("read")

	from ifitwala_drive.services.storage.base import get_storage_backend, resolve_storage_runtime_profile

	profile = resolve_storage_runtime_profile()
	backend = get_storage_backend(profile.backend_name)
	response: dict[str, Any] = {
		"backend_name": backend.backend_name,
		"provider_family": profile.provider_family,
		"storage_mode": profile.storage_mode,
	}

	if backend.backend_name == "gcs":
		bucket = backend._get_bucket()
		bucket_exists = bucket.exists() if hasattr(bucket, "exists") else None
		response.update(
			{
				"bucket_or_container": getattr(bucket, "name", None),
				"bucket_exists": bucket_exists,
				"credential_source": profile.credential_source,
				"signing_mode": profile.signing_mode,
			}
		)
		return response

	if hasattr(backend, "_storage_root"):
		response["local_staging_root"] = backend._storage_root()
	elif profile.local_staging_root:
		response["local_staging_root"] = profile.local_staging_root

	return response


@frappe.whitelist()
def dry_run_attachment_offload(limit: int | None = None) -> dict[str, Any]:
	settings = frappe.get_cached_doc("Drive Storage Settings")
	if hasattr(settings, "check_permission"):
		settings.check_permission("write")

	from ifitwala_drive.services.storage.offload import dry_run_attachment_offload_service

	return dry_run_attachment_offload_service(settings_doc=settings, limit=limit)


@frappe.whitelist()
def enqueue_attachment_offload_jobs(limit: int | None = None) -> dict[str, Any]:
	settings = frappe.get_cached_doc("Drive Storage Settings")
	if hasattr(settings, "check_permission"):
		settings.check_permission("write")

	from ifitwala_drive.services.storage.offload import enqueue_attachment_offload_jobs_service

	return enqueue_attachment_offload_jobs_service(settings_doc=settings, limit=limit)
