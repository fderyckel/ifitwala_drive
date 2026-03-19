from __future__ import annotations

from datetime import timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

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


def _format_datetime(value) -> str:
	return value.strftime("%Y-%m-%d %H:%M:%S")


def _issue_grant(*, doc, grant_kind: str) -> dict[str, Any]:
	file_url = frappe.db.get_value("File", doc.file, "file_url") if getattr(doc, "file", None) else None
	expires_on = _build_expires_on()
	storage = get_storage_backend(getattr(doc, "storage_backend", None))

	if grant_kind == "preview":
		grant = storage.issue_preview_grant(
			object_key=doc.storage_object_key,
			file_url=file_url,
			expires_on=expires_on,
		)
	else:
		grant = storage.issue_download_grant(
			object_key=doc.storage_object_key,
			file_url=file_url,
			expires_on=expires_on,
		)

	response = {
		"grant_type": grant["grant_type"],
		"url": grant["url"],
		"expires_on": _format_datetime(expires_on),
	}
	if grant_kind == "preview":
		response["preview_status"] = doc.preview_status
	return response


def issue_download_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	doc = _get_drive_file_doc(payload)
	_assert_can_issue_download(doc)
	return _issue_grant(doc=doc, grant_kind="download")


def issue_preview_grant_service(payload: dict[str, Any]) -> dict[str, Any]:
	doc = _get_drive_file_doc(payload)
	_assert_can_issue_preview(doc)
	return _issue_grant(doc=doc, grant_kind="preview")
