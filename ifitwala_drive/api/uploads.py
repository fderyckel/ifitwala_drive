# ifitwala_drive/ifitwala_drive/api/uploads.py

from __future__ import annotations

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import frappe
from frappe import _

try:
	from frappe.rate_limiter import rate_limit
except Exception:  # pragma: no cover - import-safe fallback for non-Frappe unit tests

	def rate_limit(*_args, **_kwargs):
		def decorator(func):
			return func

		return decorator


from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.logging import log_drive_event
from ifitwala_drive.services.storage.base import get_storage_backend
from ifitwala_drive.services.uploads.finalize import finalize_upload_session_service
from ifitwala_drive.services.uploads.sessions import (
	abort_upload_session_service,
	create_upload_session_service,
	load_upload_contract,
)


def _resolve_upload_session_doc(
	*,
	upload_session_id: str | None = None,
	session_key: str | None = None,
	upload_token: str | None = None,
	require_upload_token: bool = True,
):
	upload_session_id = upload_session_id or frappe.form_dict.get("upload_session_id")
	session_key = session_key or frappe.form_dict.get("session_key")
	if require_upload_token:
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
	if require_upload_token and stored_upload_token and upload_token != stored_upload_token:
		frappe.throw(_("Upload token mismatch."))
	if doc.status in {"aborted", "completed", "expired", "failed"}:
		frappe.throw(_("This upload session does not accept blob uploads in status: {0}").format(doc.status))

	return doc


def _extract_request_blob_content() -> bytes:
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

	return content


def _validate_received_content(*, doc, content: bytes) -> None:
	if not content:
		frappe.throw(_("Uploaded file content is empty."))

	expected_size_bytes = getattr(doc, "expected_size_bytes", None)
	if expected_size_bytes and len(content) > expected_size_bytes:
		frappe.throw(_("Uploaded blob exceeds the expected size for this upload session."))


def _upload_bytes_to_target(*, upload_target: dict[str, Any], content: bytes) -> None:
	method = str((upload_target or {}).get("method") or "PUT").strip().upper() or "PUT"
	url = str((upload_target or {}).get("url") or "").strip()
	if not url:
		frappe.throw(_("Drive upload target is missing a URL."))

	headers = {
		str(key): str(value)
		for key, value in ((upload_target or {}).get("headers") or {}).items()
		if value is not None
	}
	request = Request(url=url, data=content, headers=headers, method=method)

	try:
		with urlopen(request) as response:
			status = getattr(response, "status", None) or response.getcode()
	except HTTPError as exc:
		frappe.throw(_("Drive upload target rejected the upload with status {0}.").format(exc.code))
	except URLError as exc:
		frappe.throw(_("Drive upload target could not be reached: {0}").format(exc.reason or exc))

	if status is not None and not 200 <= int(status) < 300:
		frappe.throw(_("Drive upload target returned an unexpected status: {0}.").format(status))


def _mark_upload_session_uploaded(doc, *, received_size_bytes: int) -> dict[str, Any]:
	doc.status = "uploaded"
	doc.received_size_bytes = received_size_bytes
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


def _ingest_upload_session_content(
	*,
	upload_session_id: str | None = None,
	session_key: str | None = None,
	upload_token: str | None = None,
	content: bytes,
	require_proxy_post: bool,
	require_upload_token: bool,
) -> dict[str, Any]:
	doc = _resolve_upload_session_doc(
		upload_session_id=upload_session_id,
		session_key=session_key,
		upload_token=upload_token,
		require_upload_token=require_upload_token,
	)
	upload_contract = load_upload_contract(doc)
	upload_strategy = str(upload_contract.get("upload_strategy") or "").strip()
	if require_proxy_post and upload_strategy != "proxy_post":
		frappe.throw(
			_(
				"Blob proxy uploads are only allowed for proxy_post sessions. Use the issued upload_target directly."
			)
		)
	_validate_received_content(doc=doc, content=content)

	if upload_strategy == "proxy_post":
		storage = get_storage_backend(getattr(doc, "storage_backend", None))
		storage.write_temporary_object(object_key=doc.tmp_object_key, content=content)
	else:
		_upload_bytes_to_target(upload_target=upload_contract.get("upload_target") or {}, content=content)

	return _mark_upload_session_uploaded(doc, received_size_bytes=len(content))


def ingest_upload_session_content(
	*,
	upload_session_id: str | None = None,
	session_key: str | None = None,
	upload_token: str | None = None,
	content: bytes,
) -> dict[str, Any]:
	"""Drive-owned server-side ingress helper for already-buffered file content."""
	return _ingest_upload_session_content(
		upload_session_id=upload_session_id,
		session_key=session_key,
		upload_token=upload_token,
		content=content,
		require_proxy_post=False,
		require_upload_token=False,
	)


@frappe.whitelist()
@rate_limit(limit=30, seconds=60)
def create_upload_session(
	workflow_id: str | None = None,
	workflow_payload: dict[str, Any] | None = None,
	contract_version: str | None = None,
	filename_original: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Create a Drive Upload Session and return an upload target.

	This public API is workflow-spec only. Migration/backfill tooling must use
	internal services or explicit `Drive Upload Session` materialization instead.
	"""
	if not str(workflow_id or "").strip():
		frappe.throw(_("workflow_id is required."))

	return create_upload_session_service(
		compact_payload(
			workflow_id=workflow_id,
			workflow_payload=workflow_payload,
			contract_version=contract_version,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
@rate_limit(limit=60, seconds=60)
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
@rate_limit(limit=30, seconds=60)
def abort_upload_session(upload_session_id: str) -> dict[str, Any]:
	"""Abort an upload session and invalidate its temporary upload target."""
	return abort_upload_session_service(compact_payload(upload_session_id=upload_session_id))


@frappe.whitelist()
@rate_limit(limit=120, seconds=60)
def upload_session_blob(
	upload_session_id: str | None = None,
	session_key: str | None = None,
	upload_token: str | None = None,
) -> dict[str, Any]:
	"""Receive blob data for same-host proxy upload strategies."""
	return _ingest_upload_session_content(
		upload_session_id=upload_session_id,
		session_key=session_key,
		upload_token=upload_token,
		content=_extract_request_blob_content(),
		require_proxy_post=True,
		require_upload_token=True,
	)
