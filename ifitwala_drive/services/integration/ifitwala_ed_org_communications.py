from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.folders.resolution import resolve_org_communication_attachment_folder
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module

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


def validate_org_communication_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_org_communication_finalize_context", upload_session_doc)


def get_org_communication_attachment_context_override(
	owner_name: str | None,
	slot: str | None,
) -> dict[str, Any] | None:
	return _call_delegate("get_org_communication_attachment_context_override", owner_name, slot)


def run_org_communication_attachment_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_org_communication_attachment_post_finalize", upload_session_doc, created_file)


def upload_org_communication_attachment_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	org_communication = payload.get("org_communication")
	filename_original = payload.get("filename_original")
	provided_row_name = payload.get("row_name")

	if not org_communication:
		frappe.throw(_("Missing required field: org_communication"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	org_communication_doc = assert_org_communication_upload_access(org_communication, permission_type="write")
	authoritative = build_org_communication_upload_contract(
		org_communication_doc,
		row_name=provided_row_name,
	)
	provided_slot = str(payload.get("slot") or "").strip()
	if provided_slot and provided_slot != authoritative["slot"]:
		frappe.throw(_("Org Communication attachment slot does not match the authoritative row context."))

	response = create_upload_session_service(
		{
			**{
				key: value
				for key, value in authoritative.items()
				if key not in {"row_name", "course", "student_group"}
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
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	response["row_name"] = authoritative["row_name"]
	response["slot"] = authoritative["slot"]
	return response
