from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.concurrency import drive_lock, is_duplicate_entry_error


def _build_canonical_ref(*, organization: str | None, drive_file_id: str) -> str:
	scope = (organization or "unknown").strip() or "unknown"
	return f"drv:{scope}:{drive_file_id}"


def _build_drive_file_doc(upload_session_doc, *, file_id: str, storage_artifact: dict[str, Any]):
	return frappe.get_doc(
		{
			"doctype": "Drive File",
			"file": file_id,
			"source_upload_session": upload_session_doc.name,
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
			"current_version_no": 1,
			"storage_backend": storage_artifact.get("storage_backend")
			or getattr(upload_session_doc, "storage_backend", None),
			"storage_object_key": storage_artifact["object_key"],
			"upload_source": upload_session_doc.upload_source,
			"content_hash": getattr(upload_session_doc, "content_hash", None),
			"is_private": upload_session_doc.is_private,
		}
	)


def _build_primary_binding_key(*, drive_file_id: str, upload_session_doc, binding_role: str) -> str:
	parts = (
		drive_file_id,
		upload_session_doc.attached_doctype,
		upload_session_doc.attached_name,
		binding_role,
		upload_session_doc.intended_slot,
	)
	return "|".join(str(part or "").strip() for part in parts)


def _create_primary_binding(
	*,
	drive_file_id: str,
	file_id: str,
	upload_session_doc,
	binding_role: str | None = None,
) -> str | None:
	if not binding_role:
		return None

	primary_key = _build_primary_binding_key(
		drive_file_id=drive_file_id,
		upload_session_doc=upload_session_doc,
		binding_role=binding_role,
	)

	lock_key = "|".join(
		[
			"binding",
			drive_file_id,
			upload_session_doc.attached_doctype,
			upload_session_doc.attached_name,
			binding_role,
			upload_session_doc.intended_slot,
		]
	)
	with drive_lock(lock_key, timeout=20):
		existing = frappe.db.get_value(
			"Drive Binding",
			{
				"drive_file": drive_file_id,
				"binding_doctype": upload_session_doc.attached_doctype,
				"binding_name": upload_session_doc.attached_name,
				"binding_role": binding_role,
				"slot": upload_session_doc.intended_slot,
				"is_primary": 1,
				"status": "active",
			},
			"name",
		)
		if existing:
			return existing

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
				"primary_key": primary_key,
				"organization": upload_session_doc.organization,
				"school": getattr(upload_session_doc, "school", None),
			}
		)
		try:
			binding.insert(ignore_permissions=True)
		except Exception as exc:
			if not is_duplicate_entry_error(exc):
				raise

			existing = frappe.db.get_value(
				"Drive Binding",
				{"primary_key": primary_key},
				"name",
			)
			if not existing:
				raise
			return existing
		return binding.name


def _existing_drive_file_response(
	*,
	drive_file_id: str,
	upload_session_doc,
	file_id: str,
	binding_role: str | None = None,
) -> dict[str, Any]:
	binding_id = _create_primary_binding(
		drive_file_id=drive_file_id,
		file_id=file_id,
		upload_session_doc=upload_session_doc,
		binding_role=binding_role,
	)
	canonical_ref = frappe.db.get_value("Drive File", drive_file_id, "canonical_ref")
	return {
		"drive_file_id": drive_file_id,
		"drive_file_version_id": None,
		"canonical_ref": canonical_ref,
		"drive_binding_id": binding_id,
	}


def create_drive_file_artifacts(
	*,
	upload_session_doc,
	file_id: str,
	storage_artifact: dict[str, Any],
	binding_role: str | None = None,
) -> dict[str, Any]:
	with drive_lock(f"drive_file_artifacts:{upload_session_doc.name}", timeout=30):
		existing_drive_file_id = frappe.db.get_value(
			"Drive File",
			{"source_upload_session": upload_session_doc.name},
			"name",
		)
		if existing_drive_file_id:
			return _existing_drive_file_response(
				drive_file_id=existing_drive_file_id,
				upload_session_doc=upload_session_doc,
				file_id=file_id,
				binding_role=binding_role,
			)

		drive_file = _build_drive_file_doc(
			upload_session_doc,
			file_id=file_id,
			storage_artifact=storage_artifact,
		)
		try:
			drive_file.insert(ignore_permissions=True)
		except Exception as exc:
			if not is_duplicate_entry_error(exc):
				raise

			existing_drive_file_id = frappe.db.get_value(
				"Drive File",
				{"source_upload_session": upload_session_doc.name},
				"name",
			)
			if not existing_drive_file_id:
				raise
			return _existing_drive_file_response(
				drive_file_id=existing_drive_file_id,
				upload_session_doc=upload_session_doc,
				file_id=file_id,
				binding_role=binding_role,
			)

		drive_file.current_version = None
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
			binding_role=binding_role,
		)

		return {
			"drive_file_id": drive_file.name,
			"drive_file_version_id": None,
			"canonical_ref": drive_file.canonical_ref,
			"drive_binding_id": binding_id,
		}
