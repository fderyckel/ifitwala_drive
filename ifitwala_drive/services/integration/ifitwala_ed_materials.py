from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.folders.resolution import resolve_supporting_material_folder
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module

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


def upload_supporting_material_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	material = payload.get("material")
	filename_original = payload.get("filename_original")
	if not material:
		frappe.throw(_("Missing required field: material"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	material_doc = assert_supporting_material_upload_access(material, permission_type="write")
	authoritative = build_supporting_material_upload_contract(material_doc)
	provided_slot = str(payload.get("slot") or "").strip()
	if provided_slot and provided_slot != authoritative["slot"]:
		frappe.throw(
			_("Supporting Material upload currently only supports slot '{0}'.").format(authoritative["slot"])
		)

	return create_upload_session_service(
		{
			**{key: value for key, value in authoritative.items() if key != "course"},
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
