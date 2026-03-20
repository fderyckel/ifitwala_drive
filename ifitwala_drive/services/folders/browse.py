from __future__ import annotations

from typing import Any
from urllib.parse import quote

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


def _current_user() -> str | None:
	user = getattr(getattr(frappe, "session", None), "user", None)
	if not user:
		return None
	user = str(user).strip()
	return user or None


def _assert_can_read(doctype: str, name: str) -> None:
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} does not exist: {1}").format(doctype, name))

	doc = frappe.get_doc(doctype, name)
	if hasattr(doc, "check_permission"):
		doc.check_permission("read")


def _can_read(doctype: str | None, name: str | None) -> bool:
	if not doctype or not name:
		return False
	try:
		_assert_can_read(doctype, name)
	except Exception:
		return False
	return True


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


def _root_folder_filters() -> dict[str, Any]:
	return {
		"status": "active",
		"parent_drive_folder": ["in", ["", None]],
	}


def _folder_href(folder_id: str) -> str:
	return f"/drive_workspace?folder={quote(str(folder_id or '').strip())}"


def _context_href(doctype: str, name: str, binding_role: str | None = None) -> str:
	href = f"/drive_workspace?doctype={quote(str(doctype or '').strip())}&name={quote(str(name or '').strip())}"
	if binding_role:
		href += f"&binding_role={quote(str(binding_role).strip())}"
	return href


def _safe_get_all(
	doctype: str,
	*,
	filters: dict[str, Any] | None = None,
	fields: list[str] | None = None,
	order_by: str | None = None,
	limit_page_length: int | None = None,
	limit_start: int | None = None,
) -> list[dict[str, Any]]:
	try:
		return frappe.get_all(
			doctype,
			filters=filters or {},
			fields=fields or [],
			order_by=order_by,
			limit_page_length=limit_page_length,
			limit_start=limit_start,
		)
	except Exception:
		return []


def _current_roles(user: str | None) -> set[str]:
	if not user or not hasattr(frappe, "get_roles"):
		return set()
	try:
		return {str(role).strip() for role in frappe.get_roles(user) if str(role).strip()}
	except Exception:
		return set()


def _maybe_materialize_context_folders(doctype: str, name: str) -> None:
	if doctype != "Employee" or not name:
		return
	if not frappe.db.exists("Employee", name):
		return

	try:
		employee_doc = frappe.get_doc("Employee", name)
	except Exception:
		return

	organization = str(getattr(employee_doc, "organization", None) or "").strip()
	if not organization:
		return

	school = str(getattr(employee_doc, "school", None) or "").strip() or None

	try:
		from ifitwala_drive.services.folders.resolution import resolve_employee_image_folder
	except ImportError:
		return

	try:
		resolve_employee_image_folder(employee=name, organization=organization, school=school)
	except Exception:
		return


def _list_context_root_folders(doctype: str, name: str) -> list[dict[str, Any]]:
	_maybe_materialize_context_folders(doctype, name)

	folder_cache: dict[str, Any] = {}
	rows = _safe_get_all(
		"Drive Folder",
		filters={
			"status": "active",
			"context_doctype": doctype,
			"context_name": name,
		},
		fields=[
			"name",
			"title",
			"path_cache",
			"parent_drive_folder",
			"owner_doctype",
			"owner_name",
			"folder_kind",
			"context_doctype",
			"context_name",
			"is_system_managed",
			"is_private",
			"modified",
		],
		order_by="title asc, modified desc",
	)

	folders: list[dict[str, Any]] = []
	for row in rows:
		if not _can_read(row.get("owner_doctype"), row.get("owner_name")):
			continue

		folder_doc = _load_folder_doc(row["name"], folder_cache)
		if not folder_doc:
			continue

		parent_doc = _load_folder_doc(getattr(folder_doc, "parent_drive_folder", None), folder_cache)
		if parent_doc and (
			getattr(parent_doc, "context_doctype", None) == doctype
			and getattr(parent_doc, "context_name", None) == name
		):
			continue

		summary = _serialize_folder_summary(folder_doc, folder_cache)
		summary["item_type"] = "folder"
		folders.append(summary)

	if len(folders) == 1:
		context_root = folders[0]
		child_rows = _safe_get_all(
			"Drive Folder",
			filters={
				"status": "active",
				"parent_drive_folder": context_root["id"],
			},
			fields=[
				"name",
				"title",
				"path_cache",
				"parent_drive_folder",
				"owner_doctype",
				"owner_name",
				"folder_kind",
				"context_doctype",
				"context_name",
				"is_system_managed",
				"is_private",
				"modified",
			],
			order_by="title asc, modified desc",
		)

		child_folders: list[dict[str, Any]] = []
		for row in child_rows:
			if row.get("parent_drive_folder") != context_root["id"]:
				continue
			if not _can_read(row.get("owner_doctype"), row.get("owner_name")):
				continue

			folder_doc = _load_folder_doc(row["name"], folder_cache)
			if not folder_doc:
				continue

			summary = _serialize_folder_summary(folder_doc, folder_cache)
			summary["item_type"] = "folder"
			child_folders.append(summary)

		if child_folders:
			return child_folders

	return folders


