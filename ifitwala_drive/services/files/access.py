from __future__ import annotations

from datetime import timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.audit.events import record_drive_access_event
from ifitwala_drive.services.files.derivatives import (
	primary_preview_derivative_role_for_mime_type,
	resolve_ready_preview_derivative,
	resolve_ready_preview_derivative_state,
	sync_preview_pipeline_for_current_version,
)
from ifitwala_drive.services.files.versions import ensure_current_drive_file_version
from ifitwala_drive.services.storage.base import get_storage_backend

_GRANT_TTL_MINUTES = 10


def _assert_can_read(doctype: str, name: str) -> None:
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} does not exist: {1}").format(doctype, name))

	doc = frappe.get_doc(doctype, name)
	if hasattr(doc, "check_permission"):
		doc.check_permission("read")


def _resolve_drive_file_id(payload: dict[str, Any]) -> str:
	drive_file_id = payload.get("drive_file_id")
	if drive_file_id:
		return drive_file_id

	canonical_ref = payload.get("canonical_ref")
	if canonical_ref:
		resolved = frappe.db.get_value("Drive File", {"canonical_ref": canonical_ref}, "name")
		if resolved:
			return resolved
		frappe.throw(_("Drive File does not exist for canonical_ref: {0}").format(canonical_ref))

	frappe.throw(_("Missing required field: drive_file_id"))


def _get_drive_file_doc(payload: dict[str, Any]):
	drive_file_id = _resolve_drive_file_id(payload)
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	doc = frappe.get_doc("Drive File", drive_file_id)
	_assert_can_read(doc.owner_doctype, doc.owner_name)
	return doc


def _assert_can_issue_download(doc) -> None:
	if doc.status != "active":
		frappe.throw(_("Download grant cannot be issued for Drive File in status: {0}").format(doc.status))


def _assert_can_issue_preview(doc) -> None:
	_assert_can_issue_download(doc)
	if doc.preview_status != "ready":
		frappe.throw(
			_("Preview grant cannot be issued for Drive File with preview status: {0}").format(
				doc.preview_status
			)
		)


def _build_expires_on():
	return now_datetime() + timedelta(minutes=_GRANT_TTL_MINUTES)


def _save_doc_if_supported(doc) -> None:
	save = getattr(doc, "save", None)
	if callable(save):
		save(ignore_permissions=True)


def _requested_preview_roles(*, payload: dict[str, Any] | None, mime_type: str | None) -> list[str]:
	normalized: list[str] = []
	if isinstance(payload, dict):
		role_values = payload.get("derivative_roles")
		if isinstance(role_values, (list, tuple, set)):
			for value in role_values:
				candidate = str(value or "").strip()
				if candidate and candidate not in normalized:
					normalized.append(candidate)

	explicit_derivative_role = str((payload or {}).get("derivative_role") or "").strip()
	if explicit_derivative_role and explicit_derivative_role not in normalized:
		normalized.append(explicit_derivative_role)

	if normalized:
		return normalized

	default_role = primary_preview_derivative_role_for_mime_type(mime_type)
	return [default_role] if default_role else []


def _ensure_preview_pipeline_requested(*, doc, payload: dict[str, Any] | None = None) -> bool:
	current_version = ensure_current_drive_file_version(drive_file_doc=doc)
	if current_version:
		doc.current_version = current_version
	current_version = str(current_version or "").strip()
	if not current_version:
		return False

	mime_type = frappe.db.get_value("Drive File Version", current_version, "mime_type")
	if not mime_type:
		return False

	requested_roles = _requested_preview_roles(payload=payload, mime_type=mime_type)
	if getattr(doc, "preview_status", None) == "ready" and requested_roles:
		states = [
			resolve_ready_preview_derivative_state(
				drive_file_doc=doc,
				derivative_role=derivative_role,
			).get("state")
			for derivative_role in requested_roles
		]
		if all(state == "ready" for state in states):
			return False

	previous_preview_status = getattr(doc, "preview_status", None)
	result = sync_preview_pipeline_for_current_version(
		drive_file_doc=doc,
		mime_type=mime_type,
	)
	if result.get("preview_status") != previous_preview_status:
		_save_doc_if_supported(doc)
	return True


