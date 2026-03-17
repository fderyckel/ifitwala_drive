from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def _get_applicant_document_context(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_ed.admission import admissions_portal as admission_api
	from ifitwala_ed.admission.admission_utils import get_applicant_document_slot_spec

	student_applicant = payload.get("student_applicant")
	document_type = payload.get("document_type")
	applicant_document_item = payload.get("applicant_document_item")
	item_key = payload.get("item_key")
	item_label = payload.get("item_label")

	if not student_applicant:
		frappe.throw(_("Missing required field: student_applicant"))
	if not document_type and not applicant_document_item:
		frappe.throw(_("Missing required field: document_type"))

	doc = admission_api._resolve_applicant_document(
		applicant_document=payload.get("applicant_document"),
		student_applicant=student_applicant,
		document_type=document_type,
	)
	item_doc = admission_api._resolve_applicant_document_item(
		applicant_document=doc,
		applicant_document_item=applicant_document_item,
		item_key=item_key,
		item_label=item_label,
		fallback_label=payload.get("filename_original"),
	)

	doc_type_code = (
		frappe.db.get_value("Applicant Document Type", doc.document_type, "code") or doc.document_type
	)
	slot_spec = get_applicant_document_slot_spec(document_type=doc.document_type, doc_type_code=doc_type_code)
	if not slot_spec:
		frappe.throw(
			_("Applicant Document Type is missing upload classification settings: {0}.").format(doc_type_code)
		)

	applicant_row = (
		frappe.db.get_value(
			"Student Applicant",
			doc.student_applicant,
			["organization", "school"],
			as_dict=True,
		)
		or {}
	)
	if not applicant_row.get("organization") or not applicant_row.get("school"):
		frappe.throw(_("Student Applicant must have organization and school."))

	item_slot_key = f"{slot_spec['slot']}_{frappe.scrub(item_doc.item_key)[:80]}"
	return {
		"owner_doctype": "Student Applicant",
		"owner_name": doc.student_applicant,
		"attached_doctype": "Applicant Document Item",
		"attached_name": item_doc.name,
		"organization": applicant_row.get("organization"),
		"school": applicant_row.get("school"),
		"primary_subject_type": "Student Applicant",
		"primary_subject_id": doc.student_applicant,
		"data_class": slot_spec["data_class"],
		"purpose": slot_spec["purpose"],
		"retention_policy": slot_spec["retention_policy"],
		"slot": item_slot_key,
		"applicant_document": doc.name,
		"applicant_document_item": item_doc.name,
		"item_key": item_doc.item_key,
		"item_label": item_doc.item_label,
		"document_type": doc.document_type,
		"document_type_code": doc_type_code,
	}


def upload_applicant_document_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	context = _get_applicant_document_context(payload)
	response = create_upload_session_service(
		{
			"owner_doctype": context["owner_doctype"],
			"owner_name": context["owner_name"],
			"attached_doctype": context["attached_doctype"],
			"attached_name": context["attached_name"],
			"organization": context["organization"],
			"school": context["school"],
			"primary_subject_type": context["primary_subject_type"],
			"primary_subject_id": context["primary_subject_id"],
			"data_class": context["data_class"],
			"purpose": context["purpose"],
			"retention_policy": context["retention_policy"],
			"slot": context["slot"],
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	response.update(
		{
			"applicant_document": context["applicant_document"],
			"applicant_document_item": context["applicant_document_item"],
			"item_key": context["item_key"],
			"item_label": context["item_label"],
		}
	)
	return response


def validate_applicant_document_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	if (
		getattr(upload_session_doc, "owner_doctype", None) != "Student Applicant"
		or getattr(upload_session_doc, "attached_doctype", None) != "Applicant Document Item"
	):
		return None

	context = _get_applicant_document_context(
		{
			"student_applicant": upload_session_doc.owner_name,
			"applicant_document_item": upload_session_doc.attached_name,
		}
	)
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
	for session_field, context_field in field_map.items():
		if getattr(upload_session_doc, session_field, None) != context.get(context_field):
			frappe.throw(
				_(
					"Upload session no longer matches the authoritative admissions context for field '{0}'."
				).format(session_field)
			)
	return context


def run_admissions_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	if (
		getattr(upload_session_doc, "owner_doctype", None) != "Student Applicant"
		or getattr(upload_session_doc, "attached_doctype", None) != "Applicant Document Item"
	):
		return {}

	from ifitwala_ed.admission import admissions_portal as admission_api
	from ifitwala_ed.admission.applicant_review_workflow import materialize_document_item_review_assignments
	from ifitwala_ed.admission.doctype.applicant_document.applicant_document import (
		sync_applicant_document_review_from_items,
	)

	item_row = (
		frappe.db.get_value(
			"Applicant Document Item",
			upload_session_doc.attached_name,
			["applicant_document", "item_key", "item_label"],
			as_dict=True,
		)
		or {}
	)
	applicant_document = item_row.get("applicant_document")
	if not applicant_document:
		frappe.throw(
			_("Applicant Document Item '{0}' is missing its parent document.").format(
				upload_session_doc.attached_name
			)
		)

	document_type = frappe.db.get_value("Applicant Document", applicant_document, "document_type")
	document_type_code = (
		frappe.db.get_value("Applicant Document Type", document_type, "code") or document_type
	)
	file_url = getattr(created_file, "file_url", None) or frappe.db.get_value(
		"File", created_file.name, "file_url"
	)

	frappe.db.set_value(
		"Applicant Document Item",
		upload_session_doc.attached_name,
		{
			"review_status": "Pending",
			"review_notes": None,
			"reviewed_by": None,
			"reviewed_on": None,
		},
		update_modified=False,
	)
	sync_applicant_document_review_from_items(applicant_document)
	admission_api._append_document_upload_timeline(
		student_applicant=upload_session_doc.owner_name,
		applicant_document=applicant_document,
		applicant_document_item=upload_session_doc.attached_name,
		item_key=item_row.get("item_key"),
		item_label=item_row.get("item_label"),
		document_type=document_type,
		document_type_code=document_type_code,
		file_url=file_url,
		upload_source=upload_session_doc.upload_source,
		action="uploaded",
	)
	materialize_document_item_review_assignments(
		applicant_document_item=upload_session_doc.attached_name,
		source_event="document_item_uploaded",
	)

	return {
		"file_url": file_url,
		"classification": frappe.db.get_value("File Classification", {"file": created_file.name}, "name"),
		"applicant_document": applicant_document,
		"applicant_document_item": upload_session_doc.attached_name,
		"item_key": item_row.get("item_key"),
		"item_label": item_row.get("item_label"),
	}
