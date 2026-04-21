from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.folders.resolution import (
	resolve_task_resource_folder,
	resolve_task_submission_folder,
)
from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module
from ifitwala_drive.services.integration.ifitwala_ed_bridge import resolve_upload_session_context

_ED_MODULE = "ifitwala_ed.integrations.drive.tasks"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing task delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def build_task_resource_upload_contract(task_doc, *, row_name: str | None = None) -> dict[str, Any]:
	return _call_delegate("build_task_resource_upload_contract", task_doc, row_name=row_name)


def build_task_submission_upload_contract(task_submission_doc) -> dict[str, Any]:
	return _call_delegate("build_task_submission_upload_contract", task_submission_doc)


def assert_task_submission_upload_access(task_submission: str, *, permission_type: str = "write"):
	return _call_delegate(
		"assert_task_submission_upload_access",
		task_submission,
		permission_type=permission_type,
	)


def assert_task_resource_upload_access(task: str, *, permission_type: str = "write"):
	return _call_delegate("assert_task_resource_upload_access", task, permission_type=permission_type)


def validate_task_resource_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_task_resource_finalize_context", upload_session_doc)


def get_task_resource_context_override(owner_name: str | None, slot: str | None) -> dict[str, Any] | None:
	return _call_delegate("get_task_resource_context_override", owner_name, slot)


def run_task_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_task_post_finalize", upload_session_doc, created_file)


def reconcile_task_submission_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("reconcile_task_submission_session_payload", payload)


def validate_task_submission_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	return _call_delegate("validate_task_submission_finalize_context", upload_session_doc)


def get_task_submission_context_override(owner_name: str | None) -> dict[str, Any] | None:
	return _call_delegate("get_task_submission_context_override", owner_name)


def upload_task_submission_artifact_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	task_submission = payload.get("task_submission")
	filename_original = payload.get("filename_original")
	mime_type_hint = payload.get("mime_type_hint")
	expected_size_bytes = payload.get("expected_size_bytes")

	if not task_submission:
		frappe.throw(_("Missing required field: task_submission"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "task.submission"
	workflow_payload = {
		"task_submission": task_submission,
		"student": payload.get("student"),
		"slot": payload.get("slot"),
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	task_submission_doc = assert_task_submission_upload_access(task_submission, permission_type="write")

	session_payload = {
		**authoritative,
		"workflow_payload": workflow_payload,
		"folder": resolve_task_submission_folder(
			student=authoritative["primary_subject_id"],
			task_name=getattr(task_submission_doc, "task", None) or task_submission_doc.name,
			organization=authoritative["organization"],
			school=authoritative["school"],
		),
		"filename_original": filename_original,
		"mime_type_hint": mime_type_hint,
		"expected_size_bytes": expected_size_bytes,
		"is_private": 1,
		"upload_source": payload.get("upload_source") or "SPA",
		"secondary_subjects": payload.get("secondary_subjects") or [],
	}
	idempotency_key = payload.get("idempotency_key")
	if idempotency_key:
		session_payload["idempotency_key"] = idempotency_key

	return create_upload_session_service(session_payload)


def upload_task_resource_service(payload: dict[str, Any]) -> dict[str, Any]:
	from ifitwala_drive.services.uploads.sessions import create_upload_session_service

	task = payload.get("task")
	filename_original = payload.get("filename_original")
	provided_row_name = payload.get("row_name")

	if not task:
		frappe.throw(_("Missing required field: task"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	workflow_id = "task.resource"
	workflow_payload = {
		"task": task,
		"row_name": provided_row_name,
		"slot": payload.get("slot"),
	}
	authoritative = resolve_upload_session_context(workflow_id, workflow_payload)
	task_doc = assert_task_resource_upload_access(task, permission_type="write")

	session_payload = {
		**{key: value for key, value in authoritative.items() if key not in {"row_name", "course"}},
		"workflow_payload": workflow_payload,
		"workflow_result": {
			"row_name": authoritative["row_name"],
			"slot": authoritative["slot"],
		},
		"folder": resolve_task_resource_folder(
			task=task_doc.name,
			course=authoritative["course"],
			organization=authoritative["organization"],
			school=authoritative["school"],
		),
		"filename_original": filename_original,
		"mime_type_hint": payload.get("mime_type_hint"),
		"expected_size_bytes": payload.get("expected_size_bytes"),
		"is_private": 1,
		"upload_source": payload.get("upload_source") or "Desk",
	}
	idempotency_key = payload.get("idempotency_key")
	if idempotency_key:
		session_payload["idempotency_key"] = idempotency_key

	return create_upload_session_service(session_payload)