def _list_accessible_root_folders(limit: int) -> list[dict[str, Any]]:
	folder_cache: dict[str, Any] = {}
	roots: list[dict[str, Any]] = []

	root_rows = _safe_get_all(
		"Drive Folder",
		filters=_root_folder_filters(),
		fields=[
			"name",
			"title",
			"path_cache",
			"parent_drive_folder",
			"owner_doctype",
			"owner_name",
			"folder_kind",
			"context_doctype",
			"context_name",
			"is_system_managed",
			"is_private",
			"modified",
		],
		order_by="title asc, modified desc",
		limit_page_length=limit,
	)

	for row in root_rows:
		if row.get("parent_drive_folder"):
			continue
		if not _can_read(row.get("owner_doctype"), row.get("owner_name")):
			continue

		folder_doc = _load_folder_doc(row["name"], folder_cache)
		if not folder_doc:
			folder_doc = frappe.get_doc("Drive Folder", row["name"])
			folder_cache[row["name"]] = folder_doc
		roots.append(_serialize_folder_summary(folder_doc, folder_cache))

	return roots


def _build_home_target(
	*,
	target_kind: str,
	label: str,
	caption: str,
	badge: str,
	href: str,
	folder: str | None = None,
	doctype: str | None = None,
	name: str | None = None,
	binding_role: str | None = None,
) -> dict[str, Any]:
	target_id_parts = [target_kind, folder or doctype or "", name or "", binding_role or ""]
	return {
		"id": ":".join(str(part).strip() for part in target_id_parts if str(part).strip()),
		"target_kind": target_kind,
		"label": label,
		"caption": caption,
		"badge": badge,
		"href": href,
		"folder": folder,
		"doctype": doctype,
		"name": name,
		"binding_role": binding_role,
	}


def _build_folder_home_target(folder_summary: dict[str, Any]) -> dict[str, Any]:
	return _build_home_target(
		target_kind="folder",
		label=folder_summary.get("title") or folder_summary["id"],
		caption=folder_summary.get("context_path") or _("Governed root folder"),
		badge=folder_summary.get("folder_kind") or _("Folder"),
		href=_folder_href(folder_summary["id"]),
		folder=folder_summary["id"],
	)


def _build_context_home_target(
	*,
	doctype: str,
	name: str,
	label: str,
	caption: str,
	badge: str,
	binding_role: str | None = None,
) -> dict[str, Any]:
	return _build_home_target(
		target_kind="context",
		label=label,
		caption=caption,
		badge=badge,
		href=_context_href(doctype, name, binding_role),
		doctype=doctype,
		name=name,
		binding_role=binding_role,
	)


def _own_context_targets(user: str, limit: int) -> list[dict[str, Any]]:
	targets: list[dict[str, Any]] = []

	for doctype, filters, fields, label_field, caption, badge in (
		("Employee", {"user_id": user}, ["name", "employee_full_name"], "employee_full_name", _("Your employee files"), _("Mine")),
		("Student Applicant", {"applicant_user": user}, ["name"], None, _("Your applicant files"), _("Mine")),
		("Student", {"student_email": user}, ["name", "student_full_name"], "student_full_name", _("Your student workspace"), _("Mine")),
	):
		rows = _safe_get_all(doctype, filters=filters, fields=fields, limit_page_length=limit)
		for row in rows:
			name = row.get("name")
			if not name or not _can_read(doctype, name):
				continue
			label = row.get(label_field) if label_field else None
			targets.append(
				_build_context_home_target(
					doctype=doctype,
					name=name,
					label=label or name,
					caption=caption,
					badge=badge,
				)
			)
			if len(targets) >= limit:
				return targets

	return targets


def _employee_context_targets(user: str, limit: int) -> list[dict[str, Any]]:
	roles = _current_roles(user)
	if not roles.intersection({"HR Manager", "HR User", "System Manager"}):
		return []

	rows = _safe_get_all(
		"Employee",
		filters={"employment_status": "Active"},
		fields=["name", "employee_full_name", "school", "modified"],
		order_by="employee_full_name asc, modified desc",
		limit_page_length=max(limit * 4, limit),
	)

	targets: list[dict[str, Any]] = []
	seen: set[str] = set()
	for row in rows:
		name = str(row.get("name") or "").strip()
		if not name or name in seen or not _can_read("Employee", name):
			continue
		seen.add(name)

		label = str(row.get("employee_full_name") or "").strip() or name
		school = str(row.get("school") or "").strip()
		caption = name if not school else _("{0} · {1}").format(name, school)
		targets.append(
			_build_context_home_target(
				doctype="Employee",
				name=name,
				label=label,
				caption=caption,
				badge=_("Employee"),
			)
		)
		if len(targets) >= limit:
			return targets

	return targets


