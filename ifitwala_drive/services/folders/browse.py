from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import frappe
from frappe import _

from ifitwala_drive.services.integration.ifitwala_ed_bridge import (
	resolve_browse_context_presentation,
)

_INTERNAL_FOLDER_ID_RE = re.compile(r"^DRF-[A-Z0-9]{6,}$", re.IGNORECASE)
_INTERNAL_FILE_ID_RE = re.compile(r"^DF-[A-Z0-9-]{3,}$", re.IGNORECASE)
_LONG_HEX_TOKEN_RE = re.compile(r"^[A-F0-9]{16,}$", re.IGNORECASE)
_UPPER_MACHINE_TOKEN_RE = re.compile(r"^[A-Z0-9]+(?:[-_][A-Z0-9]+)+$")

_DOCTYPE_DISPLAY_LABELS = {
	"Course": "Course",
	"Employee": "Employee",
	"Guardian": "Guardian",
	"Organization": "Organization",
	"School": "School",
	"Student": "Student",
	"Student Applicant": "Applicant",
	"Supporting Material": "Material",
	"Task": "Task",
}

_FOLDER_KIND_DISPLAY_LABELS = {
	"applicant_documents": "Applicant",
	"course_shared": "Course",
	"general_resource": "Resource",
	"guardian_workspace": "Guardian",
	"organization_media": "Organization Media",
	"staff_documents": "Employee",
	"student_workspace": "Student",
	"system_bound": "Folder",
	"teacher_private": "Teacher",
}

_PARENT_TITLE_HINTS = {
	"applicant": "Applicant",
	"employees": "Employee",
	"guardians": "Guardian",
	"materials": "Material",
	"student": "Student",
	"students": "Student",
	"tasks": "Task",
}

_BINDING_ROLE_DISPLAY_LABELS = {
	"applicant_document": "Applicant document",
	"communication_attachment": "Communication attachment",
	"employee_image": "Employee image",
	"guardian_image": "Guardian image",
	"organization_media": "Media asset",
	"supporting_material": "Supporting material",
	"student_image": "Student image",
	"submission_artifact": "Submission file",
}

_IDENTIFIER_PREFIX_HINTS = {
	"APP": "Applicant",
	"APPLICANT": "Applicant",
	"COURSE": "Course",
	"CRS": "Course",
	"EMP": "Employee",
	"EMPLOYEE": "Employee",
	"GRD": "Guardian",
	"GUARDIAN": "Guardian",
	"MAT": "Material",
	"MATERIAL": "Material",
	"SCH": "School",
	"SCHOOL": "School",
	"STU": "Student",
	"STUDENT": "Student",
	"TASK": "Task",
	"TSK": "Task",
}

_PRESENTATION_HINT_DOCTYPES = {
	"applicant": "Student Applicant",
	"course": "Course",
	"employee": "Employee",
	"guardian": "Guardian",
	"material": "Supporting Material",
	"organization": "Organization",
	"school": "School",
	"student": "Student",
	"task": "Task",
}


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


def _assert_has_permission(doctype: str, name: str, permission_type: str = "read") -> None:
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} does not exist: {1}").format(doctype, name))

	doc = frappe.get_doc(doctype, name)
	if hasattr(doc, "check_permission"):
		doc.check_permission(permission_type)


def _assert_can_read(doctype: str, name: str) -> None:
	_assert_has_permission(doctype, name, "read")


def _can_read(doctype: str | None, name: str | None) -> bool:
	if not doctype or not name:
		return False
	try:
		_assert_has_permission(doctype, name, "read")
	except Exception:
		return False
	return True


def _can_write(doctype: str | None, name: str | None) -> bool:
	if not doctype or not name:
		return False
	try:
		_assert_has_permission(doctype, name, "write")
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


def _clean_text(value: Any) -> str:
	return str(value or "").strip()


def _normalize_text_key(value: Any) -> str:
	return _clean_text(value).lower()