def request_preview_derivatives_for_doc(*, doc, payload: dict[str, Any] | None = None) -> dict[str, Any]:
	_assert_can_issue_download(doc)
	requested = _ensure_preview_pipeline_requested(doc=doc, payload=payload)
	current_version = str(getattr(doc, "current_version", "") or "").strip() or None
	mime_type = (
		frappe.db.get_value("Drive File Version", current_version, "mime_type") if current_version else None
	)
	requested_roles = _requested_preview_roles(payload=payload, mime_type=mime_type)
	return {
		"drive_file_id": getattr(doc, "name", None),
		"current_version": current_version,
		"preview_status": getattr(doc, "preview_status", None),
		"requested": bool(requested),
		"derivative_roles": requested_roles,
	}


def _format_datetime(value) -> str:
	return value.strftime("%Y-%m-%d %H:%M:%S")


def _issue_grant(*, doc, grant_kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
	payload = payload or {}
	file_url = frappe.db.get_value("File", doc.file, "file_url") if getattr(doc, "file", None) else None
	expires_on = _build_expires_on()
	storage_backend = getattr(doc, "storage_backend", None)
	object_key = getattr(doc, "storage_object_key", None)
	response_file_url = file_url

	if grant_kind == "preview":
		current_version = str(getattr(doc, "current_version", "") or "").strip()
		mime_type = (
			frappe.db.get_value("Drive File Version", current_version, "mime_type")
			if current_version
			else None
		)
		explicit_derivative_role = str(payload.get("derivative_role") or "").strip() or None
		derivative_role = explicit_derivative_role or primary_preview_derivative_role_for_mime_type(mime_type)
		preview_derivative = resolve_ready_preview_derivative(
			drive_file_doc=doc,
			derivative_role=derivative_role,
		)
		derivative_state = None
		if explicit_derivative_role:
			derivative_state = resolve_ready_preview_derivative_state(
				drive_file_doc=doc,
				derivative_role=derivative_role,
			)
			preview_derivative = (
				derivative_state.get("derivative") if derivative_state.get("state") == "ready" else None
			)
		if preview_derivative and preview_derivative.get("storage_object_key"):
			storage_backend = preview_derivative.get("storage_backend") or storage_backend
			object_key = preview_derivative.get("storage_object_key")
			response_file_url = None
		elif explicit_derivative_role:
			frappe.throw(
				_("Preview grant cannot be issued for Drive File without a ready derivative: {0}").format(
					explicit_derivative_role
				)
			)
		storage = get_storage_backend(storage_backend)
		grant = storage.issue_preview_grant(
			object_key=object_key,
			file_url=response_file_url,
			expires_on=expires_on,
			filename=getattr(doc, "display_name", None),
		)
	else:
		storage = get_storage_backend(storage_backend)
		grant = storage.issue_download_grant(
			object_key=object_key,
			file_url=response_file_url,
			expires_on=expires_on,
			filename=getattr(doc, "display_name", None),
		)

	response = {
		"grant_type": grant["grant_type"],
		"url": grant["url"],
		"expires_on": _format_datetime(expires_on),
	}
	if grant_kind == "preview":
		response["preview_status"] = doc.preview_status
	record_drive_access_event(
		drive_file_id=doc.name,
		drive_file_version_id=getattr(doc, "current_version", None),
		event_type="preview_open" if grant_kind == "preview" else "download_grant",
		metadata={"grant_type": grant["grant_type"], "expires_on": response["expires_on"]},
	)
	return response


def _issue_preview_grant_for_doc(*, doc, payload: dict[str, Any] | None = None) -> dict[str, Any]:
	_ensure_preview_pipeline_requested(doc=doc, payload=payload)
	if str((payload or {}).get("derivative_role") or "").strip():
		_assert_can_issue_download(doc)
	else:
		_assert_can_issue_preview(doc)
	return _issue_grant(doc=doc, grant_kind="preview", payload=payload)


def issue_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	doc = _get_drive_file_doc(payload)
	_assert_can_issue_download(doc)
	return _issue_grant(doc=doc, grant_kind="download")


def issue_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	doc = _get_drive_file_doc(payload)
	return _issue_preview_grant_for_doc(doc=doc, payload=payload)
