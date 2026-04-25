from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from ifitwala_drive.services.audit.events import record_drive_access_event
from ifitwala_drive.services.concurrency import drive_lock
from ifitwala_drive.services.files.creation import create_drive_file_artifacts
from ifitwala_drive.services.files.projections import (
	ensure_native_file_projection,
)
from ifitwala_drive.services.integration.ifitwala_ed_bridge import (
	resolve_finalize_contract,
	run_post_finalize,
)
from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.inspection import inspect_uploaded_bytes
from ifitwala_drive.services.uploads.keys import build_upload_object_key
from ifitwala_drive.services.uploads.sessions import (
	load_upload_contract,
	load_workflow_contract_metadata,
	persist_workflow_result,
)
from ifitwala_drive.services.uploads.validation import validate_finalize_session_payload

_FINALIZE_WAIT_SECONDS = 6.0
_FINALIZE_POLL_SECONDS = 0.25
_STALE_FINALIZING_SECONDS = 90


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


def _completed_response(doc) -> dict[str, Any]:
	drive_file_id = getattr(doc, "drive_file", None)
	drive_file_version_id = getattr(doc, "drive_file_version", None)
	canonical_ref = getattr(doc, "canonical_ref", None)
	preview_status = None
	workflow_metadata = load_workflow_contract_metadata(doc)

	if drive_file_id and not drive_file_version_id:
		drive_file_version_id = frappe.db.get_value("Drive File", drive_file_id, "current_version")

	if drive_file_id and not canonical_ref:
		canonical_ref = frappe.db.get_value("Drive File", drive_file_id, "canonical_ref")

	if drive_file_id:
		preview_status = frappe.db.get_value("Drive File", drive_file_id, "preview_status")

	response = {
		"drive_file_id": drive_file_id,
		"drive_file_version_id": drive_file_version_id,
		"file_id": getattr(doc, "file", None),
		"canonical_ref": canonical_ref,
		"status": doc.status,
		"preview_status": preview_status,
		"workflow_id": workflow_metadata.get("workflow_id"),
		"contract_version": workflow_metadata.get("contract_version"),
		"workflow_result": workflow_metadata.get("workflow_result") or {},
	}
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


def _require_persisted_finalize_contract(finalize_contract: dict[str, Any] | None) -> dict[str, Any]:
	if isinstance(finalize_contract, dict) and finalize_contract.get("workflow_id"):
		return finalize_contract

	frappe.throw(
		_(
			"Upload session is missing persisted workflow metadata. Recreate the upload session or run the approved migration/backfill patch."
		)
	)
	return {}


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
		finalize_contract = _require_persisted_finalize_contract(finalize_contract)
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
		detected_mime_type = inspect_uploaded_bytes(storage=storage, upload_session_doc=doc)
		storage_artifact = storage.finalize_temporary_object(
			object_key=doc.tmp_object_key,
			final_key=_build_final_object_key(doc),
		)
		storage_artifact["mime_type"] = detected_mime_type
		if getattr(doc, "received_size_bytes", None):
			storage_artifact["size_bytes"] = doc.received_size_bytes
		if getattr(doc, "content_hash", None):
			storage_artifact["content_hash"] = doc.content_hash
		created = ensure_native_file_projection(
			upload_session_doc=doc,
			storage_artifact=storage_artifact,
			finalize_contract=finalize_contract,
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

	post_finalize_result = run_post_finalize(doc, created)
	workflow_metadata = load_workflow_contract_metadata(doc)
	merged_workflow_result = dict(workflow_metadata.get("workflow_result") or {})
	if post_finalize_result:
		merged_workflow_result.update(post_finalize_result)

	with drive_lock(f"upload_session_finalize:{doc.name}", timeout=20):
		refreshed = frappe.get_doc("Drive Upload Session", doc.name)
		persist_workflow_result(refreshed, merged_workflow_result)
		refreshed.save(ignore_permissions=True)
		doc = refreshed

	record_drive_access_event(
		drive_file_id=doc.drive_file,
		drive_file_version_id=doc.drive_file_version,
		event_type="upload",
		metadata={"upload_session_id": doc.name, "file_id": doc.file, "slot": doc.intended_slot},
	)

	log_drive_event(
		"upload_session_finalized",
		upload_session_id=doc.name,
		file_id=doc.file,
		owner_doctype=doc.owner_doctype,
		owner_name=doc.owner_name,
		slot=doc.intended_slot,
	)

	return _completed_response(doc)
