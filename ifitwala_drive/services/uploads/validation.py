# ifitwala_drive/ifitwala_drive/services/uploads/validation.py

from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

import frappe
from frappe import _


REQUIRED_CREATE_SESSION_FIELDS: tuple[str, ...] = (
	"owner_doctype",
	"owner_name",
	"attached_doctype",
	"attached_name",
	"organization",
	"primary_subject_type",
	"primary_subject_id",
	"data_class",
	"purpose",
	"retention_policy",
	"slot",
	"filename_original",
)

REQUIRED_FINALIZE_FIELDS: tuple[str, ...] = (
	"upload_session_id",
)


_OPTIONAL_SCHOOL_SUBJECT_TYPES = {"Employee", "Organization"}


def _has_value(value: Any) -> bool:
	if value is None:
		return False

	if isinstance(value, str):
		return bool(value.strip())

	return True


def require_fields(payload: Dict[str, Any], fields: Iterable[str]) -> None:
	for fieldname in fields:
		if not _has_value(payload.get(fieldname)):
			frappe.throw(_("Missing required field: {0}").format(fieldname))


def _is_school_required(primary_subject_type: str | None) -> bool:
	try:
		from ifitwala_ed.utilities.file_classification_contract import (
			is_school_required_for_subject_type,
		)
	except ImportError:
		return (primary_subject_type or "").strip() not in _OPTIONAL_SCHOOL_SUBJECT_TYPES

	return is_school_required_for_subject_type(primary_subject_type)


def _parse_optional_non_negative_int(payload: Dict[str, Any], fieldname: str, label: str) -> None:
	value = payload.get(fieldname)
	if value in (None, ""):
		return

	try:
		value = int(value)
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be an integer.").format(label))

	if value < 0:
		frappe.throw(_("{0} cannot be negative.").format(label))


def _validate_secondary_subjects(secondary_subjects: Any) -> None:
	if secondary_subjects in (None, []):
		return

	if not isinstance(secondary_subjects, Sequence) or isinstance(secondary_subjects, (str, bytes)):
		frappe.throw(_("secondary_subjects must be a list of subject rows."))

	for row in secondary_subjects:
		if not isinstance(row, dict):
			frappe.throw(_("secondary_subjects entries must be dict rows."))

		if not _has_value(row.get("subject_type")):
			frappe.throw(_("Secondary subject rows must include subject_type."))

		if not _has_value(row.get("subject_id")):
			frappe.throw(_("Secondary subject rows must include subject_id."))


def validate_create_session_payload(payload: Dict[str, Any]) -> None:
	require_fields(payload, REQUIRED_CREATE_SESSION_FIELDS)

	if payload.get("owner_doctype") == "User":
		frappe.throw(_("Owner Doctype cannot be User. Use a business document owner."))

	if payload.get("owner_name") == frappe.session.user:
		frappe.throw(_("Owner Name appears to be the current user. Owner must be a business document."))

	if _is_school_required(payload.get("primary_subject_type")) and not _has_value(payload.get("school")):
		frappe.throw(_("School is required for this upload context."))

	_parse_optional_non_negative_int(payload, "expected_size_bytes", _("Expected Size (Bytes)"))
	_validate_secondary_subjects(payload.get("secondary_subjects"))

	if payload.get("school"):
		if not frappe.db.exists("School", payload["school"]):
			frappe.throw(_("School does not exist: {0}").format(payload["school"]))

	if payload.get("folder") and not frappe.db.exists("Drive Folder", payload["folder"]):
		frappe.throw(_("Drive Folder does not exist: {0}").format(payload["folder"]))

	if not frappe.db.exists("Organization", payload["organization"]):
		frappe.throw(_("Organization does not exist: {0}").format(payload["organization"]))

	if not frappe.db.exists(payload["owner_doctype"], payload["owner_name"]):
		frappe.throw(
			_("Owner document does not exist: {0} {1}").format(
				payload["owner_doctype"], payload["owner_name"]
			)
		)

	if not frappe.db.exists(payload["attached_doctype"], payload["attached_name"]):
		frappe.throw(
			_("Attached document does not exist: {0} {1}").format(
				payload["attached_doctype"], payload["attached_name"]
			)
		)


def validate_finalize_session_payload(payload: Dict[str, Any]) -> None:
	require_fields(payload, REQUIRED_FINALIZE_FIELDS)
	_parse_optional_non_negative_int(payload, "received_size_bytes", _("Received Size (Bytes)"))
