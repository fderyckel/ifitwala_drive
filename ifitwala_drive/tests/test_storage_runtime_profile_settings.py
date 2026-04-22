from __future__ import annotations

import importlib
import os
import sys
import types

import pytest


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeDoc:
	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def get(self, fieldname, default=None):
		return getattr(self, fieldname, default)


def _install_fake_frappe(*, conf=None, settings_doc=None):
	frappe = types.ModuleType("frappe")
	frappe.conf = conf or {}
	frappe.local = types.SimpleNamespace(site=(frappe.conf.get("site_name") or "site-a"))
	frappe.get_cached_doc = lambda doctype, name=None: (
		settings_doc if doctype == "Drive Storage Settings" else None
	)
	frappe.get_single = lambda doctype: settings_doc if doctype == "Drive Storage Settings" else None
	frappe.get_doc = lambda doctype, name=None: settings_doc if doctype == "Drive Storage Settings" else None
	sys.modules["frappe"] = frappe


def _load_base_module():
	_purge_modules("ifitwala_drive.services.storage.base")
	return importlib.import_module("ifitwala_drive.services.storage.base")


def test_settings_profile_overrides_legacy_conf():
	_install_fake_frappe(
		conf={
			"ifitwala_drive_storage_profile": {
				"backend_name": "local",
				"bucket_or_container": "legacy-bucket",
			}
		},
		settings_doc=FakeDoc(
			{
				"enabled": 1,
				"backend_name": "gcs",
				"storage_mode": "gcs_for_new_writes",
				"bucket_or_container": "drive-bucket",
				"base_prefix": "sites/site-a",
				"project_id": "project-a",
				"credential_source": "adc_or_workload_identity",
				"signing_mode": "gcs_signed_url",
			}
		),
	)
	module = _load_base_module()
	profile = module.resolve_storage_runtime_profile()

	assert profile.backend_name == "gcs"
	assert profile.provider_family == "gcs"
	assert profile.storage_mode == "gcs_for_new_writes"
	assert profile.bucket_or_container == "drive-bucket"
	assert profile.base_prefix == "sites/site-a"
	assert profile.project_id == "project-a"
	assert profile.credential_source == "adc_or_workload_identity"


def test_local_only_settings_disable_legacy_remote_profile():
	_install_fake_frappe(
		conf={
			"ifitwala_drive_storage_profile": {
				"backend_name": "gcs",
				"bucket_or_container": "legacy-bucket",
			}
		},
		settings_doc=FakeDoc(
			{
				"enabled": 1,
				"backend_name": "gcs",
				"storage_mode": "local_only",
				"bucket_or_container": "drive-bucket",
			}
		),
	)
	module = _load_base_module()
	profile = module.resolve_storage_runtime_profile()

	assert profile.backend_name == "local"
	assert profile.provider_family == "local"
	assert profile.storage_mode == "local_only"
	assert profile.bucket_or_container is None


def test_env_override_wins_over_settings():
	previous = os.environ.get("IFITWALA_DRIVE_STORAGE_PROFILE")
	os.environ["IFITWALA_DRIVE_STORAGE_PROFILE"] = (
		'{"backend_name":"gcs","bucket_or_container":"env-bucket","base_prefix":"sites/site-a"}'
	)
	try:
		_install_fake_frappe(
			settings_doc=FakeDoc(
				{
					"enabled": 1,
					"backend_name": "gcs",
					"storage_mode": "gcs_for_new_writes",
					"bucket_or_container": "settings-bucket",
				}
			)
		)
		module = _load_base_module()
		profile = module.resolve_storage_runtime_profile()
	finally:
		if previous is None:
			os.environ.pop("IFITWALA_DRIVE_STORAGE_PROFILE", None)
		else:
			os.environ["IFITWALA_DRIVE_STORAGE_PROFILE"] = previous

	assert profile.backend_name == "gcs"
	assert profile.bucket_or_container == "env-bucket"
	assert profile.base_prefix == "sites/site-a"


def test_settings_profile_rejects_non_site_scoped_base_prefix():
	_install_fake_frappe(
		conf={"site_name": "site-a"},
		settings_doc=FakeDoc(
			{
				"enabled": 1,
				"backend_name": "gcs",
				"storage_mode": "gcs_for_new_writes",
				"bucket_or_container": "drive-bucket",
				"base_prefix": "shared-prefix",
			}
		),
	)
	module = _load_base_module()

	with pytest.raises(
		module.StorageProfileValidationError,
		match="Base Prefix must use the site-scoped shape sites/<site_name>",
	):
		module.resolve_storage_runtime_profile()


def test_settings_profile_rejects_wrong_site_prefix():
	_install_fake_frappe(
		conf={"site_name": "site-a"},
		settings_doc=FakeDoc(
			{
				"enabled": 1,
				"backend_name": "gcs",
				"storage_mode": "gcs_for_new_writes",
				"bucket_or_container": "drive-bucket",
				"base_prefix": "sites/site-b",
			}
		),
	)
	module = _load_base_module()

	with pytest.raises(
		module.StorageProfileValidationError,
		match="Base Prefix must match the current site and use sites/site-a",
	):
		module.resolve_storage_runtime_profile()
