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
	_purge_modules(
		"ifitwala_drive.services.governance_contract",
		"ifitwala_drive.services.uploads.validation",
		"ifitwala_drive.services.uploads.slots",
	)
	return importlib.import_module("ifitwala_drive.services.uploads.validation")


def _load_upload_session_doctype_module():
	_purge_modules(
		"ifitwala_drive.services.governance_contract",
		"ifitwala_drive.ifitwala_drive.doctype.drive_upload_session.drive_upload_session",
	)
	return importlib.import_module(
		"ifitwala_drive.ifitwala_drive.doctype.drive_upload_session.drive_upload_session"
	)


def _load_drive_file_doctype_module():
	_purge_modules(
		"ifitwala_drive.services.governance_contract",
		"ifitwala_drive.ifitwala_drive.doctype.drive_file.drive_file",
	)
	return importlib.import_module("ifitwala_drive.ifitwala_drive.doctype.drive_file.drive_file")


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


def test_unknown_slot_fails():
	FrappeError = _install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
			("Task Submission", "TSUB-0001"): True,
		}
	)
	validation = _load_validation_module()
	payload = _valid_payload()
	payload["slot"] = "freeform_slot"

	with pytest.raises(FrappeError, match="canonical Drive slot registry"):
		validation.validate_create_session_payload(payload)


@pytest.mark.parametrize(
	"slot",
	(
		"feedback",
		"rubric_evidence",
		"feedback_export__released__student",
		"portfolio_export_pdf",
		"journal_export_pdf",
		"identity_passport_passport_copy",
		"admissions_identity_passport_passport_copy",
		"communication_attachment__row-001",
		"organization_media__homepage_hero",
		"health_vaccination_proof_mmr_2020-03-04",
		"student_log_evidence__row-001",
	),
)
def test_registry_slots_pass(slot: str):
	_install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
			("Task Submission", "TSUB-0001"): True,
		}
	)
	validation = _load_validation_module()
	payload = _valid_payload()
	payload["slot"] = slot

	validation.validate_create_session_payload(payload)
	assert payload["slot"] == slot


def test_learning_resource_purpose_passes():
	_install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
			("Task", "TASK-0001"): True,
		}
	)
	validation = _load_validation_module()
	payload = {
		"owner_doctype": "Task",
		"owner_name": "TASK-0001",
		"attached_doctype": "Task",
		"attached_name": "TASK-0001",
		"organization": "ORG-0001",
		"school": "SCH-0001",
		"primary_subject_type": "Organization",
		"primary_subject_id": "ORG-0001",
		"data_class": "academic",
		"purpose": "learning_resource",
		"retention_policy": "until_program_end_plus_1y",
		"slot": "supporting_material__row-001",
		"filename_original": "worksheet.pdf",
	}

	validation.validate_create_session_payload(payload)
	assert payload["purpose"] == "learning_resource"


def test_unknown_purpose_fails():
	FrappeError = _install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("School", "SCH-0001"): True,
			("Task Submission", "TSUB-0001"): True,
		}
	)
	validation = _load_validation_module()
	payload = _valid_payload()
	payload["purpose"] = "made_up_purpose"

	with pytest.raises(FrappeError, match='Purpose cannot be "made_up_purpose"'):
		validation.validate_create_session_payload(payload)


def test_drive_upload_session_rejects_unknown_intended_purpose():
	FrappeError = _install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("User", "student@example.com"): True,
		}
	)
	module = _load_upload_session_doctype_module()
	doc = module.DriveUploadSession(
		{
			"attached_doctype": "Supporting Material",
			"attached_name": "MAT-0001",
			"owner_doctype": "Supporting Material",
			"owner_name": "MAT-0001",
			"organization": "ORG-0001",
			"filename_original": "worksheet.pdf",
			"session_key": None,
			"upload_token": None,
			"created_by_user": None,
			"status": None,
			"is_private": None,
			"expires_on": None,
			"received_size_bytes": None,
			"intended_primary_subject_type": "Organization",
			"intended_primary_subject_id": "ORG-0001",
			"intended_data_class": "academic",
			"intended_purpose": "made_up_purpose",
			"intended_retention_policy": "until_program_end_plus_1y",
			"intended_slot": "material_file",
		}
	)

	with pytest.raises(FrappeError, match='Intended Purpose cannot be "made_up_purpose"'):
		doc.validate()


def test_drive_file_accepts_learning_resource():
	_install_fake_frappe(
		exists_map={
			("File", "FILE-0001"): True,
			("Drive Upload Session", "DUS-0001"): True,
			("Organization", "ORG-0001"): True,
		}
	)
	module = _load_drive_file_doctype_module()
	doc = module.DriveFile(
		{
			"file": "FILE-0001",
			"source_upload_session": "DUS-0001",
			"display_name": None,
			"attached_doctype": "Supporting Material",
			"attached_name": "MAT-0001",
			"owner_doctype": "Supporting Material",
			"owner_name": "MAT-0001",
			"organization": "ORG-0001",
			"status": None,
			"preview_status": None,
			"current_version_no": None,
			"is_private": None,
			"legal_hold": None,
			"erasure_state": None,
			"primary_subject_type": "Organization",
			"primary_subject_id": "ORG-0001",
			"data_class": "academic",
			"purpose": "learning_resource",
			"retention_policy": "until_program_end_plus_1y",
			"slot": "material_file",
			"storage_backend": "local",
			"storage_object_key": "drive/materials/worksheet.pdf",
			"upload_source": "SPA",
		}
	)

	doc.validate()
	assert doc.purpose == "learning_resource"
