from __future__ import annotations

from typing import Any

import frappe
from frappe import _

_PROFILE_IMAGE_SLOT = "profile_image"


def _require_doc(doctype: str, name: str, *, permission_type: str | None = "write"):
	if not name or not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} does not exist: {1}").format(doctype, name))

	doc = frappe.get_doc(doctype, name)
	if permission_type:
		doc.check_permission(permission_type)
	return doc


def _get_org_from_school(school: str) -> str:
	organization = frappe.db.get_value("School", school, "organization")
	if not organization:
		frappe.throw(_("Organization is required for file classification."))
	return organization


def build_employee_image_contract(employee_doc) -> dict[str, Any]:
	if not getattr(employee_doc, "organization", None):
		frappe.throw(_("Organization is required for file classification."))

	return {
		"owner_doctype": "Employee",
		"owner_name": employee_doc.name,
		"attached_doctype": "Employee",
		"attached_name": employee_doc.name,
		"organization": employee_doc.organization,
		"school": getattr(employee_doc, "school", None),
		"primary_subject_type": "Employee",
		"primary_subject_id": employee_doc.name,
		"data_class": "identity_image",
		"purpose": "employee_profile_display",
		"retention_policy": "employment_duration_plus_grace",
		"slot": _PROFILE_IMAGE_SLOT,
	}


def build_student_image_contract(student_doc) -> dict[str, Any]:
	school = getattr(student_doc, "anchor_school", None)
	if not school:
		frappe.throw(_("Anchor School is required before uploading a student image."))

	return {
		"owner_doctype": "Student",
		"owner_name": student_doc.name,
		"attached_doctype": "Student",
		"attached_name": student_doc.name,
		"organization": _get_org_from_school(school),
		"school": school,
		"primary_subject_type": "Student",
		"primary_subject_id": student_doc.name,
		"data_class": "identity_image",
		"purpose": "student_profile_display",
		"retention_policy": "until_school_exit_plus_6m",
		"slot": _PROFILE_IMAGE_SLOT,
	}


def _build_organization_media_contract(
	*,
	organization: str,
	slot: str,
	school: str | None = None,
	upload_source: str,
) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_organization_media_classification

	classification = build_organization_media_classification(
		organization=organization,
		school=school,
		slot=slot,
		upload_source=upload_source,
	)

	return {
		"owner_doctype": "Organization",
		"owner_name": organization,
		"attached_doctype": "Organization",
		"attached_name": organization,
		"organization": organization,
		"school": school,
		"primary_subject_type": classification["primary_subject_type"],
		"primary_subject_id": classification["primary_subject_id"],
		"data_class": classification["data_class"],
		"purpose": classification["purpose"],
		"retention_policy": classification["retention_policy"],
		"slot": classification["slot"],
	}


