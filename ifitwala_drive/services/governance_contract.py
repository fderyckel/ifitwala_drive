from __future__ import annotations

import frappe
from frappe import _

_FALLBACK_ALLOWED_FILE_PURPOSES: tuple[str, ...] = (
	"text",
	"identification_document",
	"contract",
	"assessment_submission",
	"assessment_feedback",
	"safeguarding_evidence",
	"medical_record",
	"visa_document",
	"policy_acknowledgement",
	"background_check",
	"learning_resource",
	"academic_report",
	"employee_profile_display",
	"guardian_profile_display",
	"student_profile_display",
	"applicant_profile_display",
	"organization_public_media",
	"portfolio_evidence",
	"journal_attachment",
	"portfolio_export",
	"journal_export",
	"administrative",
	"other",
)

try:
	from ifitwala_ed.utilities.file_classification_contract import (
		ALLOWED_FILE_PURPOSES as _ED_ALLOWED_FILE_PURPOSES,
	)
except ImportError:
	_ALLOWED_FILE_PURPOSES = _FALLBACK_ALLOWED_FILE_PURPOSES
else:
	_ALLOWED_FILE_PURPOSES = tuple(
		str(purpose).strip() for purpose in _ED_ALLOWED_FILE_PURPOSES if str(purpose).strip()
	)

_ALLOWED_FILE_PURPOSES_SET = set(_ALLOWED_FILE_PURPOSES)


def _normalize_purpose(purpose: str | None) -> str:
	return str(purpose or "").strip()


def is_allowed_file_purpose(purpose: str | None) -> bool:
	return _normalize_purpose(purpose) in _ALLOWED_FILE_PURPOSES_SET


def format_allowed_file_purposes() -> str:
	return '", "'.join(_ALLOWED_FILE_PURPOSES)


def validate_file_purpose(purpose: str | None, *, field_label: str = "Purpose") -> str:
	normalized = _normalize_purpose(purpose)
	if is_allowed_file_purpose(normalized):
		return normalized

	frappe.throw(
		_('{0} cannot be "{1}". It should be one of "{2}".').format(
			field_label,
			normalized,
			format_allowed_file_purposes(),
		)
	)

	return normalized
