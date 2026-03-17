# ifitwala_drive/ifitwala_drive/services/uploads/sessions.py

from __future__ import annotations

from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.validation import validate_create_session_payload


def _build_secondary_subject_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
	return [
		{
			"subject_type": row["subject_type"],
			"subject_id": row["subject_id"],
			"role": row.get("role", "referenced"),
		}
		for row in (payload.get("secondary_subjects") or [])
	]


def create_upload_session_service(payload: Dict[str, Any]) -> Dict[str, Any]:
	validate_create_session_payload(payload)

	session_key = frappe.generate_hash(length=24)
	storage = get_storage_backend()
	target = storage.create_temporary_upload_target(
		session_key=session_key,
		filename=payload["filename_original"],
		mime_type=payload.get("mime_type_hint"),
	)

	doc = frappe.get_doc(
		{
			"doctype": "Drive Upload Session",
			"session_key": session_key,
			"status": "created",
			"upload_source": payload.get("upload_source") or "API",
			"created_by_user": frappe.session.user,
			"request_ip": frappe.local.request_ip if getattr(frappe.local, "request_ip", None) else None,
			"attached_doctype": payload["attached_doctype"],
			"attached_name": payload["attached_name"],
			"owner_doctype": payload["owner_doctype"],
			"owner_name": payload["owner_name"],
			"organization": payload["organization"],
			"school": payload.get("school"),
			"folder": payload.get("folder"),
			"intended_primary_subject_type": payload["primary_subject_type"],
			"intended_primary_subject_id": payload["primary_subject_id"],
			"intended_data_class": payload["data_class"],
			"intended_purpose": payload["purpose"],
			"intended_retention_policy": payload["retention_policy"],
			"intended_slot": payload["slot"],
			"secondary_subjects": _build_secondary_subject_rows(payload),
			"filename_original": payload["filename_original"],
			"mime_type_hint": payload.get("mime_type_hint"),
			"is_private": payload.get("is_private", 1),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"storage_backend": storage.backend_name,
			"tmp_object_key": target["object_key"],
		}
	)
	doc.insert(ignore_permissions=True)

	return {
		"upload_session_id": doc.name,
		"session_key": doc.session_key,
		"status": doc.status,
		"expires_on": doc.expires_on,
		"upload_strategy": target["upload_strategy"],
		"upload_target": target["upload_target"],
	}


def abort_upload_session_service(payload: Dict[str, Any]) -> Dict[str, Any]:
	upload_session_id = payload.get("upload_session_id")
	if not upload_session_id:
		frappe.throw(_("Missing required field: upload_session_id"))

	doc = frappe.get_doc("Drive Upload Session", upload_session_id)

	if doc.status in {"completed", "aborted"}:
		return {
			"upload_session_id": doc.name,
			"status": doc.status,
		}

	storage = get_storage_backend(getattr(doc, "storage_backend", None))
	if doc.tmp_object_key:
		storage.abort_temporary_object(object_key=doc.tmp_object_key)

	doc.status = "aborted"
	doc.aborted_on = now_datetime()
	doc.save(ignore_permissions=True)

	return {
		"upload_session_id": doc.name,
		"status": doc.status,
	}
