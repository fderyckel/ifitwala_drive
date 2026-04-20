from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.files.access import (
	_assert_can_issue_download,
	_assert_can_issue_preview,
	_issue_grant,
)
from ifitwala_drive.services.folders.resolution import resolve_supporting_material_folder
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module
from ifitwala_drive.services.integration.ifitwala_ed_bridge import resolve_upload_session_context

_ED_MODULE = "ifitwala_ed.integrations.drive.materials"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing materials delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def build_supporting_material_upload_contract(material_doc) -> dict[str, Any]:
	return _call_delegate("build_supporting_material_upload_contract", material_doc)


def assert_supporting_material_upload_access(material: str, *, permission_type: str = "write"):
	return _call_delegate(
		"assert_supporting_material_upload_access",
		material,
		permission_type=permission_type,
	)


def assert_supporting_material_read_access(
	material: str,
	*,
	placement: str | None = None,
	drive_file_id: str | None = None,
) -> dict[str, Any]:
	delegate_kwargs = {}
	if placement is not None:
		delegate_kwargs["placement"] = placement
	if drive_file_id is not None:
		delegate_kwargs["drive_file_id"] = drive_file_id
	return _call_delegate("assert_supporting_material_read_access", material, **delegate_kwargs)


def _get_authorized_supporting_material_drive_file(payload: dict[str, Any]):
	material = str(payload.get("material") or "").strip()
	placement = str(payload.get("placement") or "").strip() or None
	drive_file_id = str(payload.get("drive_file_id") or "").strip() or None
	if not material:
		frappe.throw(_("Missing required field: material"))

	context = assert_supporting_material_read_access(
		material,
		placement=placement,
		drive_file_id=drive_file_id,
	)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed attachment file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Supporting Material"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("material") or "").strip()
	):
		frappe.throw(_("Governed attachment file ownership is invalid."))

	return context, drive_file_doc


def issue_supporting_material_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_supporting_material_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_supporting_material_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_supporting_material_drive_file(payload)
	_assert_can_issue_preview(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="preview", payload=payload)


def upload_supporting_material_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	material = payload.get("material")
	filename_original = payload.get("filename_original")
	if not material:
		frappe.throw(_("Missing required field: material"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "supporting_material.file"
	workflow_payload = {
		"material": material,
		"slot": payload.get("slot"),
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	material_doc = assert_supporting_material_upload_access(material, permission_type="write")

	return create_upload_session_service(
		{
			**{key: value for key, value in authoritative.items() if key != "course"},
			"workflow_payload": workflow_payload,
			"folder": resolve_supporting_material_folder(
				material=material_doc.name,
				course=authoritative["course"],
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