def upload_employee_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	employee = payload.get("employee")
	filename_original = payload.get("filename_original")
	if not employee:
		frappe.throw(_("Missing required field: employee"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	employee_doc = _require_doc("Employee", employee)
	authoritative = build_employee_image_contract(employee_doc)
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


def upload_student_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	student = payload.get("student")
	filename_original = payload.get("filename_original")
	if not student:
		frappe.throw(_("Missing required field: student"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	student_doc = _require_doc("Student", student)
	authoritative = build_student_image_contract(student_doc)
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


def upload_organization_logo_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_organization_logo_slot

	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	organization = payload.get("organization")
	filename_original = payload.get("filename_original")
	if not organization:
		frappe.throw(_("Missing required field: organization"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	org_doc = _require_doc("Organization", organization)
	authoritative = _build_organization_media_contract(
		organization=org_doc.name,
		slot=build_organization_logo_slot(organization=org_doc.name),
		school=None,
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


def upload_school_logo_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.utilities.organization_media import build_school_logo_slot

	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	school = payload.get("school")
	filename_original = payload.get("filename_original")
	if not school:
		frappe.throw(_("Missing required field: school"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	school_doc = _require_doc("School", school)
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

	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	school = payload.get("school")
	filename_original = payload.get("filename_original")
	row_name = payload.get("row_name")
	caption = (payload.get("caption") or "").strip()
	if not school:
		frappe.throw(_("Missing required field: school"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	school_doc = _require_doc("School", school)
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

	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	organization = payload.get("organization")
	school = payload.get("school")
	scope = (payload.get("scope") or "organization").strip().lower()
	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	if school and not organization:
		school_doc = _require_doc("School", school)
		organization = school_doc.organization
	elif organization:
		org_doc = _require_doc("Organization", organization)
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
	if (
		upload_session_doc.owner_doctype == "Employee"
		and upload_session_doc.intended_slot == _PROFILE_IMAGE_SLOT
	):
		return "employee_image"
	if (
		upload_session_doc.owner_doctype == "Student"
		and upload_session_doc.intended_slot == _PROFILE_IMAGE_SLOT
	):
		return "student_image"
	return None


def validate_media_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	owner_doctype = getattr(upload_session_doc, "owner_doctype", None)
	if owner_doctype == "Employee":
		doc = _require_doc("Employee", upload_session_doc.owner_name)
		authoritative = build_employee_image_contract(doc)
	elif owner_doctype == "Student":
		doc = _require_doc("Student", upload_session_doc.owner_name)
		authoritative = build_student_image_contract(doc)
	elif owner_doctype == "Organization":
		school = getattr(upload_session_doc, "school", None)
		slot = getattr(upload_session_doc, "intended_slot", None)
		if school:
			_require_doc("School", school)
		else:
			_require_doc("Organization", upload_session_doc.owner_name)
		authoritative = _build_organization_media_contract(
			organization=upload_session_doc.owner_name,
			slot=slot,
			school=school,
			upload_source=upload_session_doc.upload_source,
		)
	else:
		return None

	field_map = {
		"owner_doctype": "owner_doctype",
		"owner_name": "owner_name",
		"attached_doctype": "attached_doctype",
		"attached_name": "attached_name",
		"organization": "organization",
		"school": "school",
		"intended_primary_subject_type": "primary_subject_type",
		"intended_primary_subject_id": "primary_subject_id",
		"intended_data_class": "data_class",
		"intended_purpose": "purpose",
		"intended_retention_policy": "retention_policy",
		"intended_slot": "slot",
	}
	for session_field, authoritative_field in field_map.items():
		if getattr(upload_session_doc, session_field, None) != authoritative.get(authoritative_field):
			frappe.throw(
				_("Upload session no longer matches the authoritative media context for field '{0}'.").format(
					session_field
				)
			)

	return authoritative


def run_media_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	file_url = getattr(created_file, "file_url", None) or frappe.db.get_value(
		"File", created_file.name, "file_url"
	)
	slot = upload_session_doc.intended_slot or ""

	if upload_session_doc.owner_doctype == "Employee":
		frappe.db.set_value(
			"Employee",
			upload_session_doc.owner_name,
			"employee_image",
			file_url,
			update_modified=False,
		)
		return {"file_url": file_url}

	if upload_session_doc.owner_doctype == "Student":
		student_doc = frappe.get_doc("Student", upload_session_doc.owner_name)
		frappe.db.set_value(
			"Student",
			student_doc.name,
			"student_image",
			file_url,
			update_modified=False,
		)
		student_doc.student_image = file_url
		if hasattr(student_doc, "sync_student_contact_image"):
			student_doc.sync_student_contact_image()
		return {"file_url": file_url}

	if upload_session_doc.owner_doctype != "Organization":
		return {}

	if slot.startswith("organization_logo__"):
		frappe.db.set_value(
			"Organization",
			upload_session_doc.owner_name,
			{
				"organization_logo": file_url,
				"organization_logo_file": created_file.name,
			},
			update_modified=False,
		)
		return {"file_url": file_url}

	if slot.startswith("school_logo__"):
		frappe.db.set_value(
			"School",
			upload_session_doc.school,
			{
				"school_logo": file_url,
				"school_logo_file": created_file.name,
			},
			update_modified=False,
		)
		return {"file_url": file_url}

	if slot.startswith("school_gallery_image__"):
		row_name = slot.split("school_gallery_image__", 1)[1]
		school_doc = frappe.get_doc("School", upload_session_doc.school)
		target_row = None
		for row in school_doc.gallery_image or []:
			if row.name == row_name:
				target_row = row
				break
		if not target_row:
			frappe.throw(
				_("Gallery row '{0}' was not found on School '{1}'.").format(row_name, school_doc.name)
			)
		target_row.governed_file = created_file.name
		target_row.school_image = file_url
		school_doc.save(ignore_permissions=True)
		return {"file_url": file_url, "row_name": row_name}

	return {"file_url": file_url}