def _looks_like_opaque_identifier(value: Any, *, allow_internal_file_ids: bool = True) -> bool:
	text = _clean_text(value)
	if not text:
		return False

	if _INTERNAL_FOLDER_ID_RE.fullmatch(text):
		return True
	if allow_internal_file_ids and _INTERNAL_FILE_ID_RE.fullmatch(text):
		return True

	hex_candidate = text.replace("-", "").replace("_", "")
	if len(hex_candidate) >= 16 and _LONG_HEX_TOKEN_RE.fullmatch(hex_candidate):
		return True

	if " " in text:
		return False

	return (
		text.upper() == text
		and any(character.isdigit() for character in text)
		and bool(_UPPER_MACHINE_TOKEN_RE.fullmatch(text))
	)


def _looks_like_internal_machine_title(value: Any) -> bool:
	text = _clean_text(value)
	if not text:
		return False
	if _INTERNAL_FOLDER_ID_RE.fullmatch(text) or _INTERNAL_FILE_ID_RE.fullmatch(text):
		return True
	hex_candidate = text.replace("-", "").replace("_", "")
	return len(hex_candidate) >= 16 and bool(_LONG_HEX_TOKEN_RE.fullmatch(hex_candidate))


def _doctype_display_label(doctype: str | None) -> str | None:
	label = _DOCTYPE_DISPLAY_LABELS.get(_clean_text(doctype))
	return _(label) if label else None


def _folder_kind_display_label(folder_kind: str | None) -> str | None:
	label = _FOLDER_KIND_DISPLAY_LABELS.get(_clean_text(folder_kind))
	return _(label) if label else None


def _parent_title_hint(parent_doc) -> str | None:
	if not parent_doc:
		return None
	label = _PARENT_TITLE_HINTS.get(_normalize_text_key(getattr(parent_doc, "title", None)))
	return _(label) if label else None


def _identifier_prefix_hint(value: Any) -> str | None:
	text = _clean_text(value)
	if not text or " " in text:
		return None
	prefix = re.split(r"[-_]", text, maxsplit=1)[0].upper()
	label = _IDENTIFIER_PREFIX_HINTS.get(prefix)
	return _(label) if label else None


def _hint_label_to_doctype(label: str | None) -> str | None:
	if not label:
		return None
	return _PRESENTATION_HINT_DOCTYPES.get(_normalize_text_key(label))


