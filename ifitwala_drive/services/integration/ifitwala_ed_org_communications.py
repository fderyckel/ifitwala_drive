from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.files.access import (
	_assert_can_issue_download,
	_assert_can_issue_preview,
	_issue_grant,
)
from ifitwala_drive.services.folders.resolution import resolve_org_communication_attachment_folder
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module
from ifitwala_drive.services.integration.ifitwala_ed_bridge import resolve_upload_session_context

_ED_MODULE = "ifitwala_ed.integrations.drive.org_communications"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing org-communication delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def build_org_communication_upload_contract(
	org_communication_doc,
	*,
	row_name: str | None = None,
) -> dict[str, Any]:
	return _call_delegate("build_org_communication_upload_contract", org_communication_doc, row_name=row_name)


def assert_org_communication_upload_access(org_communication: str, *, permission_type: str = "write"):
	return _call_delegate(
		"assert_org_communication_upload_access", org_communication, permission_type=permission_type
	)


def assert_org_communication_attachment_read_access(
	org_communication: str,
	row_name: str,
) -> dict[str, Any]:
	return _call_delegate("assert_org_communication_attachment_read_access", org_communication, row_name)


def validate_org_communication_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_org_communication_finalize_context", upload_session_doc)


def get_org_communication_attachment_context_override(
	owner_name: str | None,
	slot: str | None,
) -> dict[str, Any] | None:
	return _call_delegate("get_org_communication_attachment_context_override", owner_name, slot)


def run_org_communication_attachment_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_org_communication_attachment_post_finalize", upload_session_doc, created_file)


def _get_authorized_org_communication_attachment_drive_file(payload: dict[str, Any]):
	org_communication = str(payload.get("org_communication") or "").strip()
	row_name = str(payload.get("row_name") or "").strip()
	if not org_communication:
		frappe.throw(_("Missing required field: org_communication"))
	if not row_name:
		frappe.throw(_("Missing required field: row_name"))

	context = assert_org_communication_attachment_read_access(org_communication, row_name)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed attachment file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Org Communication"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("org_communication") or "").strip()
	):
		frappe.throw(_("Governed attachment file ownership is invalid."))

	return context, drive_file_doc


def issue_org_communication_attachment_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_org_communication_attachment_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_org_communication_attachment_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_org_communication_attachment_drive_file(payload)
	_assert_can_issue_preview(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="preview", payload=payload)


def upload_org_communication_attachment_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	org_communication = payload.get("org_communication")
	filename_original = payload.get("filename_original")
	provided_row_name = payload.get("row_name")

	if not org_communication:
		frappe.throw(_("Missing required field: org_communication"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "org_communication.attachment"
	workflow_payload = {
		"org_communication": org_communication,
		"row_name": provided_row_name,
		"slot": payload.get("slot"),
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	org_communication_doc = assert_org_communication_upload_access(org_communication, permission_type="write")

	response = create_upload_session_service(
		{
			**{
				key: value
				for key, value in authoritative.items()
				if key not in {"row_name", "course", "student_group"}
			},
			"workflow_payload": workflow_payload,
			"workflow_result": {
				"row_name": authoritative["row_name"],
				"slot": authoritative["slot"],
			},
			"folder": resolve_org_communication_attachment_folder(
				org_communication=org_communication_doc.name,
				course=authoritative["course"],
				student_group=authoritative["student_group"],
				organization=authoritative["organization"],
				school=authoritative["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	return response
