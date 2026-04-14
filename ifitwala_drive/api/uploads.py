# ifitwala_drive/ifitwala_drive/api/uploads.py

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.finalize import finalize_upload_session_service
from ifitwala_drive.services.uploads.sessions import (
	abort_upload_session_service,
	create_upload_session_service,
	load_upload_contract,
)


@frappe.whitelist()
def create_upload_session(
	owner_doctype: str,
	owner_name: str,
	attached_doctype: str,
	attached_name: str,
	organization: str,
	primary_subject_type: str,
	primary_subject_id: str,
	data_class: str,
	purpose: str,
	retention_policy: str,
	slot: str,
	filename_original: str,
	school: str | None = None,
	folder: str | None = None,
	secondary_subjects: list[dict[str, Any]] | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	is_private: int | bool | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Create a Drive Upload Session and return an upload target.

	This is the canonical entrypoint for new governed uploads.
	It must fail closed on missing governance context.
	"""
	return create_upload_session_service(
		compact_payload(
			owner_doctype=owner_doctype,
			owner_name=owner_name,
			attached_doctype=attached_doctype,
			attached_name=attached_name,
			organization=organization,
			school=school,
			folder=folder,
			primary_subject_type=primary_subject_type,
			primary_subject_id=primary_subject_id,
			data_class=data_class,
			purpose=purpose,
			retention_policy=retention_policy,
			slot=slot,
			secondary_subjects=secondary_subjects,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			is_private=is_private,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def finalize_upload_session(
	upload_session_id: str,
	received_size_bytes: int | str | None = None,
	content_hash: str | None = None,
) -> dict[str, Any]:
	"""Finalize an upload session and create the governed file artifact."""
	return finalize_upload_session_service(
		compact_payload(
			upload_session_id=upload_session_id,
			received_size_bytes=received_size_bytes,
			content_hash=content_hash,
		)
	)


@frappe.whitelist()
def abort_upload_session(upload_session_id: str) -> dict[str, Any]:
	"""Abort an upload session and invalidate its temporary upload target."""
	return abort_upload_session_service(compact_payload(upload_session_id=upload_session_id))


@frappe.whitelist()
def upload_session_blob(
	upload_session_id: str | None = None,
	session_key: str | None = None,
	upload_token: str | None = None,
) -> dict[str, Any]:
	"""Receive blob data for same-host proxy upload strategies."""
	upload_session_id = upload_session_id or frappe.form_dict.get("upload_session_id")
	session_key = session_key or frappe.form_dict.get("session_key")
	upload_token = upload_token or frappe.form_dict.get("upload_token")
	if not upload_token:
		request_headers = getattr(frappe, "request", None)
		if request_headers and hasattr(request_headers, "headers"):
			upload_token = request_headers.headers.get("X-Drive-Upload-Token")

	if not upload_session_id and not session_key:
		frappe.throw(_("Missing required field: upload_session_id"))

	if upload_session_id:
		doc = frappe.get_doc("Drive Upload Session", upload_session_id)
	else:
		doc_name = frappe.db.get_value("Drive Upload Session", {"session_key": session_key}, "name")
		if not doc_name:
			frappe.throw(_("Drive Upload Session was not found for the provided session_key."))
		doc = frappe.get_doc("Drive Upload Session", doc_name)

	if session_key and session_key != doc.session_key:
		frappe.throw(_("Upload session key mismatch."))
	stored_upload_token = (
		doc.get_password("upload_token")
		if hasattr(doc, "get_password")
		else getattr(doc, "upload_token", None)
	)
	if stored_upload_token and upload_token != stored_upload_token:
		frappe.throw(_("Upload token mismatch."))
	if doc.status in {"aborted", "completed", "expired", "failed"}:
		frappe.throw(_("This upload session does not accept blob uploads in status: {0}").format(doc.status))

	upload_contract = load_upload_contract(doc)
	if upload_contract.get("upload_strategy") != "proxy_post":
		frappe.throw(
			_(
				"Blob proxy uploads are only allowed for proxy_post sessions. Use the issued upload_target directly."
			)
		)

	content = b""
	request = getattr(frappe, "request", None)
	if request and getattr(request, "files", None):
		uploaded = request.files.get("file")
		if uploaded:
			if hasattr(uploaded, "stream") and hasattr(uploaded.stream, "seek"):
				uploaded.stream.seek(0)
			if hasattr(uploaded, "stream"):
				content = uploaded.stream.read() or b""
			elif hasattr(uploaded, "read"):
				content = uploaded.read() or b""

	if not content and request and hasattr(request, "get_data"):
		content = request.get_data() or b""

	if not content:
		frappe.throw(_("Uploaded file content is empty."))

	expected_size_bytes = getattr(doc, "expected_size_bytes", None)
	if expected_size_bytes and len(content) > expected_size_bytes:
		frappe.throw(_("Uploaded blob exceeds the expected size for this upload session."))

	storage = get_storage_backend(getattr(doc, "storage_backend", None))
	storage.write_temporary_object(object_key=doc.tmp_object_key, content=content)

	doc.status = "uploaded"
	doc.received_size_bytes = len(content)
	doc.error_log = None
	doc.save(ignore_permissions=True)

	log_drive_event(
		"upload_session_blob_received",
		upload_session_id=doc.name,
		owner_doctype=doc.owner_doctype,
		owner_name=doc.owner_name,
		slot=doc.intended_slot,
		received_size_bytes=doc.received_size_bytes,
	)

	return {
		"upload_session_id": doc.name,
		"status": doc.status,
		"received_size_bytes": doc.received_size_bytes,
	}
