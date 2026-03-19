# ifitwala_drive/ifitwala_drive/services/uploads/finalize.py

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from ifitwala_drive.services.concurrency import drive_lock
from ifitwala_drive.services.files.creation import create_drive_file_artifacts
from ifitwala_drive.services.integration.ifitwala_ed_admissions import (
	get_admissions_attached_field_override,
	run_admissions_post_finalize,
	validate_applicant_document_finalize_context,
	validate_applicant_guardian_image_finalize_context,
	validate_applicant_health_finalize_context,
	validate_applicant_profile_image_finalize_context,
)
from ifitwala_drive.services.integration.ifitwala_ed_media import (
	get_attached_field_override,
	run_media_post_finalize,
	validate_media_finalize_context,
)
from ifitwala_drive.services.integration.ifitwala_ed_tasks import (
	get_task_submission_context_override,
	validate_task_submission_finalize_context,
)
from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.validation import validate_finalize_session_payload


def _call_authoritative_create_and_classify_file(
	*,
	file_kwargs: dict[str, Any],
	classification: dict[str, Any],
	secondary_subjects: list[dict[str, Any]] | None = None,
	context_override: dict[str, Any] | None = None,
):
	try:
		from ifitwala_ed.utilities.file_dispatcher import create_and_classify_file
	except ImportError as exc:
		frappe.throw(
			_("Authoritative Ifitwala_Ed dispatcher is unavailable for governed finalization: {0}").format(
				exc
			)
		)

	return create_and_classify_file(
		file_kwargs=file_kwargs,
		classification=classification,
		secondary_subjects=secondary_subjects,
		context_override=context_override,
	)


def _get_secondary_subjects(doc) -> list[dict[str, Any]]:
	return [
		{
			"subject_type": row.subject_type,
			"subject_id": row.subject_id,
			"role": getattr(row, "role", None) or "referenced",
		}
		for row in (doc.secondary_subjects or [])
	]


def _build_final_object_key(doc) -> str:
	filename = (doc.filename_original or "upload.bin").strip() or "upload.bin"
	_, extension = os.path.splitext(filename)
	seed = "|".join(
		[
			(getattr(doc, "session_key", None) or getattr(doc, "name", None) or "").strip(),
			(getattr(doc, "owner_doctype", None) or "").strip(),
			(getattr(doc, "owner_name", None) or "").strip(),
			(getattr(doc, "attached_doctype", None) or "").strip(),
			(getattr(doc, "attached_name", None) or "").strip(),
			(getattr(doc, "intended_slot", None) or "").strip(),
			filename,
		]
	)
	digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
	normalized_extension = extension.lower()[:16]
	return f"files/{digest[:2]}/{digest[2:4]}/{digest}{normalized_extension}"


def _build_file_kwargs(doc, storage_artifact: dict[str, Any]) -> dict[str, Any]:
	file_url = storage_artifact.get("file_url") or storage_artifact.get("object_key")
	attached_field = get_admissions_attached_field_override(doc) or get_attached_field_override(doc)

	file_kwargs = {
		"attached_to_doctype": doc.attached_doctype,
		"attached_to_name": doc.attached_name,
		"is_private": doc.is_private,
		"file_name": doc.filename_original,
		"file_url": file_url,
	}
	if attached_field:
		file_kwargs["attached_to_field"] = attached_field

	return file_kwargs


def _build_classification(doc) -> dict[str, Any]:
	return {
		"primary_subject_type": doc.intended_primary_subject_type,
		"primary_subject_id": doc.intended_primary_subject_id,
		"data_class": doc.intended_data_class,
		"purpose": doc.intended_purpose,
		"retention_policy": doc.intended_retention_policy,
		"slot": doc.intended_slot,
		"organization": doc.organization,
		"school": doc.school,
		"upload_source": doc.upload_source,
	}


def _get_context_override(doc) -> dict[str, Any] | None:
	if doc.owner_doctype == "Task Submission":
		return get_task_submission_context_override(doc.owner_name)

	return None


def _coerce_datetime(value: Any) -> datetime | None:
	if not value:
		return None

	if isinstance(value, datetime):
		return value

	return get_datetime(value)


def _mark_session_failed(doc, exc: Exception) -> None:
	doc.status = "failed"
	doc.error_log = str(exc)
	doc.save(ignore_permissions=True)
	log_drive_event(
		"upload_session_finalize_failed",
		upload_session_id=doc.name,
		owner_doctype=doc.owner_doctype,
		owner_name=doc.owner_name,
		slot=doc.intended_slot,
		error=str(exc),
	)


