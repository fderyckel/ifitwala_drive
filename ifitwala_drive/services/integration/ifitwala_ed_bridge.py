from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module

_ED_MODULE = "ifitwala_ed.integrations.drive.bridge"
_BROWSE_TITLE_FIELD_CANDIDATES = {
	"Course": ("course_name",),
	"Employee": ("employee_full_name",),
	"Guardian": ("guardian_full_name",),
	"Organization": ("organization_name",),
	"School": ("school_name",),
	"Student": ("student_preferred_name", "student_full_name"),
	"Student Applicant": ("title", "student_preferred_name"),
	"Supporting Material": ("title",),
	"Task": ("title",),
}


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def _maybe_call_delegate(name: str, *args, **kwargs):
	try:
		module = load_ed_drive_module(_ED_MODULE)
	except Exception:
		return None
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		return None
	return callable_obj(*args, **kwargs)


def _safe_text(value: Any) -> str | None:
	text = str(value or "").strip()
	return text or None


def _meta_title_field(doctype: str) -> str | None:
	if not hasattr(frappe, "get_meta"):
		return None
	try:
		meta = frappe.get_meta(doctype)
	except Exception:
		return None
	title_field = getattr(meta, "title_field", None)
	if not title_field and isinstance(meta, dict):
		title_field = meta.get("title_field")
	return _safe_text(title_field)


def _presentation_field_candidates(doctype: str) -> list[str]:
	candidates: list[str] = []
	for fieldname in _BROWSE_TITLE_FIELD_CANDIDATES.get(doctype, ()):
		if fieldname not in candidates:
			candidates.append(fieldname)
	title_field = _meta_title_field(doctype)
	if title_field and title_field not in candidates:
		candidates.append(title_field)
	for fallback in ("title", "name"):
		if fallback not in candidates:
			candidates.append(fallback)
	return candidates


def _read_doc_value(doc, fieldname: str) -> str | None:
	value = None
	if hasattr(doc, fieldname):
		value = getattr(doc, fieldname)
	elif hasattr(doc, "get"):
		try:
			value = doc.get(fieldname)
		except Exception:
			value = None
	return _safe_text(value)


def _fallback_browse_context_presentation(doctype: str, name: str) -> dict[str, Any] | None:
	if not doctype or not name:
		return None
	if not frappe.db.exists(doctype, name):
		return None

	try:
		doc = frappe.get_doc(doctype, name)
	except Exception:
		return None

	display_title = None
	for fieldname in _presentation_field_candidates(doctype):
		value = _read_doc_value(doc, fieldname)
		if not value:
			continue
		if fieldname == "name" and display_title:
			continue
		display_title = value
		if fieldname != "name":
			break

	display_title = display_title or str(name).strip()
	display_code = str(name).strip()
	if display_code == display_title:
		display_code = None

	return {
		"display_title": display_title,
		"display_code": display_code,
	}


def resolve_browse_context_presentation(doctype: str, name: str) -> dict[str, Any] | None:
	delegated = _maybe_call_delegate("resolve_browse_context_presentation", doctype, name)
	if isinstance(delegated, dict):
		display_title = _safe_text(delegated.get("display_title")) or _safe_text(delegated.get("title"))
		display_code = _safe_text(delegated.get("display_code")) or _safe_text(delegated.get("code"))
		if not display_title:
			return None
		if display_code == display_title:
			display_code = None
		return {
			"display_title": display_title,
			"display_code": display_code,
		}

	return _fallback_browse_context_presentation(doctype, name)


def reconcile_upload_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("reconcile_upload_session_payload", payload)


def resolve_finalize_contract(upload_session_doc) -> dict[str, Any]:
	return _call_delegate("resolve_finalize_contract", upload_session_doc)


def run_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_post_finalize", upload_session_doc, created_file)
