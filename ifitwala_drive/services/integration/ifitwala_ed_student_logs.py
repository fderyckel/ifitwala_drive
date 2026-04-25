from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.files.access import (
	_assert_can_issue_download,
	_assert_can_issue_preview,
	_issue_grant,
)
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module

_ED_MODULE = "ifitwala_ed.integrations.drive.student_logs"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing Student Log delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def build_student_log_evidence_contract(student_log_doc, *, row_name: str | None = None) -> dict[str, Any]:
	return _call_delegate("build_student_log_evidence_contract", student_log_doc, row_name=row_name)


def assert_student_log_upload_access(student_log: str, *, permission_type: str = "write"):
	return _call_delegate("assert_student_log_upload_access", student_log, permission_type=permission_type)


def assert_student_log_evidence_read_access(student_log: str, row_name: str) -> dict[str, Any]:
	return _call_delegate("assert_student_log_evidence_read_access", student_log, row_name)


def validate_student_log_evidence_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_student_log_evidence_finalize_context_for_drive", upload_session_doc)


def get_student_log_evidence_context_override(
	owner_name: str | None,
	slot: str | None,
) -> dict[str, Any] | None:
	return _call_delegate("get_student_log_evidence_context_override_for_drive", owner_name, slot)


def run_student_log_evidence_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate(
		"run_student_log_evidence_post_finalize_for_drive", upload_session_doc, created_file
	)


def _get_authorized_student_log_evidence_drive_file(payload: dict[str, Any]):
	student_log = str(payload.get("student_log") or "").strip()
	row_name = str(payload.get("row_name") or "").strip()
	if not student_log:
		frappe.throw(_("Missing required field: student_log"))
	if not row_name:
		frappe.throw(_("Missing required field: row_name"))

	context = assert_student_log_evidence_read_access(student_log, row_name)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed evidence file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Student Log"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("student_log") or "").strip()
	):
		frappe.throw(_("Governed evidence file ownership is invalid."))

	return context, drive_file_doc


def issue_student_log_evidence_attachment_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_student_log_evidence_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_student_log_evidence_attachment_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_student_log_evidence_drive_file(payload)
	_assert_can_issue_preview(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="preview", payload=payload)


def upload_student_log_evidence_attachment_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	student_log = payload.get("student_log")
	filename_original = payload.get("filename_original")
	provided_row_name = payload.get("row_name")

	if not student_log:
		frappe.throw(_("Missing required field: student_log"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "student_log.evidence_attachment"
	workflow_payload = {
		"student_log": student_log,
		"row_name": provided_row_name,
		"slot": payload.get("slot"),
	}
	return create_upload_session_service(
		{
			"workflow_id": workflow_id,
			"workflow_payload": workflow_payload,
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)
