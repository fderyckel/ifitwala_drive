from __future__ import annotations

from typing import Final

import frappe
from frappe import _

_EXACT_SLOTS: Final[tuple[str, ...]] = (
	"submission",
	"feedback",
	"rubric_evidence",
	"material_file",
	"profile_image",
	"portfolio_artefact",
)

_PREFIX_SLOTS: Final[tuple[str, ...]] = (
	"identity_",
	"prior_",
	"supporting_material__",
	"communication_attachment__",
	"expense_claim_receipt__",
	"guardian_profile_image__",
	"health_vaccination_proof_",
	"organization_logo__",
	"school_logo__",
	"school_gallery_image__",
	"organization_media__",
)


def normalize_slot(slot: str | None) -> str:
	return str(slot or "").strip().lower()


def is_allowed_slot(slot: str | None) -> bool:
	normalized = normalize_slot(slot)
	if not normalized:
		return False

	if normalized in _EXACT_SLOTS:
		return True

	for prefix in _PREFIX_SLOTS:
		if normalized.startswith(prefix) and len(normalized) > len(prefix):
			return True

	return False


def validate_slot(slot: str | None) -> str:
	normalized = normalize_slot(slot)
	if is_allowed_slot(normalized):
		return normalized

	frappe.throw(_("Slot is not part of the canonical Drive slot registry: {0}").format(slot or ""))
