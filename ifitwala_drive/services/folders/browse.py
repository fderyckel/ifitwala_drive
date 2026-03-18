from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def _as_int(value: Any, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _truthy(value: Any, default: bool = True) -> bool:
	if value in (None, ""):
		return default
	if isinstance(value, str):
		return value.strip().lower() not in {"0", "false", "no", "off"}
	return bool(value)


def _assert_can_read(doctype: str, name: str) -> None:
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} does not exist: {1}").format(doctype, name))

	doc = frappe.get_doc(doctype, name)
	if hasattr(doc, "check_permission"):
		doc.check_permission("read")


def _get_folder_doc(folder_id: str):
	if not folder_id:
		frappe.throw(_("Missing required field: folder"))
	if not frappe.db.exists("Drive Folder", folder_id):
		frappe.throw(_("Drive Folder does not exist: {0}").format(folder_id))
	doc = frappe.get_doc("Drive Folder", folder_id)
	_assert_can_read(doc.owner_doctype, doc.owner_name)
	return doc


def _active_drive_file_statuses() -> list[str]:
	return ["active", "processing", "blocked"]


def _get_binding_map(drive_file_ids: list[str]) -> dict[str, dict[str, Any]]:
	if not drive_file_ids:
		return {}

	rows = frappe.get_all(
		"Drive Binding",
		filters={
			"drive_file": ["in", drive_file_ids],
			"status": "active",
		},
		fields=["drive_file", "binding_role", "is_primary", "modified"],
		order_by="is_primary desc, modified desc",
	)

	binding_map: dict[str, dict[str, Any]] = {}
	for row in rows:
		drive_file = row["drive_file"]
		if drive_file not in binding_map:
			binding_map[drive_file] = row
	return binding_map


def list_folder_items_service(payload: dict[str, Any]) -> dict[str, Any]:
	folder_id = payload.get("folder")
	include_folders = _truthy(payload.get("include_folders"), default=True)
	include_files = _truthy(payload.get("include_files"), default=True)
	limit = max(_as_int(payload.get("limit"), 50), 1)
	offset = max(_as_int(payload.get("offset"), 0), 0)

	folder_doc = _get_folder_doc(folder_id)
	items: list[dict[str, Any]] = []

	if include_folders:
		child_folders = frappe.get_all(
			"Drive Folder",
			filters={
				"parent_drive_folder": folder_doc.name,
				"status": "active",
			},
			fields=["name", "title", "path_cache", "modified"],
			order_by="sort_order asc, title asc, modified desc",
			limit_page_length=limit,
			limit_start=offset,
		)
		for child in child_folders:
			items.append(
				{
					"item_type": "folder",
					"id": child["name"],
					"title": child["title"],
					"path_cache": child.get("path_cache"),
				}
			)

	if include_files:
		drive_files = frappe.get_all(
			"Drive File",
			filters={
				"folder": folder_doc.name,
				"status": ["in", _active_drive_file_statuses()],
			},
			fields=[
				"name",
				"display_name",
				"preview_status",
				"canonical_ref",
				"slot",
				"current_version_no",
				"modified",
			],
			order_by="modified desc",
			limit_page_length=limit,
			limit_start=offset,
		)
		binding_map = _get_binding_map([row["name"] for row in drive_files])
		for row in drive_files:
			binding = binding_map.get(row["name"]) or {}
			items.append(
				{
					"item_type": "file",
					"id": row["name"],
					"title": row["display_name"],
					"binding_role": binding.get("binding_role"),
					"preview_status": row["preview_status"],
					"canonical_ref": row.get("canonical_ref"),
					"slot": row.get("slot"),
					"current_version_no": row.get("current_version_no"),
				}
			)

	return {
		"folder": {
			"id": folder_doc.name,
			"title": folder_doc.title,
			"path_cache": getattr(folder_doc, "path_cache", None),
		},
		"items": items,
	}


def list_context_files_service(payload: dict[str, Any]) -> dict[str, Any]:
	doctype = payload.get("doctype")
	name = payload.get("name")
	if not doctype:
		frappe.throw(_("Missing required field: doctype"))
	if not name:
		frappe.throw(_("Missing required field: name"))

	_assert_can_read(doctype, name)

	filters: dict[str, Any] = {
		"binding_doctype": doctype,
		"binding_name": name,
		"status": "active",
	}
	if payload.get("binding_role"):
		filters["binding_role"] = payload["binding_role"]

	bindings = frappe.get_all(
		"Drive Binding",
		filters=filters,
		fields=["drive_file", "binding_role", "slot", "is_primary", "modified"],
		order_by="is_primary desc, modified desc",
	)

	drive_file_ids = []
	binding_by_file: dict[str, dict[str, Any]] = {}
	for row in bindings:
		drive_file_id = row["drive_file"]
		if drive_file_id not in binding_by_file:
			binding_by_file[drive_file_id] = row
			drive_file_ids.append(drive_file_id)

	files = []
	if drive_file_ids:
		drive_files = frappe.get_all(
			"Drive File",
			filters={
				"name": ["in", drive_file_ids],
				"status": ["in", _active_drive_file_statuses()],
			},
			fields=[
				"name",
				"canonical_ref",
				"slot",
				"display_name",
				"current_version_no",
				"preview_status",
				"folder",
			],
		)
		drive_file_map = {row["name"]: row for row in drive_files}

		for drive_file_id in drive_file_ids:
			drive_file = drive_file_map.get(drive_file_id)
			if not drive_file:
				continue
			binding = binding_by_file[drive_file_id]
			files.append(
				{
					"drive_file_id": drive_file_id,
					"canonical_ref": drive_file.get("canonical_ref"),
					"slot": drive_file.get("slot") or binding.get("slot"),
					"title": drive_file.get("display_name"),
					"current_version_no": drive_file.get("current_version_no"),
					"preview_status": drive_file.get("preview_status"),
					"binding_role": binding.get("binding_role"),
					"folder": drive_file.get("folder"),
				}
			)

	return {
		"context": {
			"doctype": doctype,
			"name": name,
		},
		"files": files,
	}
