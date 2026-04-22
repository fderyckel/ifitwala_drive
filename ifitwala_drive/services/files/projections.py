from __future__ import annotations

from typing import Any

import frappe


def _default_native_file_folder() -> str | None:
	for candidate in ("Home/Attachments", "Home"):
		if frappe.db.exists("File", candidate):
			return candidate
	return None


def _build_native_file_payload(
	upload_session_doc,
	*,
	storage_artifact: dict[str, Any],
	finalize_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
	file_url = storage_artifact.get("file_url") or storage_artifact.get("object_key")
	payload = {
		"doctype": "File",
		"attached_to_doctype": upload_session_doc.attached_doctype,
		"attached_to_name": upload_session_doc.attached_name,
		"is_private": upload_session_doc.is_private,
		"file_name": upload_session_doc.filename_original,
		"file_url": file_url,
	}
	attached_field = (finalize_contract or {}).get("attached_field_override")
	if attached_field:
		payload["attached_to_field"] = attached_field
	folder = _default_native_file_folder()
	if folder:
		payload["folder"] = folder
	size_bytes = storage_artifact.get("size_bytes")
	if size_bytes is not None:
		payload["file_size"] = size_bytes
	return payload


def _existing_file_projection(upload_session_doc) -> str | None:
	existing_file_id = str(getattr(upload_session_doc, "file", "") or "").strip()
	if existing_file_id and frappe.db.exists("File", existing_file_id):
		return existing_file_id

	existing_drive_file = frappe.db.get_value(
		"Drive File",
		{"source_upload_session": upload_session_doc.name},
		"file",
	)
	if existing_drive_file and frappe.db.exists("File", existing_drive_file):
		return str(existing_drive_file)

	return None


def ensure_native_file_projection(
	*,
	upload_session_doc,
	storage_artifact: dict[str, Any],
	finalize_contract: dict[str, Any] | None = None,
):
	existing_file_id = _existing_file_projection(upload_session_doc)
	if existing_file_id:
		return frappe.get_doc("File", existing_file_id)

	file_doc = frappe.get_doc(
		_build_native_file_payload(
			upload_session_doc,
			storage_artifact=storage_artifact,
			finalize_contract=finalize_contract,
		)
	)
	if getattr(file_doc, "flags", None) is None:
		file_doc.flags = frappe._dict()
	file_doc.flags.governed_upload = True
	# Skip Ed's legacy route/derivative hooks for Drive-managed compatibility rows.
	file_doc.flags.drive_compat_projection = True
	file_doc.insert(ignore_permissions=True)
	return file_doc
