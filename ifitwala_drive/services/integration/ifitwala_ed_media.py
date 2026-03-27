from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.folders.resolution import (
	resolve_employee_image_folder,
	resolve_guardian_image_folder,
	resolve_organization_media_folder,
	resolve_student_image_folder,
)
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module
from ifitwala_drive.services.uploads.sessions import create_upload_session_service

_ED_MODULE = "ifitwala_ed.integrations.drive.media"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing media delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def build_employee_image_contract(employee_doc) -> dict[str, Any]:
	return _call_delegate("build_employee_image_contract", employee_doc)


def build_student_image_contract(student_doc) -> dict[str, Any]:
	return _call_delegate("build_student_image_contract", student_doc)


def build_guardian_image_contract(guardian_doc) -> dict[str, Any]:
	return _call_delegate("build_guardian_image_contract", guardian_doc)


def _build_organization_media_contract(
	*,
	organization: str,
	slot: str,
	school: str | None = None,
	upload_source: str,
) -> dict[str, Any]:
	return _call_delegate(
		"build_organization_media_contract",
		organization=organization,
		slot=slot,
		school=school,
		upload_source=upload_source,
	)


def upload_employee_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	employee = payload.get("employee")
	filename_original = payload.get("filename_original")
	if not employee:
		frappe.throw(_("Missing required field: employee"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	employee_doc = frappe.get_doc("Employee", employee)
	employee_doc.check_permission("write")
	authoritative = build_employee_image_contract(employee_doc)
	return create_upload_session_service(
		{
			**authoritative,
			"folder": resolve_employee_image_folder(
				employee=employee_doc.name,
				organization=authoritative["organization"],
				school=authoritative["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)


def upload_student_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	student = payload.get("student")
	filename_original = payload.get("filename_original")
	if not student:
		frappe.throw(_("Missing required field: student"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	student_doc = frappe.get_doc("Student", student)
	student_doc.check_permission("write")
	authoritative = build_student_image_contract(student_doc)
	return create_upload_session_service(
		{
			**authoritative,
			"folder": resolve_student_image_folder(
				student=student_doc.name,
				organization=authoritative["organization"],
				school=authoritative["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)


def upload_guardian_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	guardian = payload.get("guardian")
	filename_original = payload.get("filename_original")
	if not guardian:
		frappe.throw(_("Missing required field: guardian"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	guardian_doc = frappe.get_doc("Guardian", guardian)
	guardian_doc.check_permission("write")
	authoritative = build_guardian_image_contract(guardian_doc)
	return create_upload_session_service(
		{
			**authoritative,
			"folder": resolve_guardian_image_folder(
				guardian=guardian_doc.name,
				organization=authoritative["organization"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)


def upload_organization_logo_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_organization_logo_slot

	organization = payload.get("organization")
	filename_original = payload.get("filename_original")
	if not organization:
		frappe.throw(_("Missing required field: organization"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	org_doc = frappe.get_doc("Organization", organization)
	org_doc.check_permission("write")
	authoritative = _build_organization_media_contract(
		organization=org_doc.name,
		slot=build_organization_logo_slot(organization=org_doc.name),
		school=None,
		upload_source=payload.get("upload_source") or "Desk",
	)
	return create_upload_session_service(
		{
			**authoritative,
			"folder": resolve_organization_media_folder(
				organization=org_doc.name,
				school=None,
				slot=authoritative["slot"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)


def upload_school_logo_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_school_logo_slot

	school = payload.get("school")
	filename_original = payload.get("filename_original")
	if not school:
		frappe.throw(_("Missing required field: school"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	school_doc = frappe.get_doc("School", school)
	school_doc.check_permission("write")
	if not getattr(school_doc, "organization", None):
		frappe.throw(_("Organization is required before uploading a school logo."))

	authoritative = _build_organization_media_contract(
		organization=school_doc.organization,
		slot=build_school_logo_slot(school=school_doc.name),
		school=school_doc.name,
		upload_source=payload.get("upload_source") or "Desk",
	)
	return create_upload_session_service(
		{
			**authoritative,
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)


def upload_school_gallery_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_school_gallery_slot

	school = payload.get("school")
	filename_original = payload.get("filename_original")
	row_name = payload.get("row_name")
	caption = (payload.get("caption") or "").strip()
	if not school:
		frappe.throw(_("Missing required field: school"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	school_doc = frappe.get_doc("School", school)
	school_doc.check_permission("write")
	if not getattr(school_doc, "organization", None):
		frappe.throw(_("Organization is required before uploading a gallery image."))

	target_row = None
	if row_name:
		for row in school_doc.gallery_image or []:
			if row.name == row_name:
				target_row = row
				break
		if not target_row:
			frappe.throw(
				_("Gallery row '{0}' was not found on School '{1}'.").format(row_name, school_doc.name)
			)
	else:
		target_row = school_doc.append("gallery_image", {})
		if not target_row.name:
			target_row.name = frappe.generate_hash(length=10)
		if caption:
			target_row.caption = caption
		school_doc.save(ignore_permissions=True)

	authoritative = _build_organization_media_contract(
		organization=school_doc.organization,
		slot=build_school_gallery_slot(row_name=target_row.name),
		school=school_doc.name,
		upload_source=payload.get("upload_source") or "Desk",
	)
	response = create_upload_session_service(
		{
			**authoritative,
			"folder": resolve_organization_media_folder(
				organization=school_doc.organization,
				school=school_doc.name,
				slot=authoritative["slot"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)
	response["row_name"] = target_row.name
	response["caption"] = getattr(target_row, "caption", None)
	return response


def upload_organization_media_asset_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_organization_media_slot

	organization = payload.get("organization")
	school = payload.get("school")
	scope = (payload.get("scope") or "organization").strip().lower()
	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	if school and not organization:
		school_doc = frappe.get_doc("School", school)
		school_doc.check_permission("write")
		organization = school_doc.organization
	elif organization:
		org_doc = frappe.get_doc("Organization", organization)
		org_doc.check_permission("write")
		organization = org_doc.name

	if not organization:
		frappe.throw(_("Organization is required before uploading organization media."))
	if scope not in {"organization", "school"}:
		frappe.throw(_("Scope must be 'organization' or 'school'."))
	if scope == "school" and not school:
		frappe.throw(_("School is required for school-scoped organization media."))
	if scope == "organization":
		school = None

	media_key = (payload.get("media_key") or "").strip()
	if not media_key:
		base_name = (payload.get("filename_original") or "media").rsplit(".", 1)[0]
		media_key = f"{frappe.scrub(base_name) or 'media'}_{frappe.generate_hash(length=6)}"

	authoritative = _build_organization_media_contract(
		organization=organization,
		slot=build_organization_media_slot(media_key=media_key),
		school=school,
		upload_source=payload.get("upload_source") or "Desk",
	)
	response = create_upload_session_service(
		{
			**authoritative,
			"folder": resolve_organization_media_folder(
				organization=organization,
				school=school,
				slot=authoritative["slot"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)
	response["organization"] = organization
	response["school"] = school
	response["scope"] = scope
	response["slot"] = authoritative["slot"]
	return response


def get_attached_field_override(upload_session_doc) -> str | None:
	return _call_delegate("get_attached_field_override", upload_session_doc)


def validate_media_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_media_finalize_context", upload_session_doc)


def run_media_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_media_post_finalize", upload_session_doc, created_file)


MEDIA_API_SERVICE_EXPORTS = {
	"upload_employee_image": upload_employee_image_service,
	"upload_guardian_image": upload_guardian_image_service,
	"upload_student_image": upload_student_image_service,
	"upload_organization_logo": upload_organization_logo_service,
	"upload_school_logo": upload_school_logo_service,
	"upload_school_gallery_image": upload_school_gallery_image_service,
	"upload_organization_media_asset": upload_organization_media_asset_service,
}
