from __future__ import annotations

import importlib
import sys
import types

import pytest


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe(*, site_name: str = "site-a"):
	class FrappeError(Exception):
		pass

	def _throw(message):
		raise FrappeError(message)

	def _identity(message):
		return message

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = _identity
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.local = types.SimpleNamespace(site=site_name)
	frappe.conf = {"site_name": site_name}

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		def __init__(self, data=None):
			self.meta = types.SimpleNamespace(get_label=lambda fieldname: fieldname.replace("_", " ").title())
			for key, value in (data or {}).items():
				setattr(self, key, value)

		def get(self, key, default=None):
			return getattr(self, key, default)

	document.Document = Document

	sys.modules["frappe"] = frappe
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return FrappeError


def _load_module():
	_purge_modules(
		"ifitwala_drive.services.storage.base",
		"ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings",
	)
	return importlib.import_module(
		"ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings"
	)


def _settings_doc(**overrides):
	values = {
		"enabled": 1,
		"backend_name": "gcs",
		"storage_mode": "gcs_for_new_writes",
		"bucket_or_container": "drive-bucket",
		"base_prefix": "sites/site-a",
		"credential_source": "adc_or_workload_identity",
		"signing_mode": "gcs_signed_url",
		"migration_status": "idle",
		"batch_size": 100,
	}
	values.update(overrides)
	return values


def test_remote_settings_require_site_scoped_base_prefix():
	FrappeError = _install_fake_frappe()
	module = _load_module()
	doc = module.DriveStorageSettings(_settings_doc(base_prefix="shared-prefix"))

	with pytest.raises(FrappeError, match="Base Prefix must use the site-scoped shape sites/<site_name>"):
		doc.validate()


def test_remote_settings_require_current_site_prefix():
	FrappeError = _install_fake_frappe(site_name="site-a")
	module = _load_module()
	doc = module.DriveStorageSettings(_settings_doc(base_prefix="sites/site-b"))

	with pytest.raises(FrappeError, match="Base Prefix must match the current site and use sites/site-a"):
		doc.validate()


def test_remote_settings_require_non_empty_base_prefix():
	FrappeError = _install_fake_frappe()
	module = _load_module()
	doc = module.DriveStorageSettings(_settings_doc(base_prefix=""))

	with pytest.raises(FrappeError, match="Base Prefix is required when remote storage is enabled"):
		doc.validate()


def test_remote_settings_normalize_valid_base_prefix():
	_install_fake_frappe(site_name="site-a")
	module = _load_module()
	doc = module.DriveStorageSettings(_settings_doc(base_prefix="/sites/site-a/"))

	doc.validate()

	assert doc.base_prefix == "sites/site-a"