def _resolve_context_presentation(
	doctype: str | None,
	name: str | None,
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> dict[str, Any] | None:
	doctype = _clean_text(doctype)
	name = _clean_text(name)
	if not doctype or not name:
		return None
	cache_key = (doctype, name)
	if cache_key not in presentation_cache:
		try:
			presentation_cache[cache_key] = resolve_browse_context_presentation(doctype, name)
		except Exception:
			presentation_cache[cache_key] = None
	return presentation_cache[cache_key]


def _context_presentation_fields(
	doctype: str | None,
	name: str | None,
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> dict[str, Any]:
	presentation = _resolve_context_presentation(doctype, name, presentation_cache)
	if not isinstance(presentation, dict):
		return {}

	display_title = _clean_text(presentation.get("display_title"))
	display_code = _clean_text(presentation.get("display_code"))
	name_text = _clean_text(name)
	fields: dict[str, Any] = {}
	if display_title and display_title != name_text:
		fields["display_title"] = display_title
	if display_code and display_code != display_title:
		fields["display_code"] = display_code
	return fields


def _is_subject_placeholder_title(
	title: str | None,
	doctype: str | None,
	name: str | None,
) -> bool:
	title_text = _clean_text(title)
	if not title_text:
		return False
	if title_text == _clean_text(name):
		return True
	if _looks_like_internal_machine_title(title_text):
		return True
	display_label = _doctype_display_label(doctype)
	return bool(display_label and _normalize_text_key(title_text) == _normalize_text_key(display_label))


def _folder_subject_presentation(
	folder_doc,
	parent_doc,
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> dict[str, Any] | None:
	title = _clean_text(getattr(folder_doc, "title", None))

	for doctype_attr, name_attr in (("context_doctype", "context_name"), ("owner_doctype", "owner_name")):
		doctype = _clean_text(getattr(folder_doc, doctype_attr, None))
		name = _clean_text(getattr(folder_doc, name_attr, None))
		if not doctype or not name or not _can_read(doctype, name):
			continue
		presentation = _resolve_context_presentation(doctype, name, presentation_cache)
		if not isinstance(presentation, dict):
			continue
		display_title = _clean_text(presentation.get("display_title"))
		if not display_title:
			continue
		can_use_placeholder = doctype_attr == "context_doctype" or doctype != "Organization"
		if (
			can_use_placeholder and _is_subject_placeholder_title(title, doctype, name)
		) or _normalize_text_key(title) == _normalize_text_key(display_title):
			return presentation

	for hint in (_identifier_prefix_hint(title), _parent_title_hint(parent_doc)):
		inferred_doctype = _hint_label_to_doctype(hint)
		if inferred_doctype and title and _can_read(inferred_doctype, title):
			return _resolve_context_presentation(inferred_doctype, title, presentation_cache)

	return None


def _display_folder_presentation(
	folder_doc,
	folder_cache: dict[str, Any],
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> dict[str, Any]:
	title = _clean_text(getattr(folder_doc, "title", None))
	parent_doc = _load_folder_doc(getattr(folder_doc, "parent_drive_folder", None), folder_cache)
	subject_presentation = _folder_subject_presentation(folder_doc, parent_doc, presentation_cache)
	if isinstance(subject_presentation, dict):
		display_title = _clean_text(subject_presentation.get("display_title"))
		display_code = _clean_text(subject_presentation.get("display_code"))
		if display_title:
			presentation = {"display_title": display_title}
			if display_code and display_code != display_title:
				presentation["display_code"] = display_code
			return presentation

	if title and not _looks_like_opaque_identifier(title, allow_internal_file_ids=False):
		return {"display_title": title}

	return {"display_title": _fallback_folder_display_title(folder_doc, parent_doc)}


def _fallback_folder_display_title(folder_doc, parent_doc=None) -> str:
	prefix_hint = _identifier_prefix_hint(getattr(folder_doc, "title", None))
	context_label = _doctype_display_label(getattr(folder_doc, "context_doctype", None))
	owner_label = _doctype_display_label(getattr(folder_doc, "owner_doctype", None))
	parent_hint = _parent_title_hint(parent_doc)
	folder_kind_label = _folder_kind_display_label(getattr(folder_doc, "folder_kind", None))

	if prefix_hint:
		return prefix_hint

	if parent_hint and parent_doc:
		parent_context_doctype = _clean_text(getattr(parent_doc, "context_doctype", None))
		parent_owner_doctype = _clean_text(getattr(parent_doc, "owner_doctype", None))
		current_context_doctype = _clean_text(getattr(folder_doc, "context_doctype", None))
		current_owner_doctype = _clean_text(getattr(folder_doc, "owner_doctype", None))
		if (
			parent_context_doctype == current_context_doctype
			and parent_owner_doctype == current_owner_doctype
		):
			return parent_hint

	for candidate in (
		context_label if context_label != _("Organization") else None,
		owner_label if owner_label != _("Organization") else None,
		parent_hint,
		folder_kind_label,
		context_label,
		owner_label,
	):
		if candidate:
			return candidate
	return _("Folder")


def _display_folder_title(
	folder_doc,
	folder_cache: dict[str, Any],
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> str:
	return _display_folder_presentation(folder_doc, folder_cache, presentation_cache)["display_title"]


def _build_path(breadcrumbs: list[dict[str, Any]], title_key: str) -> str | None:
	parts = [crumb.get(title_key) for crumb in breadcrumbs if crumb.get(title_key)]
	if not parts:
		return None
	return " / ".join(parts)


def _build_folder_breadcrumbs(
	folder_doc,
	folder_cache: dict[str, Any],
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> list[dict[str, Any]]:
	chain = []
	visited = set()
	current = folder_doc

	while current and current.name not in visited:
		visited.add(current.name)
		chain.append(current)
		current = _load_folder_doc(getattr(current, "parent_drive_folder", None), folder_cache)

	chain.reverse()
	breadcrumbs: list[dict[str, Any]] = []
	for doc in chain:
		crumb = {
			"id": doc.name,
			"title": doc.title,
			"path_cache": getattr(doc, "path_cache", None),
		}
		presentation = _display_folder_presentation(doc, folder_cache, presentation_cache)
		display_title = presentation.get("display_title")
		if display_title and display_title != doc.title:
			crumb["display_title"] = display_title
		if presentation.get("display_code"):
			crumb["display_code"] = presentation["display_code"]
		breadcrumbs.append(crumb)
	return breadcrumbs


def _build_context_path(breadcrumbs: list[dict[str, Any]]) -> str | None:
	return _build_path(breadcrumbs, "title")


def _build_display_path(breadcrumbs: list[dict[str, Any]]) -> str | None:
	display_breadcrumbs = []
	for crumb in breadcrumbs:
		display_breadcrumbs.append(
			{
				**crumb,
				"display_title": crumb.get("display_title") or crumb.get("title"),
			}
		)
	return _build_path(display_breadcrumbs, "display_title")


def _serialize_folder_summary(
	folder_doc,
	folder_cache: dict[str, Any],
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> dict[str, Any]:
	breadcrumbs = _build_folder_breadcrumbs(folder_doc, folder_cache, presentation_cache)
	context_doctype = getattr(folder_doc, "context_doctype", None)
	context_name = getattr(folder_doc, "context_name", None)
	context_path = _build_context_path(breadcrumbs)
	presentation = _display_folder_presentation(folder_doc, folder_cache, presentation_cache)
	display_title = presentation.get("display_title")
	display_code = presentation.get("display_code")
	display_path = _build_display_path(breadcrumbs)
	summary = {
		"id": folder_doc.name,
		"title": folder_doc.title,
		"path_cache": getattr(folder_doc, "path_cache", None),
		"context_path": context_path,
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
	if display_title and display_title != folder_doc.title:
		summary["display_title"] = display_title
	if display_code:
		summary["display_code"] = display_code
	if display_path and display_path != context_path:
		summary["display_path"] = display_path
		if display_path != display_title:
			summary["display_caption"] = display_path
	return summary


def _serialize_optional_folder_summary(
	folder_id: str | None,
	folder_cache: dict[str, Any],
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> dict[str, Any] | None:
	folder_doc = _load_folder_doc(folder_id, folder_cache)
	if not folder_doc:
		return None
	return _serialize_folder_summary(folder_doc, folder_cache, presentation_cache)


def _root_folder_filters() -> dict[str, Any]:
	return {
		"status": "active",
		"parent_drive_folder": ["in", ["", None]],
	}


def _folder_href(folder_id: str) -> str:
	return f"/drive_workspace?folder={quote(str(folder_id or '').strip())}"


def _context_href(doctype: str, name: str, binding_role: str | None = None) -> str:
	href = (
		f"/drive_workspace?doctype={quote(str(doctype or '').strip())}&name={quote(str(name or '').strip())}"
	)
	if binding_role:
		href += f"&binding_role={quote(str(binding_role).strip())}"
	return href


def _build_upload_field(
	*,
	name: str,
	label: str,
	required: bool = False,
	placeholder: str | None = None,
	help_text: str | None = None,
) -> dict[str, Any]:
	field = {
		"name": name,
		"label": label,
		"required": required,
	}
	if placeholder:
		field["placeholder"] = placeholder
	if help_text:
		field["help"] = help_text
	return field


def _build_upload_action(
	*,
	action_id: str,
	label: str,
	description: str,
	api_method: str,
	payload: dict[str, Any],
	destination_label: str,
	fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
	action = {
		"id": action_id,
		"label": label,
		"description": description,
		"api_method": api_method,
		"payload": payload,
		"destination_label": destination_label,
	}
	if fields:
		action["fields"] = fields
	return action


def _get_upload_actions_for_context(
	doctype: str | None,
	name: str | None,
	*,
	folder_doc=None,
) -> list[dict[str, Any]]:
	if not doctype or not name:
		return []

	actions: list[dict[str, Any]] = []
	if doctype == "Supporting Material" and _can_write("Supporting Material", name):
		actions.append(
			_build_upload_action(
				action_id="supporting_material",
				label=_("Upload Material File"),
				description=_("Add the governed file for this Supporting Material record."),
				api_method="ifitwala_drive.api.materials.upload_supporting_material",
				payload={"material": name, "upload_source": "SPA"},
				destination_label=_("Course Materials"),
			)
		)

	if doctype == "Task Submission" and _can_write("Task Submission", name):
		actions.append(
			_build_upload_action(
				action_id="task_submission_artifact",
				label=_("Upload Submission Artifact"),
				description=_("Add a governed artifact to this Task Submission."),
				api_method="ifitwala_drive.api.submissions.upload_task_submission_artifact",
				payload={"task_submission": name, "upload_source": "SPA"},
				destination_label=_("Submission Artifacts"),
			)
		)

	if doctype == "Employee" and _can_write("Employee", name):
		actions.append(
			_build_upload_action(
				action_id="employee_image",
				label=_("Upload Employee Image"),
				description=_("Create or replace the governed employee profile image."),
				api_method="ifitwala_drive.api.media.upload_employee_image",
				payload={"employee": name, "upload_source": "SPA"},
				destination_label=_("Employee Image"),
			)
		)

	if doctype == "Student" and _can_write("Student", name):
		actions.append(
			_build_upload_action(
				action_id="student_image",
				label=_("Upload Student Image"),
				description=_("Create or replace the governed student profile image."),
				api_method="ifitwala_drive.api.media.upload_student_image",
				payload={"student": name, "upload_source": "SPA"},
				destination_label=_("Student Image"),
			)
		)

	if doctype == "Guardian" and _can_write("Guardian", name):
		actions.append(
			_build_upload_action(
				action_id="guardian_image",
				label=_("Upload Guardian Image"),
				description=_("Create or replace the governed guardian profile image."),
				api_method="ifitwala_drive.api.media.upload_guardian_image",
				payload={"guardian": name, "upload_source": "SPA"},
				destination_label=_("Guardian Image"),
			)
		)

	if doctype == "Student Applicant" and _can_write("Student Applicant", name):
		actions.append(
			_build_upload_action(
				action_id="applicant_profile_image",
				label=_("Upload Applicant Image"),
				description=_("Create or replace the governed applicant profile image."),
				api_method="ifitwala_drive.api.admissions.upload_applicant_profile_image",
				payload={"student_applicant": name, "upload_source": "SPA"},
				destination_label=_("Applicant Profile"),
			)
		)

	if getattr(folder_doc, "folder_kind", None) != "organization_media":
		return actions

	folder_title = str(getattr(folder_doc, "title", None) or "").strip().lower()
	organization = str(
		getattr(folder_doc, "organization", None) or getattr(folder_doc, "owner_name", None) or ""
	).strip()

	if doctype == "Organization" and _can_write("Organization", name):
		if folder_title == "logos":
			actions.append(
				_build_upload_action(
					action_id="organization_logo",
					label=_("Upload Organization Logo"),
					description=_("Replace the governed organization logo used across Ifitwala_Ed."),
					api_method="ifitwala_drive.api.media.upload_organization_logo",
					payload={"organization": name, "upload_source": "SPA"},
					destination_label=_("Organization Logos"),
				)
			)
		else:
			actions.append(
				_build_upload_action(
					action_id="organization_media_asset",
					label=_("Upload Media Asset"),
					description=_("Add a governed organization media asset for reuse across Ed surfaces."),
					api_method="ifitwala_drive.api.media.upload_organization_media_asset",
					payload={
						"organization": name,
						"scope": "organization",
						"upload_source": "SPA",
					},
					destination_label=_("Organization Media"),
					fields=[
						_build_upload_field(
							name="media_key",
							label=_("Media Key"),
							placeholder="homepage-hero",
							help_text=_("Optional stable key used for reuse and replacement."),
						)
					],
				)
			)

	if doctype == "School" and _can_write("School", name) and organization:
		if folder_title == "logos":
			actions.append(
				_build_upload_action(
					action_id="school_logo",
					label=_("Upload School Logo"),
					description=_("Replace the governed school logo used across Ifitwala_Ed."),
					api_method="ifitwala_drive.api.media.upload_school_logo",
					payload={"school": name, "upload_source": "SPA"},
					destination_label=_("School Logos"),
				)
			)
		else:
			actions.append(
				_build_upload_action(
					action_id="school_media_asset",
					label=_("Upload School Media"),
					description=_("Add a governed school-scoped media asset for reuse across Ed surfaces."),
					api_method="ifitwala_drive.api.media.upload_organization_media_asset",
					payload={
						"organization": organization,
						"school": name,
						"scope": "school",
						"upload_source": "SPA",
					},
					destination_label=_("School Media"),
					fields=[
						_build_upload_field(
							name="media_key",
							label=_("Media Key"),
							placeholder="campus-banner",
							help_text=_("Optional stable key used for reuse and replacement."),
						)
					],
				)
			)

	return actions


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
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
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

		summary = _serialize_folder_summary(folder_doc, folder_cache, presentation_cache)
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

			summary = _serialize_folder_summary(folder_doc, folder_cache, presentation_cache)
			summary["item_type"] = "folder"
			child_folders.append(summary)

		if child_folders:
			return child_folders

	return folders


def _list_accessible_root_folders(limit: int) -> list[dict[str, Any]]:
	folder_cache: dict[str, Any] = {}
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
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
		roots.append(_serialize_folder_summary(folder_doc, folder_cache, presentation_cache))

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
	display_code: str | None = None,
) -> dict[str, Any]:
	target_id_parts = [target_kind, folder or doctype or "", name or "", binding_role or ""]
	target = {
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
	if display_code:
		target["display_code"] = display_code
	return target


def _build_folder_home_target(folder_summary: dict[str, Any]) -> dict[str, Any]:
	return _build_home_target(
		target_kind="folder",
		label=folder_summary.get("display_title") or folder_summary.get("title") or _("Folder"),
		caption=folder_summary.get("display_path")
		or folder_summary.get("context_path")
		or _("Governed root folder"),
		badge=folder_summary.get("folder_kind") or _("Folder"),
		href=_folder_href(folder_summary["id"]),
		folder=folder_summary["id"],
		display_code=folder_summary.get("display_code"),
	)


def _build_context_home_target(
	*,
	doctype: str,
	name: str,
	label: str,
	caption: str,
	badge: str,
	binding_role: str | None = None,
	display_code: str | None = None,
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
		display_code=display_code,
	)


def _build_context_target_presentation(
	*,
	doctype: str,
	name: str,
	fallback_label: str | None,
	caption: str,
	badge: str,
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
	binding_role: str | None = None,
) -> dict[str, Any]:
	presentation = _resolve_context_presentation(doctype, name, presentation_cache) or {}
	resolved_label = _clean_text(presentation.get("display_title"))
	label = (
		resolved_label
		if resolved_label and resolved_label != name
		else _clean_text(fallback_label) or resolved_label or name
	)
	display_code = _clean_text(presentation.get("display_code"))
	if not display_code and label and label != name:
		display_code = name
	return _build_context_home_target(
		doctype=doctype,
		name=name,
		label=label,
		caption=caption,
		badge=badge,
		binding_role=binding_role,
		display_code=display_code,
	)


def _own_context_targets(user: str, limit: int) -> list[dict[str, Any]]:
	targets: list[dict[str, Any]] = []
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}

	for doctype, filters, fields, label_field, caption, badge in (
		(
			"Employee",
			{"user_id": user},
			["name", "employee_full_name"],
			"employee_full_name",
			_("Your employee files"),
			_("Mine"),
		),
		("Student Applicant", {"applicant_user": user}, ["name"], None, _("Your applicant files"), _("Mine")),
		(
			"Student",
			{"student_email": user},
			["name", "student_full_name"],
			"student_full_name",
			_("Your student workspace"),
			_("Mine"),
		),
	):
		rows = _safe_get_all(doctype, filters=filters, fields=fields, limit_page_length=limit)
		for row in rows:
			name = row.get("name")
			if not name or not _can_read(doctype, name):
				continue
			label = row.get(label_field) if label_field else None
			targets.append(
				_build_context_target_presentation(
					doctype=doctype,
					name=name,
					fallback_label=label or name,
					caption=caption,
					badge=badge,
					presentation_cache=presentation_cache,
				)
			)
			if len(targets) >= limit:
				return targets

	return targets


def _employee_context_targets(user: str, limit: int) -> list[dict[str, Any]]:
	roles = _current_roles(user)
	if not roles.intersection({"HR Manager", "HR User", "System Manager"}):
		return []
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}

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
			_build_context_target_presentation(
				doctype="Employee",
				name=name,
				fallback_label=label,
				caption=caption,
				badge=_("Employee"),
				presentation_cache=presentation_cache,
			)
		)
		if len(targets) >= limit:
			return targets

	return targets


def _review_assignment_targets(user: str, limit: int) -> list[dict[str, Any]]:
	roles = sorted(_current_roles(user))
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
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
				fields=[
					"name",
					"student_applicant",
					"target_type",
					"target_name",
					"source_event",
					"modified",
				],
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
			_build_context_target_presentation(
				doctype="Student Applicant",
				name=student_applicant,
				fallback_label=student_applicant,
				caption=caption,
				badge=badge,
				presentation_cache=presentation_cache,
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
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None],
	include_item_type: bool,
) -> dict[str, Any]:
	folder_summary = _serialize_optional_folder_summary(row.get("folder"), folder_cache, presentation_cache)
	raw_title = _clean_text(row.get("display_name"))
	binding_role = (binding or {}).get("binding_role")
	display_title = raw_title
	if not display_title or _looks_like_opaque_identifier(display_title):
		display_title = (
			_BINDING_ROLE_DISPLAY_LABELS.get(_clean_text(binding_role))
			or _clean_text(row.get("slot")).replace("_", " ").strip().capitalize()
			or _("Governed file")
		)
	entry = {
		"id": row["name"],
		"title": row.get("display_name"),
		"canonical_ref": row.get("canonical_ref"),
		"slot": row.get("slot"),
		"current_version_no": row.get("current_version_no"),
		"preview_status": row.get("preview_status"),
		"binding_role": binding_role,
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
	if display_title and display_title != raw_title:
		entry["display_title"] = display_title
	if (folder_summary or {}).get("display_path"):
		entry["display_path"] = folder_summary.get("display_path")
	if include_item_type:
		entry["item_type"] = "file"
	return entry


def _derive_direct_binding_role(row: dict[str, Any]) -> str | None:
	owner_doctype = str(row.get("owner_doctype") or "").strip()
	slot = str(row.get("slot") or "").strip()
	attached_doctype = str(row.get("attached_doctype") or "").strip()

	if owner_doctype == "Supporting Material" and slot == "material_file":
		return "supporting_material"
	if owner_doctype == "Task Submission":
		return "submission_artifact"
	if owner_doctype == "Organization":
		return "organization_media"
	if owner_doctype == "Student" and slot == "profile_image":
		return "student_image"
	if owner_doctype == "Employee" and slot == "profile_image":
		return "employee_image"
	if owner_doctype == "Student Applicant" and attached_doctype == "Applicant Document Item":
		return "applicant_document"
	return None


def _matches_requested_binding_role(row: dict[str, Any], binding_role: str | None) -> bool:
	if not binding_role:
		return True
	return _derive_direct_binding_role(row) == binding_role


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
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
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
				getattr(child_doc, "owner_doctype", None)
				if hasattr(child_doc, "owner_doctype")
				else child.get("owner_doctype"),
				getattr(child_doc, "owner_name", None)
				if hasattr(child_doc, "owner_name")
				else child.get("owner_name"),
			):
				continue
			if hasattr(child_doc, "name"):
				child_summary = _serialize_folder_summary(child_doc, folder_cache, presentation_cache)
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
					presentation_cache=presentation_cache,
					include_item_type=True,
				)
			)

	response = {
		"folder": _serialize_folder_summary(folder_doc, folder_cache, presentation_cache),
		"items": items,
	}
	upload_actions = _get_upload_actions_for_context(
		getattr(folder_doc, "context_doctype", None),
		getattr(folder_doc, "context_name", None),
		folder_doc=folder_doc,
	)
	if upload_actions:
		response["upload_actions"] = upload_actions
	return response


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

	files = []
	folder_cache: dict[str, Any] = {}
	presentation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
	seen_drive_files: set[str] = set()
	requested_binding_role = payload.get("binding_role")

	direct_drive_files = frappe.get_all(
		"Drive File",
		filters={
			"owner_doctype": doctype,
			"owner_name": name,
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
			"owner_doctype",
			"owner_name",
		],
		order_by="modified desc",
	)
	for row in direct_drive_files:
		if row.get("owner_doctype") != doctype or row.get("owner_name") != name:
			continue
		if not _matches_requested_binding_role(row, requested_binding_role):
			continue
		seen_drive_files.add(row["name"])
		entry = _serialize_file_entry(
			row,
			binding={"binding_role": _derive_direct_binding_role(row)},
			folder_cache=folder_cache,
			presentation_cache=presentation_cache,
			include_item_type=False,
		)
		entry["drive_file_id"] = row["name"]
		files.append(entry)

	binding_filters: dict[str, Any] = {
		"binding_doctype": doctype,
		"binding_name": name,
		"status": "active",
	}
	if requested_binding_role:
		binding_filters["binding_role"] = requested_binding_role

	bindings = frappe.get_all(
		"Drive Binding",
		filters=binding_filters,
		fields=["drive_file", "binding_role", "slot", "is_primary", "modified"],
		order_by="is_primary desc, modified desc",
	)

	drive_file_ids = []
	binding_by_file: dict[str, dict[str, Any]] = {}
	for row in bindings:
		drive_file_id = row["drive_file"]
		if drive_file_id in seen_drive_files:
			continue
		if drive_file_id not in binding_by_file:
			binding_by_file[drive_file_id] = row
			drive_file_ids.append(drive_file_id)

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
				"owner_doctype",
				"owner_name",
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
				presentation_cache=presentation_cache,
				include_item_type=False,
			)
			entry["drive_file_id"] = drive_file_id
			entry["slot"] = drive_file.get("slot") or binding.get("slot")
			files.append(entry)

	items = list(context_folders)
	items.extend({**file, "item_type": "file"} for file in files)

	context_summary = {
		"doctype": doctype,
		"name": name,
	}
	context_summary.update(_context_presentation_fields(doctype, name, presentation_cache))
	response = {
		"context": context_summary,
		"folders": context_folders,
		"files": files,
		"items": items,
	}
	upload_actions = _get_upload_actions_for_context(doctype, name)
	if upload_actions:
		response["upload_actions"] = upload_actions
	return response
