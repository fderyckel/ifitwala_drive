from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.concurrency import drive_lock, is_duplicate_entry_error
from ifitwala_drive.services.integration.ifitwala_ed_bridge import reconcile_upload_session_payload
from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.keys import build_upload_object_key, build_upload_session_key
from ifitwala_drive.services.uploads.validation import validate_create_session_payload


def _build_secondary_subject_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
	return [
		{
			"subject_type": row["subject_type"],
			"subject_id": row["subject_id"],
			"role": row.get("role", "referenced"),
		}
		for row in (payload.get("secondary_subjects") or [])
	]


def _serialize_session_response(doc, target: dict[str, Any]) -> dict[str, Any]:
	return {
		"upload_session_id": doc.name,
		"session_key": doc.session_key,
		"status": doc.status,
		"expires_on": getattr(doc, "expires_on", None),
		"upload_strategy": target["upload_strategy"],
		"upload_target": target["upload_target"],
	}


def _workflow_contract_metadata(payload: dict[str, Any]) -> dict[str, Any] | None:
	workflow_id = str(payload.get("workflow_id") or "").strip()
	contract_version = str(payload.get("contract_version") or "").strip()
	if not workflow_id:
		return None
	return {
		"workflow_id": workflow_id,
		"contract_version": contract_version or None,
	}


def _dump_upload_contract(target: dict[str, Any], *, workflow: dict[str, Any] | None = None) -> str:
	serialized = dict(target)
	if workflow:
		serialized["workflow"] = workflow
	return json.dumps(serialized, sort_keys=True)


def load_upload_contract(doc, *, storage=None, fallback_to_storage: bool = True) -> dict[str, Any]:
	raw = getattr(doc, "upload_contract_json", None)
	if raw:
		parsed = json.loads(raw)
		if isinstance(parsed, dict):
			return parsed

	if not fallback_to_storage:
		return {}

	if storage is None:
		storage = get_storage_backend(getattr(doc, "storage_backend", None))

	return storage.create_temporary_upload_target(
		session_key=doc.session_key,
		filename=doc.filename_original,
		mime_type=getattr(doc, "mime_type_hint", None),
		upload_token=getattr(doc, "upload_token", None),
		expected_size_bytes=getattr(doc, "expected_size_bytes", None),
		object_key_hint=getattr(doc, "tmp_object_key", None),
	)


def _load_existing_session_response(session_key: str) -> dict[str, Any] | None:
	doc_name = frappe.db.get_value("Drive Upload Session", {"session_key": session_key}, "name")
	if not doc_name:
		return None

	doc = frappe.get_doc("Drive Upload Session", doc_name)
	target = load_upload_contract(doc)
	return _serialize_session_response(doc, target)


def create_upload_session_service(payload: dict[str, Any]) -> dict[str, Any]:
	payload = reconcile_upload_session_payload(payload)
	validate_create_session_payload(payload)

	session_key = build_upload_session_key(payload, user=getattr(frappe.session, "user", None))
	existing_response = _load_existing_session_response(session_key)
	if existing_response:
		return existing_response

	upload_token = frappe.generate_hash(length=32)
	storage = get_storage_backend()
	object_key = build_upload_object_key(
		session_key=session_key,
		owner_doctype=payload["owner_doctype"],
		owner_name=payload["owner_name"],
		attached_doctype=payload["attached_doctype"],
		attached_name=payload["attached_name"],
		slot=payload["slot"],
		filename=payload["filename_original"],
	)
	target = storage.create_temporary_upload_target(
		session_key=session_key,
		filename=payload["filename_original"],
		mime_type=payload.get("mime_type_hint"),
		upload_token=upload_token,
		expected_size_bytes=payload.get("expected_size_bytes"),
		object_key_hint=object_key,
	)

	lock_key = f"upload_session_create:{session_key}"
	with drive_lock(lock_key, timeout=20):
		existing_response = _load_existing_session_response(session_key)
		if existing_response:
			return existing_response

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
				"upload_contract_json": _dump_upload_contract(
					target,
					workflow=_workflow_contract_metadata(payload),
				),
				"upload_token": upload_token,
			}
		)
		try:
			doc.insert(ignore_permissions=True)
		except Exception as exc:
			if not is_duplicate_entry_error(exc):
				raise

			existing_response = _load_existing_session_response(session_key)
			if existing_response:
				return existing_response
			raise

	log_drive_event(
		"upload_session_created",
		upload_session_id=doc.name,
		owner_doctype=doc.owner_doctype,
		owner_name=doc.owner_name,
		slot=doc.intended_slot,
		storage_backend=doc.storage_backend,
		status=doc.status,
	)

	return _serialize_session_response(doc, target)


def abort_upload_session_service(payload: dict[str, Any]) -> dict[str, Any]:
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

	log_drive_event(
		"upload_session_aborted",
		upload_session_id=doc.name,
		owner_doctype=doc.owner_doctype,
		owner_name=doc.owner_name,
		slot=doc.intended_slot,
	)

	return {
		"upload_session_id": doc.name,
		"status": doc.status,
	}
