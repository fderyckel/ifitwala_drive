from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from ifitwala_drive.services.concurrency import drive_lock
from ifitwala_drive.services.files.creation import create_drive_file_artifacts
from ifitwala_drive.services.integration.ifitwala_ed_bridge import (
	resolve_finalize_contract,
	run_post_finalize,
)
from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.inspection import inspect_uploaded_bytes
from ifitwala_drive.services.uploads.keys import build_upload_object_key
from ifitwala_drive.services.uploads.sessions import load_upload_contract
from ifitwala_drive.services.uploads.validation import validate_finalize_session_payload

_FINALIZE_WAIT_SECONDS = 6.0
_FINALIZE_POLL_SECONDS = 0.25
_STALE_FINALIZING_SECONDS = 90


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
	return build_upload_object_key(
		session_key=getattr(doc, "session_key", None) or getattr(doc, "name", None) or "",
		owner_doctype=getattr(doc, "owner_doctype", None) or "",
		owner_name=getattr(doc, "owner_name", None) or "",
		attached_doctype=getattr(doc, "attached_doctype", None) or "",
		attached_name=getattr(doc, "attached_name", None) or "",
		slot=getattr(doc, "intended_slot", None) or "",
		filename=getattr(doc, "filename_original", None) or "upload.bin",
	)


def _build_file_kwargs(
	doc,
	storage_artifact: dict[str, Any],
	finalize_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
	file_url = storage_artifact.get("file_url") or storage_artifact.get("object_key")
	attached_field = (finalize_contract or {}).get("attached_field_override")

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


def _is_stale_finalizing(doc) -> bool:
	if getattr(doc, "status", None) != "finalizing":
		return False
	modified = _coerce_datetime(getattr(doc, "modified", None))
	if not modified:
		return False
	return modified <= now_datetime() - timedelta(seconds=_STALE_FINALIZING_SECONDS)


def _wait_for_terminal_session(upload_session_id: str) -> dict[str, Any]:
	deadline = time.monotonic() + _FINALIZE_WAIT_SECONDS
	while time.monotonic() < deadline:
		doc = frappe.get_doc("Drive Upload Session", upload_session_id)
		if doc.status == "completed":
			return _completed_response(doc)
		if doc.status in {"failed", "aborted", "expired"}:
			frappe.throw(
				_("This upload session cannot be finalized from its current status: {0}").format(doc.status)
			)
		time.sleep(_FINALIZE_POLL_SECONDS)

	frappe.throw(_("This upload session is already finalizing. Please retry in a moment."))


def _claim_upload_session_for_finalize(payload: dict[str, Any]):
	upload_session_id = payload["upload_session_id"]
	with drive_lock(f"upload_session_finalize:{upload_session_id}", timeout=20):
		doc = frappe.get_doc("Drive Upload Session", upload_session_id)

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
			return doc, "completed", None

		if doc.status == "finalizing" and not _is_stale_finalizing(doc):
			return doc, "wait", None

		finalize_contract = resolve_finalize_contract(doc)
		doc.status = "finalizing"
		doc.received_size_bytes = payload.get("received_size_bytes") or getattr(
			doc, "received_size_bytes", None
		)
		doc.content_hash = payload.get("content_hash") or getattr(doc, "content_hash", None)
		doc.error_log = None
		doc.save(ignore_permissions=True)

		log_drive_event(
			"upload_session_finalize_started",
			upload_session_id=doc.name,
			owner_doctype=doc.owner_doctype,
			owner_name=doc.owner_name,
			slot=doc.intended_slot,
		)
		return doc, "claimed", finalize_contract


def finalize_upload_session_service(payload: dict[str, Any]) -> dict[str, Any]:
	validate_finalize_session_payload(payload)
	doc, claim_state, finalize_contract = _claim_upload_session_for_finalize(payload)
	if claim_state == "completed":
		return _completed_response(doc)
	if claim_state == "wait":
		return _wait_for_terminal_session(doc.name)

	storage = get_storage_backend(getattr(doc, "storage_backend", None))
	load_upload_contract(doc, storage=storage, fallback_to_storage=False)
	if not doc.tmp_object_key or not storage.temporary_object_exists(object_key=doc.tmp_object_key):
		frappe.throw(_("Temporary uploaded object was not found for this upload session."))

	try:
		inspect_uploaded_bytes(storage=storage, upload_session_doc=doc)
		storage_artifact = storage.finalize_temporary_object(
			object_key=doc.tmp_object_key,
			final_key=_build_final_object_key(doc),
		)
		created = _call_authoritative_create_and_classify_file(
			file_kwargs=_build_file_kwargs(doc, storage_artifact, finalize_contract),
			classification=_build_classification(doc),
			secondary_subjects=_get_secondary_subjects(doc),
			context_override=(finalize_contract or {}).get("context_override"),
		)
		drive_artifacts = create_drive_file_artifacts(
			upload_session_doc=doc,
			file_id=created.name,
			storage_artifact=storage_artifact,
			binding_role=(finalize_contract or {}).get("binding_role"),
		)
	except Exception as exc:
		_mark_session_failed(doc, exc)
		raise

	with drive_lock(f"upload_session_finalize:{doc.name}", timeout=20):
		refreshed = frappe.get_doc("Drive Upload Session", doc.name)
		if refreshed.status == "completed":
			doc = refreshed
		else:
			refreshed.file = created.name
			refreshed.drive_file = drive_artifacts["drive_file_id"]
			refreshed.drive_file_version = drive_artifacts.get("drive_file_version_id")
			refreshed.canonical_ref = drive_artifacts["canonical_ref"]
			refreshed.status = "completed"
			refreshed.completed_on = now_datetime()
			refreshed.error_log = None
			refreshed.save(ignore_permissions=True)
			doc = refreshed

	extra_response = run_post_finalize(doc, created)

	log_drive_event(
		"upload_session_finalized",
		upload_session_id=doc.name,
		file_id=doc.file,
		owner_doctype=doc.owner_doctype,
		owner_name=doc.owner_name,
		slot=doc.intended_slot,
	)

	return _completed_response(doc, extra=extra_response)
