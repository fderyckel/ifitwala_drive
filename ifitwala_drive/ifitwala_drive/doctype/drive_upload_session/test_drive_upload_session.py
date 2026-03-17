# ifitwala_drive/ifitwala_drive/doctype/drive_upload_session/test_drive_upload_session.py

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta

import pytest


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe(*, exists_map: dict[tuple[str, object], object] | None = None):
	exists_map = exists_map or {}
	now = datetime(2026, 3, 17, 9, 0, 0)

	class FrappeError(Exception):
		pass

	class FakeDB:
		def exists(self, doctype, name=None):
			key = (doctype, name)
			return exists_map.get(key, False)

	def _throw(message):
		raise FrappeError(message)

	def _identity(message):
		return message

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = _identity
	frappe.db = FakeDB()
	frappe.session = types.SimpleNamespace(user="student@example.com")
	frappe.local = types.SimpleNamespace(request_ip="127.0.0.1")
	frappe.generate_hash = lambda length=24: "x" * length
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.get_doc = lambda *args, **kwargs: None
	frappe.get_cached_doc = lambda *args, **kwargs: None
	frappe.log_error = lambda *args, **kwargs: None
	frappe.get_traceback = lambda: "traceback"
	frappe.as_json = lambda value, indent=None: str(value)
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: now
	utils.get_datetime = lambda value: value
	utils.add_to_date = lambda value, hours=0, as_datetime=False: value + timedelta(hours=hours)

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		def __init__(self, data=None):
			for key, value in (data or {}).items():
				setattr(self, key, value)

		def get(self, key, default=None):
			return getattr(self, key, default)

	document.Document = Document

	frappe.utils = utils

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document

	return FrappeError


def _load_validation_module():
	_purge_modules("ifitwala_drive.services.uploads.validation")
	return importlib.import_module("ifitwala_drive.services.uploads.validation")


def _valid_payload():
	return {
		"owner_doctype": "Task Submission",
		"owner_name": "TSUB-0001",
		"attached_doctype": "Task Submission",
		"attached_name": "TSUB-0001",
		"organization": "ORG-0001",
		"school": "SCH-0001",
		"primary_subject_type": "Student",
		"primary_subject_id": "STU-0001",
		"data_class": "assessment",
		"purpose": "assessment_submission",
		"retention_policy": "until_school_exit_plus_6m",
		"slot": "submission",
		"filename_original": "essay.docx",
	}


def test_missing_slot_fails():
	FrappeError = _install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
			("Task Submission", "TSUB-0001"): True,
		}
	)
	validation = _load_validation_module()
	payload = _valid_payload()
	payload.pop("slot")

	with pytest.raises(FrappeError, match="Missing required field: slot"):
		validation.validate_create_session_payload(payload)


def test_invalid_owner_fails():
	FrappeError = _install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
			("Task Submission", "TSUB-0001"): True,
		}
	)
	validation = _load_validation_module()
	payload = _valid_payload()
	payload["owner_doctype"] = "User"
	payload["owner_name"] = "student@example.com"

	with pytest.raises(FrappeError, match="Owner Doctype cannot be User"):
		validation.validate_create_session_payload(payload)
