from __future__ import annotations

import re

import frappe
from frappe import _

_MAX_SLOT_LENGTH = 140
_SLOT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,139}$")


def normalize_slot(slot: str | None) -> str:
	return str(slot or "").strip().lower()


def is_allowed_slot(slot: str | None) -> bool:
	normalized = normalize_slot(slot)
	return bool(normalized) and bool(_SLOT_PATTERN.fullmatch(normalized))


def validate_slot(slot: str | None) -> str:
	normalized = normalize_slot(slot)
	if not normalized:
		frappe.throw(_("Slot is required."))

	if len(normalized) > _MAX_SLOT_LENGTH:
		frappe.throw(_("Slot cannot be longer than {0} characters.").format(_MAX_SLOT_LENGTH))

	if is_allowed_slot(normalized):
		return normalized

	frappe.throw(
		_(
			"Slot must be a workflow-resolved key using only lowercase letters, numbers, dots, underscores, and hyphens."
		)
	)
