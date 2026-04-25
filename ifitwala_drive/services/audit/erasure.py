from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.audit.events import record_drive_access_event
from ifitwala_drive.services.files.derivatives import delete_derivative_artifacts_for_drive_file
from ifitwala_drive.services.storage.base import get_storage_backend

_ALLOWED_ERASURE_SCOPES = {"all", "files_only", "slot_only"}
_METADATA_FILTER_FIELDS = (
	"owner_doctype",
	"owner_name",
	"attached_doctype",
	"attached_name",
	"slot",
	"purpose",
	"retention_policy",
	"organization",
	"school",
	"data_class",
)
_DECISION_MATCH_FIELDS = ("drive_file_id", "name", *_METADATA_FILTER_FIELDS)
_DRIVE_FILE_AUDIT_FIELDS = [
	"name",
	"status",
	"erasure_state",
	"legal_hold",
	"owner_doctype",
	"owner_name",
	"attached_doctype",
	"attached_name",
	"organization",
	"school",
	"primary_subject_type",
	"primary_subject_id",
	"data_class",
	"purpose",
	"retention_policy",
	"slot",
	"file",
	"storage_backend",
	"storage_object_key",
	"current_version",
]
_ALLOWED_DECISIONS = {"erase", "retain", "anonymize", "skip"}
_DECISION_ALIASES = {"delete": "erase", "deleted": "erase", "erased": "erase"}


