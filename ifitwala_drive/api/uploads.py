# ifitwala_drive/ifitwala_drive/api/uploads.py

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.finalize import finalize_upload_session_service
from ifitwala_drive.services.uploads.sessions import (
	abort_upload_session_service,
	create_upload_session_service,
)


@frappe.whitelist()
def create_upload_session(**kwargs: Any) -> dict[str, Any]:
	"""Create a Drive Upload Session and return an upload target.

	This is the canonical entrypoint for new governed uploads.
	It must fail closed on missing governance context.
	"""
	return create_upload_session_service(kwargs)


@frappe.whitelist()
def finalize_upload_session(**kwargs: Any) -> dict[str, Any]:
	"""Finalize an upload session and create the governed file artifact."""
	return finalize_upload_session_service(kwargs)


@frappe.whitelist()
def abort_upload_session(**kwargs: Any) -> dict[str, Any]:
	"""Abort an upload session and invalidate its temporary upload target."""
	return abort_upload_session_service(kwargs)


@frappe.whitelist()
def upload_session_blob(**kwargs: Any) -> dict[str, Any]:
	"""Receive blob data for same-host proxy upload strategies."""
	upload_session_id = kwargs.get("upload_session_id") or frappe.form_dict.get("upload_session_id")
	session_key = kwargs.get("session_key") or frappe.form_dict.get("session_key")
	upload_token = kwargs.get("upload_token") or frappe.form_dict.get("upload_token")
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

	if doc.expected_size_bytes and len(content) > doc.expected_size_bytes:
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
