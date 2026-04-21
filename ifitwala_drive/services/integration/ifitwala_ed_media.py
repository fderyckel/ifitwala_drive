from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.files.access import (
	_assert_can_issue_download,
	_issue_grant,
	_issue_preview_grant_for_doc,
	request_preview_derivatives_for_doc,
)
from ifitwala_drive.services.folders.resolution import (
	resolve_employee_image_folder,
	resolve_guardian_image_folder,
	resolve_organization_media_folder,
	resolve_student_image_folder,
)
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module
from ifitwala_drive.services.integration.ifitwala_ed_bridge import resolve_upload_session_context
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


def assert_employee_image_read_access(employee: str, *, file_name: str) -> dict[str, Any]:
	return _call_delegate("assert_employee_image_read_access", employee, file_name=file_name)


def assert_student_image_read_access(student: str, *, file_name: str) -> dict[str, Any]:
	return _call_delegate("assert_student_image_read_access", student, file_name=file_name)


def assert_guardian_image_read_access(guardian: str, *, file_name: str) -> dict[str, Any]:
	return _call_delegate("assert_guardian_image_read_access", guardian, file_name=file_name)


def assert_public_website_media_read_access(*, file_name: str) -> dict[str, Any]:
	return _call_delegate("assert_public_website_media_read_access", file_name=file_name)


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

	workflow_id = "media.employee_profile_image"
	workflow_payload = {
		"employee": employee,
		"slot": payload.get("slot"),
	}
	employee_doc = frappe.get_doc("Employee", employee)
	employee_doc.check_permission("write")
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	return create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"folder": resolve_employee_image_folder(
				employee=employee_doc.name,
				organization=authoritative["organization"],
				school=authoritative["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
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

	workflow_id = "media.student_profile_image"
	workflow_payload = {
		"student": student,
		"slot": payload.get("slot"),
	}
	student_doc = frappe.get_doc("Student", student)
	student_doc.check_permission("write")
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	return create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"folder": resolve_student_image_folder(
				student=student_doc.name,
				organization=authoritative["organization"],
				school=authoritative["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
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

	workflow_id = "media.guardian_profile_image"
	workflow_payload = {
		"guardian": guardian,
		"slot": payload.get("slot"),
	}
	guardian_doc = frappe.get_doc("Guardian", guardian)
	guardian_doc.check_permission("write")
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	return create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"folder": resolve_guardian_image_folder(
				guardian=guardian_doc.name,
				organization=authoritative["organization"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
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
	workflow_id = "organization_media.organization_logo"
	workflow_payload = {
		"organization": org_doc.name,
		"upload_source": payload.get("upload_source") or "Desk",
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	return create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"folder": resolve_organization_media_folder(
				organization=org_doc.name,
				school=None,
				slot=authoritative["slot"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
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

	workflow_id = "organization_media.school_logo"
	workflow_payload = {
		"school": school_doc.name,
		"upload_source": payload.get("upload_source") or "Desk",
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	return create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
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

	workflow_id = "organization_media.school_gallery_image"
	workflow_payload = {
		"school": school_doc.name,
		"row_name": target_row.name,
		"upload_source": payload.get("upload_source") or "Desk",
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	response = create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"workflow_result": {
				"row_name": target_row.name,
				"caption": getattr(target_row, "caption", None),
			},
			"folder": resolve_organization_media_folder(
				organization=school_doc.organization,
				school=school_doc.name,
				slot=authoritative["slot"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)
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

	workflow_id = "organization_media.asset"
	workflow_payload = {
		"organization": organization,
		"school": school,
		"scope": scope,
		"media_key": media_key,
		"upload_source": payload.get("upload_source") or "Desk",
		"filename_original": filename_original,
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	response = create_upload_session_service(
		{
			**authoritative,
			"workflow_payload": workflow_payload,
			"workflow_result": {
				"organization": organization,
				"school": school,
				"scope": scope,
				"slot": authoritative["slot"],
			},
			"folder": resolve_organization_media_folder(
				organization=organization,
				school=school,
				slot=authoritative["slot"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 0,
			"upload_source": payload.get("upload_source") or "Desk",
		}
	)
	return response


def get_attached_field_override(upload_session_doc) -> str | None:
	return _call_delegate("get_attached_field_override", upload_session_doc)


def validate_media_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_media_finalize_context", upload_session_doc)


def run_media_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_media_post_finalize", upload_session_doc, created_file)


def _get_authorized_employee_image_drive_file(payload: dict[str, Any]):
	employee = str(payload.get("employee") or "").strip()
	file_id = str(payload.get("file_id") or "").strip()
	if not employee:
		frappe.throw(_("Missing required field: employee"))
	if not file_id:
		frappe.throw(_("Missing required field: file_id"))

	context = assert_employee_image_read_access(employee, file_name=file_id)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed employee image file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Employee"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("employee") or "").strip()
	):
		frappe.throw(_("Governed employee image ownership is invalid."))

	return context, drive_file_doc


def _get_authorized_student_image_drive_file(payload: dict[str, Any]):
	student = str(payload.get("student") or "").strip()
	file_id = str(payload.get("file_id") or "").strip()
	if not student:
		frappe.throw(_("Missing required field: student"))
	if not file_id:
		frappe.throw(_("Missing required field: file_id"))

	context = assert_student_image_read_access(student, file_name=file_id)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed student image file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Student"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("student") or "").strip()
	):
		frappe.throw(_("Governed student image ownership is invalid."))

	return context, drive_file_doc


def _get_authorized_guardian_image_drive_file(payload: dict[str, Any]):
	guardian = str(payload.get("guardian") or "").strip()
	file_id = str(payload.get("file_id") or "").strip()
	if not guardian:
		frappe.throw(_("Missing required field: guardian"))
	if not file_id:
		frappe.throw(_("Missing required field: file_id"))

	context = assert_guardian_image_read_access(guardian, file_name=file_id)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed guardian image file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Guardian"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("guardian") or "").strip()
	):
		frappe.throw(_("Governed guardian image ownership is invalid."))

	return context, drive_file_doc


def _get_authorized_public_website_media_drive_file(payload: dict[str, Any]):
	file_id = str(payload.get("file_id") or "").strip()
	if not file_id:
		frappe.throw(_("Missing required field: file_id"))

	context = assert_public_website_media_read_access(file_name=file_id)
	drive_file_id = str(context.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Governed public website media file was not found."))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
	if (
		str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() != "Organization"
		or str(getattr(drive_file_doc, "owner_name", "") or "").strip()
		!= str(context.get("organization") or "").strip()
		or str(getattr(drive_file_doc, "purpose", "") or "").strip() != "organization_public_media"
	):
		frappe.throw(_("Governed public website media ownership is invalid."))

	return context, drive_file_doc


def issue_employee_image_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_employee_image_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_employee_image_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_employee_image_drive_file(payload)
	return _issue_preview_grant_for_doc(doc=drive_file_doc, payload=payload)


def request_employee_image_preview_derivatives_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_employee_image_drive_file(payload)
	return request_preview_derivatives_for_doc(doc=drive_file_doc, payload=payload)


def issue_student_image_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_student_image_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_student_image_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_student_image_drive_file(payload)
	return _issue_preview_grant_for_doc(doc=drive_file_doc, payload=payload)


def request_student_image_preview_derivatives_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_student_image_drive_file(payload)
	return request_preview_derivatives_for_doc(doc=drive_file_doc, payload=payload)


def issue_guardian_image_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_guardian_image_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_guardian_image_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_guardian_image_drive_file(payload)
	return _issue_preview_grant_for_doc(doc=drive_file_doc, payload=payload)


def request_guardian_image_preview_derivatives_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_guardian_image_drive_file(payload)
	return request_preview_derivatives_for_doc(doc=drive_file_doc, payload=payload)


def issue_public_website_media_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_public_website_media_drive_file(payload)
	_assert_can_issue_download(drive_file_doc)
	return _issue_grant(doc=drive_file_doc, grant_kind="download")


def issue_public_website_media_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	_context, drive_file_doc = _get_authorized_public_website_media_drive_file(payload)
	return _issue_preview_grant_for_doc(doc=drive_file_doc, payload=payload)


MEDIA_API_SERVICE_EXPORTS = {
	"issue_employee_image_download_grant": issue_employee_image_download_grant_service,
	"issue_employee_image_preview_grant": issue_employee_image_preview_grant_service,
	"request_employee_image_preview_derivatives": request_employee_image_preview_derivatives_service,
	"issue_guardian_image_download_grant": issue_guardian_image_download_grant_service,
	"issue_guardian_image_preview_grant": issue_guardian_image_preview_grant_service,
	"request_guardian_image_preview_derivatives": request_guardian_image_preview_derivatives_service,
	"issue_public_website_media_download_grant": issue_public_website_media_download_grant_service,
	"issue_public_website_media_preview_grant": issue_public_website_media_preview_grant_service,
	"issue_student_image_download_grant": issue_student_image_download_grant_service,
	"issue_student_image_preview_grant": issue_student_image_preview_grant_service,
	"request_student_image_preview_derivatives": request_student_image_preview_derivatives_service,
	"upload_employee_image": upload_employee_image_service,
	"upload_guardian_image": upload_guardian_image_service,
	"upload_student_image": upload_student_image_service,
	"upload_organization_logo": upload_organization_logo_service,
	"upload_school_logo": upload_school_logo_service,
	"upload_school_gallery_image": upload_school_gallery_image_service,
	"upload_organization_media_asset": upload_organization_media_asset_service,
}