def _review_assignment_targets(user: str, limit: int) -> list[dict[str, Any]]:
	roles = sorted(_current_roles(user))
	rows = _safe_get_all(
		"Applicant Review Assignment",
		filters={"assigned_to_user": user, "status": "Open"},
		fields=["name", "student_applicant", "target_type", "target_name", "source_event", "modified"],
		order_by="modified desc",
		limit_page_length=limit,
	)
	if roles:
		rows.extend(
			_safe_get_all(
				"Applicant Review Assignment",
				filters={"assigned_to_role": ["in", roles], "status": "Open"},
				fields=["name", "student_applicant", "target_type", "target_name", "source_event", "modified"],
				order_by="modified desc",
				limit_page_length=limit,
			)
		)

	seen_assignments: set[str] = set()
	seen_applicants: set[str] = set()
	targets: list[dict[str, Any]] = []
	for row in rows:
		assignment_name = str(row.get("name") or "").strip()
		if assignment_name and assignment_name in seen_assignments:
			continue
		if assignment_name:
			seen_assignments.add(assignment_name)

		student_applicant = str(row.get("student_applicant") or "").strip()
		if not student_applicant or student_applicant in seen_applicants:
			continue
		if not _can_read("Student Applicant", student_applicant):
			continue

		target_type = str(row.get("target_type") or "").strip()
		caption = _("Assigned applicant review")
		badge = _("Review")
		if target_type == "Applicant Health Profile":
			caption = _("Assigned health review")
			badge = _("Health")

		targets.append(
			_build_context_home_target(
				doctype="Student Applicant",
				name=student_applicant,
				label=student_applicant,
				caption=caption,
				badge=badge,
			)
		)
		seen_applicants.add(student_applicant)
		if len(targets) >= limit:
			break

	return targets


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
			fields=[
				"name",
				"title",
				"path_cache",
				"parent_drive_folder",
				"owner_doctype",
				"owner_name",
				"folder_kind",
				"context_doctype",
				"context_name",
				"is_system_managed",
				"is_private",
				"modified",
			],
			order_by="sort_order asc, title asc, modified desc",
			limit_page_length=limit,
			limit_start=offset,
		)
		for child in child_folders:
			child_doc = _load_folder_doc(child["name"], folder_cache) or child
			if not _can_read(
				getattr(child_doc, "owner_doctype", None) if hasattr(child_doc, "owner_doctype") else child.get("owner_doctype"),
				getattr(child_doc, "owner_name", None) if hasattr(child_doc, "owner_name") else child.get("owner_name"),
			):
				continue
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
				"owner_doctype",
				"owner_name",
				"modified",
			],
			order_by="modified desc",
			limit_page_length=limit,
			limit_start=offset,
		)
		binding_map = _get_binding_map([row["name"] for row in drive_files])
		for row in drive_files:
			if not _can_read(row.get("owner_doctype"), row.get("owner_name")):
				continue
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


def list_workspace_roots_service(payload: dict[str, Any]) -> dict[str, Any]:
	limit = max(_as_int(payload.get("limit"), 24), 1)
	return {
		"roots": _list_accessible_root_folders(limit),
	}


def list_workspace_home_service(payload: dict[str, Any]) -> dict[str, Any]:
	limit = max(_as_int(payload.get("limit"), 6), 1)
	user = _current_user()
	sections: list[dict[str, Any]] = []

	if user:
		review_targets = _review_assignment_targets(user, limit)
		if review_targets:
			sections.append(
				{
					"key": "reviewing",
					"label": _("Reviewing"),
					"description": _("Applicant work currently assigned to you."),
					"items": review_targets,
				}
			)

		own_targets = _own_context_targets(user, limit)
		if own_targets:
			sections.append(
				{
					"key": "mine",
					"label": _("My Drive"),
					"description": _("Your readable governed contexts."),
					"items": own_targets,
				}
			)

		employee_targets = _employee_context_targets(user, limit)
		if employee_targets:
			sections.append(
				{
					"key": "employees",
					"label": _("Employees"),
					"description": _("Readable employee Drive contexts for HR-scoped staff."),
					"items": employee_targets,
				}
			)

	root_targets = [_build_folder_home_target(root) for root in _list_accessible_root_folders(limit)]
	if root_targets:
		sections.append(
			{
				"key": "roots",
				"label": _("Folders"),
				"description": _("Governed roots available to your current permissions."),
				"items": root_targets,
			}
		)

	all_targets = [item for section in sections for item in section.get("items", [])]
	suggested_target = None
	if all_targets:
		suggested_target = dict(all_targets[0])
		suggested_target["auto_open"] = len(all_targets) == 1

	return {
		"sections": sections,
		"suggested_target": suggested_target,
	}


def list_context_files_service(payload: dict[str, Any]) -> dict[str, Any]:
	doctype = payload.get("doctype")
	name = payload.get("name")
	if not doctype:
		frappe.throw(_("Missing required field: doctype"))
	if not name:
		frappe.throw(_("Missing required field: name"))

	_assert_can_read(doctype, name)
	context_folders = _list_context_root_folders(doctype, name)

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

	items = list(context_folders)
	items.extend({**file, "item_type": "file"} for file in files)

	return {
		"context": {
			"doctype": doctype,
			"name": name,
		},
		"folders": context_folders,
		"files": files,
		"items": items,
	}
