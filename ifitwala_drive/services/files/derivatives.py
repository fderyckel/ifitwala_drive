from __future__ import annotations

import json
from typing import Any

import frappe

DEFAULT_PREVIEW_DERIVATIVE_ROLE = "viewer_preview"
_IMAGE_PREVIEW_ROLES = ("thumb", "viewer_preview")
_PREVIEW_JOB_STATUSES = ("queued", "running")


def resolve_ready_preview_derivative(
	*,
	drive_file_doc,
	derivative_role: str = DEFAULT_PREVIEW_DERIVATIVE_ROLE,
) -> dict[str, Any] | None:
	current_version = str(getattr(drive_file_doc, "current_version", "") or "").strip()
	if not current_version:
		return None

	derivative_id = frappe.db.exists(
		"Drive File Derivative",
		{
			"drive_file": drive_file_doc.name,
			"drive_file_version": current_version,
			"derivative_role": derivative_role,
			"status": "ready",
		},
	)
	if not derivative_id:
		return None

	derivative_doc = frappe.get_doc("Drive File Derivative", derivative_id)
	return {
		"name": derivative_doc.name,
		"derivative_role": getattr(derivative_doc, "derivative_role", None),
		"status": getattr(derivative_doc, "status", None),
		"storage_backend": getattr(derivative_doc, "storage_backend", None)
		or getattr(drive_file_doc, "storage_backend", None),
		"storage_object_key": getattr(derivative_doc, "storage_object_key", None),
		"mime_type": getattr(derivative_doc, "mime_type", None),
	}


def preview_plan_for_mime_type(mime_type: str | None) -> dict[str, Any]:
	normalized = str(mime_type or "").strip().lower()
	if normalized.startswith("image/"):
		return {
			"supported": True,
			"preview_status": "pending",
			"derivative_roles": list(_IMAGE_PREVIEW_ROLES),
			"queue_name": "drive_default",
		}

	return {
		"supported": False,
		"preview_status": "not_applicable",
		"derivative_roles": [],
		"queue_name": None,
	}


def _ensure_derivative_row(
	*,
	drive_file_id: str,
	drive_file_version_id: str,
	derivative_role: str,
	source_hash: str | None = None,
) -> str:
	filters = {
		"drive_file": drive_file_id,
		"drive_file_version": drive_file_version_id,
		"derivative_role": derivative_role,
	}
	existing = frappe.db.exists("Drive File Derivative", filters)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Drive File Derivative",
			"drive_file": drive_file_id,
			"drive_file_version": drive_file_version_id,
			"derivative_role": derivative_role,
			"status": "pending",
			"source_hash": source_hash,
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except Exception as exc:
		duplicate_error = getattr(frappe, "DuplicateEntryError", None)
		if duplicate_error is None or not isinstance(exc, duplicate_error):
			raise
		existing = frappe.db.exists("Drive File Derivative", filters)
		if existing:
			return existing
		raise
	return doc.name


def _ensure_preview_job(
	*,
	drive_file_doc,
	mime_type: str | None,
	derivative_roles: list[str],
	queue_name: str,
) -> str:
	file_id = str(getattr(drive_file_doc, "file", "") or "").strip()
	drive_file_id = str(getattr(drive_file_doc, "name", "") or "").strip()
	for status in _PREVIEW_JOB_STATUSES:
		existing = frappe.db.exists(
			"Drive Processing Job",
			{
				"job_type": "preview",
				"drive_file": drive_file_id,
				"file": file_id,
				"status": status,
			},
		)
		if existing:
			return existing

	job = frappe.get_doc(
		{
			"doctype": "Drive Processing Job",
			"job_type": "preview",
			"status": "queued",
			"queue_name": queue_name,
			"priority": "normal",
			"drive_file": drive_file_id,
			"file": file_id,
			"payload_json": json.dumps(
				{
					"drive_file_version": getattr(drive_file_doc, "current_version", None),
					"mime_type": mime_type,
					"derivative_roles": derivative_roles,
				},
				sort_keys=True,
			),
		}
	)
	job.insert(ignore_permissions=True)
	return job.name


def mark_version_derivatives_stale(*, drive_file_id: str, drive_file_version_id: str | None) -> int:
	version_id = str(drive_file_version_id or "").strip()
	if not version_id:
		return 0

	get_all = getattr(frappe, "get_all", None)
	if not callable(get_all):
		return 0

	stale_count = 0
	for row in get_all(
		"Drive File Derivative",
		filters={"drive_file": drive_file_id, "drive_file_version": version_id},
		fields=["name", "status"],
	):
		derivative_id = str(row.get("name") or "").strip()
		if not derivative_id or row.get("status") == "stale":
			continue
		doc = frappe.get_doc("Drive File Derivative", derivative_id)
		doc.status = "stale"
		doc.save(ignore_permissions=True)
		stale_count += 1
	return stale_count


def sync_preview_pipeline_for_current_version(
	*,
	drive_file_doc,
	mime_type: str | None,
) -> dict[str, Any]:
	plan = preview_plan_for_mime_type(mime_type)
	drive_file_doc.preview_status = plan["preview_status"]
	if not plan["supported"]:
		return {
			"preview_status": drive_file_doc.preview_status,
			"derivative_ids": [],
			"drive_processing_job_id": None,
		}

	drive_file_id = str(getattr(drive_file_doc, "name", "") or "").strip()
	drive_file_version_id = str(getattr(drive_file_doc, "current_version", "") or "").strip()
	source_hash = str(getattr(drive_file_doc, "content_hash", "") or "").strip() or None
	derivative_ids = [
		_ensure_derivative_row(
			drive_file_id=drive_file_id,
			drive_file_version_id=drive_file_version_id,
			derivative_role=role,
			source_hash=source_hash,
		)
		for role in plan["derivative_roles"]
	]
	job_id = _ensure_preview_job(
		drive_file_doc=drive_file_doc,
		mime_type=mime_type,
		derivative_roles=plan["derivative_roles"],
		queue_name=plan["queue_name"],
	)
	return {
		"preview_status": drive_file_doc.preview_status,
		"derivative_ids": derivative_ids,
		"drive_processing_job_id": job_id,
	}
