from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.folders.resolution import (
	resolve_applicant_document_folder,
	resolve_applicant_guardian_image_folder,
	resolve_applicant_health_folder,
	resolve_applicant_profile_image_folder,
)
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module
from ifitwala_drive.services.integration.ifitwala_ed_bridge import resolve_upload_session_context

_ED_MODULE = "ifitwala_ed.integrations.drive.admissions"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing admissions delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def _get_applicant_document_context(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("get_applicant_document_context", payload)


def _get_applicant_health_vaccination_context(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("get_applicant_health_vaccination_context", payload)


def _get_applicant_profile_image_context(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("get_applicant_profile_image_context", payload)


def _get_applicant_guardian_image_context(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("get_applicant_guardian_image_context", payload)


def upload_applicant_document_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "admissions.applicant_document"
	workflow_payload = {
		"student_applicant": payload.get("student_applicant"),
		"document_type": payload.get("document_type"),
		"applicant_document": payload.get("applicant_document"),
		"applicant_document_item": payload.get("applicant_document_item"),
		"item_key": payload.get("item_key"),
		"item_label": payload.get("item_label"),
		"filename_original": filename_original,
	}
	context = resolve_upload_session_context(workflow_id, workflow_payload)
	response = create_upload_session_service(
		{
			"owner_doctype": context["owner_doctype"],
			"owner_name": context["owner_name"],
			"attached_doctype": context["attached_doctype"],
			"attached_name": context["attached_name"],
			"organization": context["organization"],
			"school": context["school"],
			"primary_subject_type": context["primary_subject_type"],
			"primary_subject_id": context["primary_subject_id"],
			"data_class": context["data_class"],
			"purpose": context["purpose"],
			"retention_policy": context["retention_policy"],
			"slot": context["slot"],
			"workflow_id": context["workflow_id"],
			"contract_version": context["contract_version"],
			"workflow_payload": workflow_payload,
			"folder": resolve_applicant_document_folder(
				student_applicant=context["owner_name"],
				organization=context["organization"],
				school=context["school"],
				slot=context["slot"],
				document_type_code=context.get("document_type_code"),
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	response.update(
		{
			"applicant_document": context["applicant_document"],
			"applicant_document_item": context["applicant_document_item"],
			"item_key": context["item_key"],
			"item_label": context["item_label"],
		}
	)
	return response


def upload_applicant_profile_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "admissions.applicant_profile_image"
	workflow_payload = {
		"student_applicant": payload.get("student_applicant"),
	}
	context = resolve_upload_session_context(workflow_id, workflow_payload)
	response = create_upload_session_service(
		{
			**context,
			"workflow_payload": workflow_payload,
			"folder": resolve_applicant_profile_image_folder(
				student_applicant=context["owner_name"],
				organization=context["organization"],
				school=context["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	response.update({"student_applicant": context["owner_name"], "slot": context["slot"]})
	return response


def upload_applicant_guardian_image_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "admissions.applicant_guardian_image"
	workflow_payload = {
		"student_applicant": payload.get("student_applicant"),
		"guardian_row_name": payload.get("guardian_row_name"),
	}
	context = resolve_upload_session_context(workflow_id, workflow_payload)
	response = create_upload_session_service(
		{
			**context,
			"workflow_payload": workflow_payload,
			"folder": resolve_applicant_guardian_image_folder(
				student_applicant=context["owner_name"],
				organization=context["organization"],
				school=context["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	response.update(
		{
			"student_applicant": context["owner_name"],
			"guardian_row_name": context["attached_name"],
			"slot": context["slot"],
		}
	)
	return response


def upload_applicant_health_vaccination_proof_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	filename_original = payload.get("filename_original")
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "admissions.applicant_health_vaccination"
	workflow_payload = {
		"student_applicant": payload.get("student_applicant"),
		"applicant_health_profile": payload.get("applicant_health_profile"),
		"vaccine_name": payload.get("vaccine_name"),
		"date": payload.get("date"),
		"row_index": payload.get("row_index"),
	}
	context = resolve_upload_session_context(workflow_id, workflow_payload)
	response = create_upload_session_service(
		{
			**context,
			"workflow_payload": workflow_payload,
			"folder": resolve_applicant_health_folder(
				student_applicant=context["owner_name"],
				organization=context["organization"],
				school=context["school"],
			),
			"filename_original": filename_original,
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
		}
	)
	response.update(
		{
			"student_applicant": context["owner_name"],
			"applicant_health_profile": context["attached_name"],
			"slot": context["slot"],
		}
	)
	return response


def validate_applicant_document_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_applicant_document_finalize_context", upload_session_doc)


def validate_applicant_profile_image_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_applicant_profile_image_finalize_context", upload_session_doc)


def validate_applicant_guardian_image_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_applicant_guardian_image_finalize_context", upload_session_doc)


def validate_applicant_health_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_applicant_health_finalize_context", upload_session_doc)


def get_admissions_attached_field_override(upload_session_doc) -> str | None:
	return _call_delegate("get_admissions_attached_field_override", upload_session_doc)


def run_admissions_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_admissions_post_finalize", upload_session_doc, created_file)
