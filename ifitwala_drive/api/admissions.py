from __future__ import annotations

import json
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


def _has_bound_value(value: Any) -> bool:
	if value is None:
		return False
	if isinstance(value, str):
		return bool(value.strip())
	return True


def _parse_request_payload(value: Any) -> dict[str, Any] | None:
	if isinstance(value, dict):
		return value
	if isinstance(value, (bytes, bytearray)):
		try:
			value = value.decode()
		except Exception:
			return None
	if isinstance(value, str):
		try:
			payload = json.loads(value)
		except Exception:
			return None
		return payload if isinstance(payload, dict) else None
	return None


def _request_json_payload() -> dict[str, Any]:
	request = getattr(frappe, "request", None)
	if not request:
		return {}

	get_json = getattr(request, "get_json", None)
	if callable(get_json):
		try:
			payload = get_json(silent=True)
		except TypeError:
			try:
				payload = get_json()
			except Exception:
				payload = None
		except Exception:
			payload = None
		parsed_payload = _parse_request_payload(payload)
		if isinstance(parsed_payload, dict):
			return parsed_payload

	parsed_payload = _parse_request_payload(getattr(request, "data", None))
	if isinstance(parsed_payload, dict):
		return parsed_payload
	return {}


def _request_value(key: str, current_value: Any = None) -> Any:
	if _has_bound_value(current_value):
		return current_value

	form_dict = getattr(frappe, "form_dict", None)
	if form_dict and hasattr(form_dict, "get"):
		value = form_dict.get(key)
		if _has_bound_value(value):
			return value

		args = _parse_request_payload(form_dict.get("args"))
		if isinstance(args, dict):
			value = args.get(key)
			if _has_bound_value(value):
				return value

	request_payload = _request_json_payload()
	value = request_payload.get(key)
	if _has_bound_value(value):
		return value

	args = _parse_request_payload(request_payload.get("args"))
	if isinstance(args, dict):
		value = args.get(key)
		if _has_bound_value(value):
			return value

	return current_value


@frappe.whitelist()
def upload_applicant_document(
	student_applicant: str | None = None,
	filename_original: str | None = None,
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
	student_applicant = _request_value("student_applicant", student_applicant)
	filename_original = _request_value("filename_original", filename_original)
	document_type = _request_value("document_type", document_type)
	applicant_document = _request_value("applicant_document", applicant_document)
	applicant_document_item = _request_value("applicant_document_item", applicant_document_item)
	item_key = _request_value("item_key", item_key)
	item_label = _request_value("item_label", item_label)
	slot = _request_value("slot", slot)
	mime_type_hint = _request_value("mime_type_hint", mime_type_hint)
	expected_size_bytes = _request_value("expected_size_bytes", expected_size_bytes)
	idempotency_key = _request_value("idempotency_key", idempotency_key)
	upload_source = _request_value("upload_source", upload_source)
	is_private = _request_value("is_private", is_private)
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
	student_applicant: str | None = None,
	filename_original: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant profile image uploads."""
	student_applicant = _request_value("student_applicant", student_applicant)
	filename_original = _request_value("filename_original", filename_original)
	mime_type_hint = _request_value("mime_type_hint", mime_type_hint)
	expected_size_bytes = _request_value("expected_size_bytes", expected_size_bytes)
	idempotency_key = _request_value("idempotency_key", idempotency_key)
	upload_source = _request_value("upload_source", upload_source)
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
	student_applicant: str | None = None,
	guardian_row_name: str | None = None,
	filename_original: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant guardian image uploads."""
	student_applicant = _request_value("student_applicant", student_applicant)
	guardian_row_name = _request_value("guardian_row_name", guardian_row_name)
	filename_original = _request_value("filename_original", filename_original)
	mime_type_hint = _request_value("mime_type_hint", mime_type_hint)
	expected_size_bytes = _request_value("expected_size_bytes", expected_size_bytes)
	idempotency_key = _request_value("idempotency_key", idempotency_key)
	upload_source = _request_value("upload_source", upload_source)
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
	student_applicant: str | None = None,
	applicant_health_profile: str | None = None,
	vaccine_name: str | None = None,
	date: str | None = None,
	filename_original: str | None = None,
	row_index: int | str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for applicant health vaccination proof uploads."""
	student_applicant = _request_value("student_applicant", student_applicant)
	applicant_health_profile = _request_value("applicant_health_profile", applicant_health_profile)
	vaccine_name = _request_value("vaccine_name", vaccine_name)
	date = _request_value("date", date)
	filename_original = _request_value("filename_original", filename_original)
	row_index = _request_value("row_index", row_index)
	mime_type_hint = _request_value("mime_type_hint", mime_type_hint)
	expected_size_bytes = _request_value("expected_size_bytes", expected_size_bytes)
	idempotency_key = _request_value("idempotency_key", idempotency_key)
	upload_source = _request_value("upload_source", upload_source)
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