def _completed_response(doc, extra: dict[str, Any] | None = None) -> dict[str, Any]:
	drive_file_id = getattr(doc, "drive_file", None)
	drive_file_version_id = getattr(doc, "drive_file_version", None)
	canonical_ref = getattr(doc, "canonical_ref", None)

	if drive_file_id and not drive_file_version_id:
		drive_file_version_id = frappe.db.get_value("Drive File", drive_file_id, "current_version")

	if drive_file_id and not canonical_ref:
		canonical_ref = frappe.db.get_value("Drive File", drive_file_id, "canonical_ref")

	response = {
		"drive_file_id": drive_file_id,
		"drive_file_version_id": drive_file_version_id,
		"file_id": getattr(doc, "file", None),
		"canonical_ref": canonical_ref,
		"status": doc.status,
		"preview_status": "pending" if doc.status == "completed" else None,
		"file_url": frappe.db.get_value("File", doc.file, "file_url") if getattr(doc, "file", None) else None,
	}
	if extra:
		response.update(extra)
	return response


def finalize_upload_session_service(payload: dict[str, Any]) -> dict[str, Any]:
	validate_finalize_session_payload(payload)

	with drive_lock(f"upload_session_finalize:{payload['upload_session_id']}", timeout=45):
		doc = frappe.get_doc("Drive Upload Session", payload["upload_session_id"])

		expires_on = _coerce_datetime(getattr(doc, "expires_on", None))
		if (
			doc.status not in {"completed", "aborted", "expired", "failed"}
			and expires_on
			and expires_on < now_datetime()
		):
			doc.status = "expired"
			doc.save(ignore_permissions=True)

		if doc.status in {"aborted", "expired", "failed"}:
			frappe.throw(
				_("This upload session cannot be finalized from its current status: {0}").format(doc.status)
			)

		if doc.status == "completed":
			return _completed_response(doc)

		validate_task_submission_finalize_context(doc)
		validate_media_finalize_context(doc)
		validate_applicant_document_finalize_context(doc)
		validate_applicant_profile_image_finalize_context(doc)
		validate_applicant_guardian_image_finalize_context(doc)
		validate_applicant_health_finalize_context(doc)

		storage = get_storage_backend(getattr(doc, "storage_backend", None))
		if not doc.tmp_object_key or not storage.temporary_object_exists(object_key=doc.tmp_object_key):
			frappe.throw(_("Temporary uploaded object was not found for this upload session."))

		doc.status = "finalizing"
		doc.received_size_bytes = payload.get("received_size_bytes") or doc.received_size_bytes
		doc.content_hash = payload.get("content_hash") or doc.content_hash
		doc.save(ignore_permissions=True)

		log_drive_event(
			"upload_session_finalize_started",
			upload_session_id=doc.name,
			owner_doctype=doc.owner_doctype,
			owner_name=doc.owner_name,
			slot=doc.intended_slot,
		)

		try:
			storage_artifact = storage.finalize_temporary_object(
				object_key=doc.tmp_object_key,
				final_key=_build_final_object_key(doc),
			)
			created = _call_authoritative_create_and_classify_file(
				file_kwargs=_build_file_kwargs(doc, storage_artifact),
				classification=_build_classification(doc),
				secondary_subjects=_get_secondary_subjects(doc),
				context_override=_get_context_override(doc),
			)
			drive_artifacts = create_drive_file_artifacts(
				upload_session_doc=doc,
				file_id=created.name,
				storage_artifact=storage_artifact,
			)
		except Exception as exc:
			_mark_session_failed(doc, exc)
			raise

		doc.file = created.name
		doc.drive_file = drive_artifacts["drive_file_id"]
		doc.drive_file_version = drive_artifacts["drive_file_version_id"]
		doc.canonical_ref = drive_artifacts["canonical_ref"]
		doc.status = "completed"
		doc.completed_on = now_datetime()
		doc.error_log = None
		doc.save(ignore_permissions=True)

		extra_response = {}
		extra_response.update(run_media_post_finalize(doc, created))
		extra_response.update(run_admissions_post_finalize(doc, created))

		log_drive_event(
			"upload_session_finalized",
			upload_session_id=doc.name,
			file_id=doc.file,
			owner_doctype=doc.owner_doctype,
			owner_name=doc.owner_name,
			slot=doc.intended_slot,
		)

		return _completed_response(doc, extra=extra_response)
