from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.integration.ifitwala_ed_admissions import (
	upload_applicant_guardian_image_service,
	upload_applicant_health_vaccination_proof_service,
	upload_applicant_profile_image_service,
	upload_applicant_document_service,
)


@frappe.whitelist()
def upload_applicant_document(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for admissions document uploads."""
	return upload_applicant_document_service(kwargs)


@frappe.whitelist()
def upload_applicant_profile_image(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant profile image uploads."""
	return upload_applicant_profile_image_service(kwargs)


@frappe.whitelist()
def upload_applicant_guardian_image(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant guardian image uploads."""
	return upload_applicant_guardian_image_service(kwargs)


@frappe.whitelist()
def upload_applicant_health_vaccination_proof(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant health vaccination proof uploads."""
	return upload_applicant_health_vaccination_proof_service(kwargs)
