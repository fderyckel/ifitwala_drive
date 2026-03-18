from __future__ import annotations

from typing import Any

import frappe


def _build_canonical_ref(*, organization: str | None, drive_file_id: str) -> str:
	scope = (organization or "unknown").strip() or "unknown"
	return f"drv:{scope}:{drive_file_id}"


def _resolve_binding_role(upload_session_doc) -> str | None:
	if upload_session_doc.owner_doctype == "Task Submission":
		return "submission_artifact"

	if upload_session_doc.owner_doctype == "Organization":
		return "organization_media"

	if upload_session_doc.owner_doctype == "Student" and upload_session_doc.intended_slot == "profile_image":
		return "student_image"

	if upload_session_doc.owner_doctype == "Employee" and upload_session_doc.intended_slot == "profile_image":
		return "employee_image"

	if upload_session_doc.owner_doctype == "Student Applicant":
		if upload_session_doc.attached_doctype == "Applicant Document Item":
			return "applicant_document"
		return "general_reference"

	return None


def _build_drive_file_doc(upload_session_doc, *, file_id: str, storage_artifact: dict[str, Any]):
	return frappe.get_doc(
		{
			"doctype": "Drive File",
			"file": file_id,
			"status": "active",
			"preview_status": "pending",
			"display_name": upload_session_doc.filename_original,
			"folder": getattr(upload_session_doc, "folder", None),
			"attached_doctype": upload_session_doc.attached_doctype,
			"attached_name": upload_session_doc.attached_name,
			"owner_doctype": upload_session_doc.owner_doctype,
			"owner_name": upload_session_doc.owner_name,
			"organization": upload_session_doc.organization,
			"school": getattr(upload_session_doc, "school", None),
			"primary_subject_type": upload_session_doc.intended_primary_subject_type,
			"primary_subject_id": upload_session_doc.intended_primary_subject_id,
			"data_class": upload_session_doc.intended_data_class,
			"purpose": upload_session_doc.intended_purpose,
			"retention_policy": upload_session_doc.intended_retention_policy,
			"slot": upload_session_doc.intended_slot,
			"current_version_no": 0,
			"storage_backend": storage_artifact.get("storage_backend")
			or getattr(upload_session_doc, "storage_backend", None),
			"storage_object_key": storage_artifact["object_key"],
			"upload_source": upload_session_doc.upload_source,
			"content_hash": getattr(upload_session_doc, "content_hash", None),
			"is_private": upload_session_doc.is_private,
		}
	)


def _build_drive_file_version_doc(
	drive_file_id: str,
	upload_session_doc,
	*,
	file_id: str,
	storage_artifact: dict[str, Any],
):
	size_bytes = (
		getattr(upload_session_doc, "received_size_bytes", None)
		or getattr(upload_session_doc, "expected_size_bytes", None)
		or 0
	)
	return frappe.get_doc(
		{
			"doctype": "Drive File Version",
			"drive_file": drive_file_id,
			"version_no": 1,
			"file": file_id,
			"is_current": 1,
			"version_reason": "initial_upload",
			"storage_object_key": storage_artifact["object_key"],
			"size_bytes": size_bytes,
			"mime_type": getattr(upload_session_doc, "mime_type_hint", None),
			"content_hash": getattr(upload_session_doc, "content_hash", None),
		}
	)


def _create_primary_binding(*, drive_file_id: str, file_id: str, upload_session_doc) -> str | None:
	binding_role = _resolve_binding_role(upload_session_doc)
	if not binding_role:
		return None

	binding = frappe.get_doc(
		{
			"doctype": "Drive Binding",
			"drive_file": drive_file_id,
			"file": file_id,
			"status": "active",
			"binding_doctype": upload_session_doc.attached_doctype,
			"binding_name": upload_session_doc.attached_name,
			"binding_role": binding_role,
			"slot": upload_session_doc.intended_slot,
			"is_primary": 1,
			"sort_order": 0,
			"organization": upload_session_doc.organization,
			"school": getattr(upload_session_doc, "school", None),
		}
	)
	binding.insert(ignore_permissions=True)
	return binding.name


def create_drive_file_artifacts(
	*,
	upload_session_doc,
	file_id: str,
	storage_artifact: dict[str, Any],
) -> dict[str, Any]:
	drive_file = _build_drive_file_doc(
		upload_session_doc,
		file_id=file_id,
		storage_artifact=storage_artifact,
	)
	drive_file.insert(ignore_permissions=True)

	drive_file_version = _build_drive_file_version_doc(
		drive_file.name,
		upload_session_doc,
		file_id=file_id,
		storage_artifact=storage_artifact,
	)
	drive_file_version.insert(ignore_permissions=True)

	drive_file.current_version = drive_file_version.name
	drive_file.current_version_no = 1
	drive_file.canonical_ref = _build_canonical_ref(
		organization=getattr(upload_session_doc, "organization", None),
		drive_file_id=drive_file.name,
	)
	drive_file.save(ignore_permissions=True)

	binding_id = _create_primary_binding(
		drive_file_id=drive_file.name,
		file_id=file_id,
		upload_session_doc=upload_session_doc,
	)

	return {
		"drive_file_id": drive_file.name,
		"drive_file_version_id": drive_file_version.name,
		"canonical_ref": drive_file.canonical_ref,
		"drive_binding_id": binding_id,
	}
