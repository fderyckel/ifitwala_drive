# ifitwala_drive/ifitwala_drive/services/uploads/finalize.py

from __future__ import annotations

from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.uploads.validation import validate_finalize_session_payload
from ifitwala_drive.services.storage.gcs import GCSStorageBackend

# Transitional compatibility bridge.
from ifitwala_ed.utilities.file_dispatcher import create_and_classify_file


def finalize_upload_session_service(payload: Dict[str, Any]) -> Dict[str, Any]:
	validate_finalize_session_payload(payload)

	doc = frappe.get_doc("Drive Upload Session", payload["upload_session_id"])

	if doc.status in {"aborted", "expired", "failed"}:
		frappe.throw(_("This upload session cannot be finalized from its current status: {0}").format(doc.status))

	if doc.status == "completed":
		return {
			"drive_file_id": doc.drive_file,
			"file_id": doc.file,
			"canonical_ref": None,
			"status": doc.status,
			"preview_status": None,
		}

	storage = GCSStorageBackend()
	if not doc.tmp_object_key or not storage.temporary_object_exists(object_key=doc.tmp_object_key):
		frappe.throw(_("Temporary uploaded object was not found for this upload session."))

	doc.status = "finalizing"
	doc.received_size_bytes = payload.get("received_size_bytes") or doc.received_size_bytes
	doc.content_hash = payload.get("content_hash") or doc.content_hash
	doc.save(ignore_permissions=True)

	# Transitional path:
	# still call the authoritative governed creation path from Ifitwala_Ed.
	created = create_and_classify_file(
		file_kwargs={
			"attached_to_doctype": doc.attached_doctype,
			"attached_to_name": doc.attached_name,
			"is_private": doc.is_private,
			"file_name": doc.filename_original,
			# Replace this later with storage-aware final file binding.
			"file_url": doc.tmp_object_key,
		},
		classification={
			"primary_subject_type": doc.intended_primary_subject_type,
			"primary_subject_id": doc.intended_primary_subject_id,
			"data_class": doc.intended_data_class,
			"purpose": doc.intended_purpose,
			"retention_policy": doc.intended_retention_policy,
			"slot": doc.intended_slot,
			"organization": doc.organization,
			"school": doc.school,
		},
		secondary_subjects=[
			{
				"subject_type": row.subject_type,
				"subject_id": row.subject_id,
				"role": row.role,
			}
			for row in (doc.secondary_subjects or [])
		],
	)

	doc.file = created.name
	doc.status = "completed"
	doc.completed_on = now_datetime()
	doc.save(ignore_permissions=True)

	return {
		"drive_file_id": None,  # Fill when Drive File is introduced as canonical record.
		"drive_file_version_id": None,
		"file_id": doc.file,
		"canonical_ref": None,
		"status": doc.status,
		"preview_status": "pending",
	}
