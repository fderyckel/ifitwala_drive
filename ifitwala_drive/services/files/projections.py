from __future__ import annotations

from types import SimpleNamespace
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
	if not getattr(file_doc, "flags", None):
		file_doc.flags = SimpleNamespace()
	file_doc.flags.governed_upload = True
	# Skip Ed's legacy route/derivative hooks for Drive-managed compatibility rows.
	file_doc.flags.drive_compat_projection = True
	file_doc.insert(ignore_permissions=True)
	return file_doc


def _secondary_subject_rows(upload_session_doc) -> list[dict[str, Any]]:
	return [
		{
			"subject_type": row.subject_type,
			"subject_id": row.subject_id,
			"role": getattr(row, "role", None) or "referenced",
		}
		for row in (getattr(upload_session_doc, "secondary_subjects", None) or [])
	]


def _resolve_retention_until(upload_session_doc):
	retention_policy = getattr(upload_session_doc, "intended_retention_policy", None)
	data_class = getattr(upload_session_doc, "intended_data_class", None)
	purpose = getattr(upload_session_doc, "intended_purpose", None)
	if not (retention_policy and data_class and purpose):
		return None

	if not frappe.db.exists("DocType", "File Retention Policy"):
		return None

	retention_days = frappe.db.get_value(
		"File Retention Policy",
		{
			"data_class": data_class,
			"purpose": purpose,
		},
		"retention_days",
	)
	if retention_days is None:
		return None

	utils = getattr(frappe, "utils", None)
	today = getattr(utils, "today", None)
	add_days = getattr(utils, "add_days", None)
	if not callable(today) or not callable(add_days):
		return None

	return add_days(today(), int(retention_days))


def _list_slot_classifications(
	*, primary_subject_type: str, primary_subject_id: str, slot: str
) -> list[dict[str, Any]]:
	get_all = getattr(frappe, "get_all", None)
	if not callable(get_all):
		return []

	rows = get_all(
		"File Classification",
		fields=["name", "version_number", "is_current_version"],
		filters={
			"primary_subject_type": primary_subject_type,
			"primary_subject_id": primary_subject_id,
			"slot": slot,
		},
	)
	return rows or []


def _next_projection_version(*, primary_subject_type: str, primary_subject_id: str, slot: str) -> int:
	rows = _list_slot_classifications(
		primary_subject_type=primary_subject_type,
		primary_subject_id=primary_subject_id,
		slot=slot,
	)
	current_max = 0
	for row in rows:
		try:
			current_max = max(current_max, int(row.get("version_number") or 0))
		except (TypeError, ValueError):
			continue
	return current_max + 1


def _mark_previous_projection_versions_inactive(
	*,
	primary_subject_type: str,
	primary_subject_id: str,
	slot: str,
) -> None:
	set_value = getattr(getattr(frappe, "db", None), "set_value", None)
	if not callable(set_value):
		return

	for row in _list_slot_classifications(
		primary_subject_type=primary_subject_type,
		primary_subject_id=primary_subject_id,
		slot=slot,
	):
		if not int(row.get("is_current_version") or 0):
			continue
		set_value(
			"File Classification",
			row["name"],
			"is_current_version",
			0,
			update_modified=False,
		)


def _build_file_classification_payload(upload_session_doc, *, file_doc) -> dict[str, Any]:
	primary_subject_type = upload_session_doc.intended_primary_subject_type
	primary_subject_id = upload_session_doc.intended_primary_subject_id
	slot = upload_session_doc.intended_slot
	_mark_previous_projection_versions_inactive(
		primary_subject_type=primary_subject_type,
		primary_subject_id=primary_subject_id,
		slot=slot,
	)

	payload = {
		"doctype": "File Classification",
		"file": file_doc.name,
		"attached_doctype": file_doc.attached_to_doctype,
		"attached_name": file_doc.attached_to_name,
		"primary_subject_type": primary_subject_type,
		"primary_subject_id": primary_subject_id,
		"data_class": upload_session_doc.intended_data_class,
		"purpose": upload_session_doc.intended_purpose,
		"retention_policy": upload_session_doc.intended_retention_policy,
		"slot": slot,
		"organization": upload_session_doc.organization,
		"legal_hold": 0,
		"erasure_state": "active",
		"version_number": _next_projection_version(
			primary_subject_type=primary_subject_type,
			primary_subject_id=primary_subject_id,
			slot=slot,
		),
		"is_current_version": 1,
		"content_hash": getattr(upload_session_doc, "content_hash", None),
		"upload_source": getattr(upload_session_doc, "upload_source", None) or "API",
		"ip_address": getattr(getattr(frappe, "local", None), "request_ip", None),
		"secondary_subjects": _secondary_subject_rows(upload_session_doc),
	}
	retention_until = _resolve_retention_until(upload_session_doc)
	if retention_until:
		payload["retention_until"] = retention_until
	school = getattr(upload_session_doc, "school", None)
	if school:
		payload["school"] = school
	return payload


def ensure_file_classification_projection(*, upload_session_doc, file_doc):
	existing_name = frappe.db.get_value("File Classification", {"file": file_doc.name}, "name")
	if existing_name:
		return frappe.get_doc("File Classification", existing_name)

	classification_doc = frappe.get_doc(
		_build_file_classification_payload(upload_session_doc, file_doc=file_doc)
	)
	classification_doc.insert(ignore_permissions=True)
	return classification_doc
