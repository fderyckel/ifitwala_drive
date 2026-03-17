# ifitwala_drive/ifitwala_drive/services/uploads/validation.py

from __future__ import annotations

from typing import Any, Dict, Iterable

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


def require_fields(payload: Dict[str, Any], fields: Iterable[str]) -> None:
	for fieldname in fields:
		if not payload.get(fieldname):
			frappe.throw(_("Missing required field: {0}").format(fieldname))


def validate_create_session_payload(payload: Dict[str, Any]) -> None:
	require_fields(payload, REQUIRED_CREATE_SESSION_FIELDS)

	if payload.get("owner_doctype") == "User":
		frappe.throw(_("Owner Doctype cannot be User. Use a business document owner."))

	if payload.get("slot") is not None and not str(payload["slot"]).strip():
		frappe.throw(_("Slot is required."))

	expected_size_bytes = payload.get("expected_size_bytes")
	if expected_size_bytes is not None and int(expected_size_bytes) < 0:
		frappe.throw(_("Expected Size (Bytes) cannot be negative."))

	if payload.get("school"):
		if not frappe.db.exists("School", payload["school"]):
			frappe.throw(_("School does not exist: {0}").format(payload["school"]))

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

	received_size_bytes = payload.get("received_size_bytes")
	if received_size_bytes is not None and int(received_size_bytes) < 0:
		frappe.throw(_("Received Size (Bytes) cannot be negative."))