def _get_all(doctype: str, *, filters: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
	get_all = getattr(frappe, "get_all", None)
	if callable(get_all):
		return get_all(doctype, filters=filters, fields=fields)

	db_get_all = getattr(getattr(frappe, "db", None), "get_all", None)
	if callable(db_get_all):
		return db_get_all(doctype, filters=filters, fields=fields)

	return []


def _clean_text(value: Any) -> str:
	return str(value or "").strip()


def _coerce_mapping(value: Any, *, fieldname: str) -> dict[str, Any]:
	if value in (None, ""):
		return {}
	if isinstance(value, dict):
		return value
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except Exception:
			frappe.throw(_("{0} must be valid JSON.").format(fieldname))
		if isinstance(parsed, dict):
			return parsed
	frappe.throw(_("{0} must be a mapping.").format(fieldname))
	return {}


def _coerce_list(value: Any, *, fieldname: str) -> list[dict[str, Any]]:
	if value in (None, ""):
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except Exception:
			frappe.throw(_("{0} must be valid JSON.").format(fieldname))
	if not isinstance(value, list):
		frappe.throw(_("{0} must be a list.").format(fieldname))
	rows: list[dict[str, Any]] = []
	for row in value:
		if not isinstance(row, dict):
			frappe.throw(_("{0} entries must be mappings.").format(fieldname))
		rows.append(row)
	return rows


def _normalize_metadata_filters(payload: dict[str, Any]) -> dict[str, str]:
	raw_filters = _coerce_mapping(payload.get("metadata_filters"), fieldname="metadata_filters")
	merged = {**raw_filters}
	for fieldname in _METADATA_FILTER_FIELDS:
		if payload.get(fieldname) not in (None, ""):
			merged[fieldname] = payload.get(fieldname)

	return {
		fieldname: _clean_text(merged.get(fieldname))
		for fieldname in _METADATA_FILTER_FIELDS
		if _clean_text(merged.get(fieldname))
	}


def _normalize_decision(value: Any) -> str:
	decision = _clean_text(value).lower()
	decision = _DECISION_ALIASES.get(decision, decision)
	if decision not in _ALLOWED_DECISIONS:
		frappe.throw(_("Invalid erasure decision: {0}").format(decision or "<empty>"))
	return decision


def _normalize_decision_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
	rows = _coerce_list(
		payload.get("decision_items", payload.get("decisions")),
		fieldname="decision_items",
	)
	normalized: list[dict[str, Any]] = []
	for row in rows:
		decision = _normalize_decision(row.get("decision"))
		selector = {
			fieldname: _clean_text(row.get(fieldname))
			for fieldname in _DECISION_MATCH_FIELDS
			if _clean_text(row.get(fieldname))
		}
		if not selector:
			frappe.throw(_("Erasure decision items must include drive_file_id or metadata selectors."))
		normalized.append(
			{
				**selector,
				"decision": decision,
				"reason": _clean_text(row.get("reason")) or f"ed_decision_{decision}",
			}
		)
	return normalized


def _validate_create_payload(payload: dict[str, Any]) -> None:
	for fieldname in ("data_subject_type", "data_subject_id"):
		if not payload.get(fieldname):
			frappe.throw(_("Missing required field: {0}").format(fieldname))

	scope = str(payload.get("scope") or "files_only").strip()
	if scope not in _ALLOWED_ERASURE_SCOPES:
		frappe.throw(_("Invalid erasure request scope: {0}").format(scope))

	if scope == "slot_only" and not payload.get("slot_filter"):
		frappe.throw(_("Slot Filter is required when creating a slot-scoped erasure request."))


def create_drive_erasure_request_service(payload: dict[str, Any]) -> dict[str, Any]:
	_validate_create_payload(payload)
	doc = frappe.get_doc(
		{
			"doctype": "Drive Erasure Request",
			"data_subject_type": payload["data_subject_type"],
			"data_subject_id": payload["data_subject_id"],
			"requested_by": getattr(getattr(frappe, "session", None), "user", None),
			"request_reason": payload.get("request_reason"),
			"scope": payload.get("scope") or "files_only",
			"slot_filter": payload.get("slot_filter"),
			"status": payload.get("status") or "draft",
		}
	)
	doc.insert(ignore_permissions=True)
	return {
		"erasure_request_id": doc.name,
		"status": doc.status,
		"data_subject_type": doc.data_subject_type,
		"data_subject_id": doc.data_subject_id,
		"scope": doc.scope,
		"slot_filter": getattr(doc, "slot_filter", None),
	}


def _iter_matching_drive_files(
	request_doc, *, metadata_filters: dict[str, str] | None = None
) -> list[dict[str, Any]]:
	filters = {
		"primary_subject_type": request_doc.data_subject_type,
		"primary_subject_id": request_doc.data_subject_id,
	}
	if request_doc.scope == "slot_only":
		filters["slot"] = request_doc.slot_filter
	for fieldname, value in (metadata_filters or {}).items():
		if fieldname == "slot" and filters.get("slot") and filters["slot"] != value:
			return []
		filters[fieldname] = value

	return _get_all(
		"Drive File",
		filters=filters,
		fields=_DRIVE_FILE_AUDIT_FIELDS,
	)


def _iter_versions_for_file(drive_file_id: str) -> list[dict[str, Any]]:
	return _get_all(
		"Drive File Version",
		filters={"drive_file": drive_file_id},
		fields=["name", "file", "storage_object_key"],
	)


def _iter_active_bindings_for_file(drive_file_id: str) -> list[dict[str, Any]]:
	return _get_all(
		"Drive Binding",
		filters={"drive_file": drive_file_id, "status": "active"},
		fields=["name"],
	)


def _scrub_file_doc(file_id: str | None) -> None:
	file_id = str(file_id or "").strip()
	if not file_id or not frappe.db.exists("File", file_id):
		return

	try:
		file_doc = frappe.get_doc("File", file_id)
	except Exception:
		return

	if hasattr(file_doc, "file_url"):
		file_doc.file_url = None
	if hasattr(file_doc, "content_hash"):
		file_doc.content_hash = None
	if hasattr(file_doc, "save"):
		file_doc.save(ignore_permissions=True)


def _erase_drive_file(file_row: dict[str, Any], *, erasure_request_id: str) -> None:
	drive_file_id = str(file_row.get("name") or "").strip()
	if not drive_file_id:
		return

	versions = _iter_versions_for_file(drive_file_id)
	object_keys = {
		str(row.get("storage_object_key") or "").strip()
		for row in [*versions, file_row]
		if str(row.get("storage_object_key") or "").strip()
	}
	file_ids = {
		str(row.get("file") or "").strip()
		for row in [*versions, file_row]
		if str(row.get("file") or "").strip()
	}

	storage = get_storage_backend(file_row.get("storage_backend"))
	for object_key in object_keys:
		storage.delete_object(object_key=object_key)

	for file_id in file_ids:
		_scrub_file_doc(file_id)

	delete_derivative_artifacts_for_drive_file(drive_file_id=drive_file_id)

	drive_doc = frappe.get_doc("Drive File", drive_file_id)
	drive_doc.status = "erased"
	drive_doc.preview_status = "not_applicable"
	drive_doc.erasure_state = "erased"
	drive_doc.save(ignore_permissions=True)

	for binding_row in _iter_active_bindings_for_file(drive_file_id):
		binding_id = str(binding_row.get("name") or "").strip()
		if not binding_id:
			continue
		binding_doc = frappe.get_doc("Drive Binding", binding_id)
		binding_doc.status = "inactive"
		binding_doc.save(ignore_permissions=True)

	record_drive_access_event(
		drive_file_id=drive_file_id,
		drive_file_version_id=file_row.get("current_version"),
		event_type="erase",
		metadata={"erasure_request_id": erasure_request_id, "slot": file_row.get("slot")},
	)


def _audit_item(file_row: dict[str, Any], *, decision: str, reason: str) -> dict[str, Any]:
	return {
		"drive_file_id": file_row.get("name"),
		"file_id": file_row.get("file"),
		"owner_doctype": file_row.get("owner_doctype"),
		"owner_name": file_row.get("owner_name"),
		"attached_doctype": file_row.get("attached_doctype"),
		"attached_name": file_row.get("attached_name"),
		"primary_subject_type": file_row.get("primary_subject_type"),
		"primary_subject_id": file_row.get("primary_subject_id"),
		"organization": file_row.get("organization"),
		"school": file_row.get("school"),
		"slot": file_row.get("slot"),
		"purpose": file_row.get("purpose"),
		"retention_policy": file_row.get("retention_policy"),
		"status": file_row.get("status"),
		"erasure_state": file_row.get("erasure_state"),
		"legal_hold": int(file_row.get("legal_hold") or 0),
		"decision": decision,
		"reason": reason,
	}


def _decision_matches_file(decision_item: dict[str, Any], file_row: dict[str, Any]) -> bool:
	drive_file_id = _clean_text(decision_item.get("drive_file_id") or decision_item.get("name"))
	if drive_file_id:
		return drive_file_id == _clean_text(file_row.get("name"))

	for fieldname in _METADATA_FILTER_FIELDS:
		expected = _clean_text(decision_item.get(fieldname))
		if expected and expected != _clean_text(file_row.get(fieldname)):
			return False
	return True


def _resolve_file_decision(
	file_row: dict[str, Any],
	decision_items: list[dict[str, Any]],
) -> tuple[str, str]:
	if not decision_items:
		return "erase", "approved_subject_erasure"

	for decision_item in decision_items:
		if _decision_matches_file(decision_item, file_row):
			return decision_item["decision"], decision_item["reason"]

	return "skip", "no_ed_erasure_decision"


def execute_drive_erasure_request_service(payload: dict[str, Any]) -> dict[str, Any]:
	erasure_request_id = payload.get("erasure_request_id")
	if not erasure_request_id:
		frappe.throw(_("Missing required field: erasure_request_id"))

	request_doc = frappe.get_doc("Drive Erasure Request", erasure_request_id)
	if request_doc.status not in {"approved", "executing"}:
		frappe.throw(
			_("Drive Erasure Request must be approved before execution. Current status: {0}").format(
				request_doc.status
			)
		)

	request_doc.status = "executing"
	request_doc.save(ignore_permissions=True)

	deleted_count = 0
	blocked_count = 0
	slots_touched: set[str] = set()
	erased: list[dict[str, Any]] = []
	retained: list[dict[str, Any]] = []
	skipped: list[dict[str, Any]] = []
	metadata_filters = _normalize_metadata_filters(payload)
	decision_items = _normalize_decision_items(payload)

	for file_row in _iter_matching_drive_files(request_doc, metadata_filters=metadata_filters):
		slot = str(file_row.get("slot") or "").strip()
		if slot:
			slots_touched.add(slot)

		if str(file_row.get("status") or "").strip() == "erased":
			skipped.append(_audit_item(file_row, decision="skip", reason="already_erased"))
			continue

		if int(file_row.get("legal_hold") or 0):
			drive_doc = frappe.get_doc("Drive File", file_row["name"])
			drive_doc.erasure_state = "blocked_legal"
			drive_doc.save(ignore_permissions=True)
			blocked_count += 1
			retained.append(_audit_item(file_row, decision="retain", reason="legal_hold"))
			continue

		decision, reason = _resolve_file_decision(file_row, decision_items)
		if decision == "retain":
			retained.append(_audit_item(file_row, decision=decision, reason=reason))
			continue
		if decision == "anonymize":
			retained.append(
				_audit_item(
					file_row,
					decision=decision,
					reason=reason or "anonymize_structured_record_file_retained",
				)
			)
			continue
		if decision == "skip":
			skipped.append(_audit_item(file_row, decision=decision, reason=reason))
			continue

		_erase_drive_file(file_row, erasure_request_id=request_doc.name)
		deleted_count += 1
		erased.append(_audit_item(file_row, decision="erase", reason=reason))

	request_doc.result_deleted_count = deleted_count
	request_doc.result_blocked_count = blocked_count
	request_doc.executed_on = now_datetime()
	request_doc.status = "blocked" if blocked_count else "completed"
	request_doc.save(ignore_permissions=True)

	return {
		"erasure_request_id": request_doc.name,
		"status": request_doc.status,
		"deleted_count": deleted_count,
		"blocked_count": blocked_count,
		"retained_count": len(retained),
		"skipped_count": len(skipped),
		"slots_touched": sorted(slots_touched),
		"metadata_filters": metadata_filters,
		"erased": erased,
		"retained": retained,
		"skipped": skipped,
	}
