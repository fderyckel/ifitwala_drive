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


def _load_folder_doc(folder_id: str | None, folder_cache: dict[str, Any]):
	if not folder_id:
		return None
	if folder_id in folder_cache:
		return folder_cache[folder_id]
	if not frappe.db.exists("Drive Folder", folder_id):
		return None
	doc = frappe.get_doc("Drive Folder", folder_id)
	folder_cache[folder_id] = doc
	return doc


def _build_folder_breadcrumbs(folder_doc, folder_cache: dict[str, Any]) -> list[dict[str, Any]]:
	chain = []
	visited = set()
	current = folder_doc

	while current and current.name not in visited:
		visited.add(current.name)
		chain.append(current)
		current = _load_folder_doc(getattr(current, "parent_drive_folder", None), folder_cache)

	chain.reverse()
	return [
		{
			"id": doc.name,
			"title": doc.title,
			"path_cache": getattr(doc, "path_cache", None),
		}
		for doc in chain
	]


def _build_context_path(breadcrumbs: list[dict[str, Any]]) -> str | None:
	if not breadcrumbs:
		return None
	return " / ".join(crumb["title"] for crumb in breadcrumbs if crumb.get("title"))


def _serialize_folder_summary(folder_doc, folder_cache: dict[str, Any]) -> dict[str, Any]:
	breadcrumbs = _build_folder_breadcrumbs(folder_doc, folder_cache)
	context_doctype = getattr(folder_doc, "context_doctype", None)
	context_name = getattr(folder_doc, "context_name", None)
	return {
		"id": folder_doc.name,
		"title": folder_doc.title,
		"path_cache": getattr(folder_doc, "path_cache", None),
		"context_path": _build_context_path(breadcrumbs),
		"folder_kind": getattr(folder_doc, "folder_kind", None),
		"parent_folder": getattr(folder_doc, "parent_drive_folder", None),
		"breadcrumbs": breadcrumbs,
		"owner": {
			"doctype": getattr(folder_doc, "owner_doctype", None),
			"name": getattr(folder_doc, "owner_name", None),
		},
		"context": (
			{
				"doctype": context_doctype,
				"name": context_name,
			}
			if context_doctype and context_name
			else None
		),
		"is_system_managed": getattr(folder_doc, "is_system_managed", None),
		"is_private": getattr(folder_doc, "is_private", None),
	}


def _serialize_optional_folder_summary(
	folder_id: str | None,
	folder_cache: dict[str, Any],
) -> dict[str, Any] | None:
	folder_doc = _load_folder_doc(folder_id, folder_cache)
	if not folder_doc:
		return None
	return _serialize_folder_summary(folder_doc, folder_cache)


def _serialize_file_entry(
	row: dict[str, Any],
	*,
	binding: dict[str, Any] | None,
	folder_cache: dict[str, Any],
	include_item_type: bool,
) -> dict[str, Any]:
	folder_summary = _serialize_optional_folder_summary(row.get("folder"), folder_cache)
	entry = {
		"id": row["name"],
		"title": row.get("display_name"),
		"canonical_ref": row.get("canonical_ref"),
		"slot": row.get("slot"),
		"current_version_no": row.get("current_version_no"),
		"preview_status": row.get("preview_status"),
		"binding_role": (binding or {}).get("binding_role"),
		"folder": folder_summary,
		"folder_path": (folder_summary or {}).get("path_cache"),
		"context_path": (folder_summary or {}).get("context_path"),
		"attached_to": {
			"doctype": row.get("attached_doctype"),
			"name": row.get("attached_name"),
		},
		"can_preview": row.get("preview_status") == "ready",
		"can_download": bool(row.get("canonical_ref")),
	}
	if include_item_type:
		entry["item_type"] = "file"
	return entry


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
	folder_cache: dict[str, Any] = {folder_doc.name: folder_doc}
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
			child_doc = _load_folder_doc(child["name"], folder_cache) or child
			if hasattr(child_doc, "name"):
				child_summary = _serialize_folder_summary(child_doc, folder_cache)
			else:
				child_summary = {
					"item_type": "folder",
					"id": child["name"],
					"title": child["title"],
					"path_cache": child.get("path_cache"),
					"context_path": None,
					"folder_kind": None,
					"parent_folder": folder_doc.name,
					"breadcrumbs": [],
					"owner": None,
					"context": None,
					"is_system_managed": None,
					"is_private": None,
				}
			child_summary["item_type"] = "folder"
			items.append(child_summary)

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
				"folder",
				"attached_doctype",
				"attached_name",
				"modified",
			],
			order_by="modified desc",
			limit_page_length=limit,
			limit_start=offset,
		)
		binding_map = _get_binding_map([row["name"] for row in drive_files])
		for row in drive_files:
			items.append(
				_serialize_file_entry(
					row,
					binding=binding_map.get(row["name"]),
					folder_cache=folder_cache,
					include_item_type=True,
				)
			)

	return {
		"folder": _serialize_folder_summary(folder_doc, folder_cache),
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
	folder_cache: dict[str, Any] = {}
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
				"attached_doctype",
				"attached_name",
			],
		)
		drive_file_map = {row["name"]: row for row in drive_files}

		for drive_file_id in drive_file_ids:
			drive_file = drive_file_map.get(drive_file_id)
			if not drive_file:
				continue
			binding = binding_by_file[drive_file_id]
			entry = _serialize_file_entry(
				drive_file,
				binding=binding,
				folder_cache=folder_cache,
				include_item_type=False,
			)
			entry["drive_file_id"] = drive_file_id
			entry["slot"] = drive_file.get("slot") or binding.get("slot")
			files.append(entry)

	return {
		"context": {
			"doctype": doctype,
			"name": name,
		},
		"files": files,
	}
