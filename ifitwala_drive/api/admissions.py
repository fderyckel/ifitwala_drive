from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.integration.ifitwala_ed_admissions import (
	issue_admissions_file_download_grant_service,
	issue_admissions_file_preview_grant_service,
	upload_applicant_document_service,
	upload_applicant_guardian_image_service,
	upload_applicant_health_vaccination_proof_service,
	upload_applicant_profile_image_service,
)


@frappe.whitelist()
def upload_applicant_document(
	student_applicant: str,
	filename_original: str,
	document_type: str | None = None,
	applicant_document: str | None = None,
	applicant_document_item: str | None = None,
	item_key: str | None = None,
	item_label: str | None = None,
	slot: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
	is_private: int | str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for admissions document uploads."""
	return upload_applicant_document_service(
		compact_payload(
			student_applicant=student_applicant,
			filename_original=filename_original,
			document_type=document_type,
			applicant_document=applicant_document,
			applicant_document_item=applicant_document_item,
			item_key=item_key,
			item_label=item_label,
			slot=slot,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
			is_private=is_private,
		)
	)


@frappe.whitelist()
def upload_applicant_profile_image(
	student_applicant: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant profile image uploads."""
	return upload_applicant_profile_image_service(
		compact_payload(
			student_applicant=student_applicant,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_applicant_guardian_image(
	student_applicant: str,
	guardian_row_name: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant guardian image uploads."""
	return upload_applicant_guardian_image_service(
		compact_payload(
			student_applicant=student_applicant,
			guardian_row_name=guardian_row_name,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_applicant_health_vaccination_proof(
	student_applicant: str,
	applicant_health_profile: str,
	vaccine_name: str,
	date: str,
	filename_original: str,
	row_index: int | str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant health vaccination proof uploads."""
	return upload_applicant_health_vaccination_proof_service(
		compact_payload(
			student_applicant=student_applicant,
			applicant_health_profile=applicant_health_profile,
			vaccine_name=vaccine_name,
			date=date,
			filename_original=filename_original,
			row_index=row_index,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def issue_admissions_file_download_grant(
	file_id: str | None = None,
	drive_file_id: str | None = None,
	canonical_ref: str | None = None,
	context_doctype: str | None = None,
	context_name: str | None = None,
) -> dict[str, Any]:
	return issue_admissions_file_download_grant_service(
		compact_payload(
			file_id=file_id,
			drive_file_id=drive_file_id,
			canonical_ref=canonical_ref,
			context_doctype=context_doctype,
			context_name=context_name,
		)
	)


@frappe.whitelist()
def issue_admissions_file_preview_grant(
	file_id: str | None = None,
	drive_file_id: str | None = None,
	canonical_ref: str | None = None,
	context_doctype: str | None = None,
	context_name: str | None = None,
	derivative_role: str | None = None,
) -> dict[str, Any]:
	return issue_admissions_file_preview_grant_service(
		compact_payload(
			file_id=file_id,
			drive_file_id=drive_file_id,
			canonical_ref=canonical_ref,
			context_doctype=context_doctype,
			context_name=context_name,
			derivative_role=derivative_role,
		)
	)
