# ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_tasks.py

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.folders.resolution import resolve_task_submission_folder

_TASK_SUBMISSION_DATA_CLASS = "assessment"
_TASK_SUBMISSION_PURPOSE = "assessment_submission"
_TASK_SUBMISSION_RETENTION_POLICY = "until_school_exit_plus_6m"
_TASK_SUBMISSION_SLOT = "submission"


def _get_task_submission_doc(task_submission: str, *, permission_type: str | None = None):
	if not frappe.db.exists("Task Submission", task_submission):
		frappe.throw(_("Task Submission does not exist: {0}").format(task_submission))

	doc = frappe.get_doc("Task Submission", task_submission)
	if permission_type:
		doc.check_permission(permission_type)
	return doc


def _get_organization_from_school(school: str | None) -> str:
	if not school:
		frappe.throw(_("Task Submission is missing school."))

	organization = frappe.db.get_value("School", school, "organization")
	if not organization:
		frappe.throw(_("Task Submission school is missing organization."))

	return organization


def build_task_submission_upload_contract(task_submission_doc) -> dict[str, Any]:
	student = getattr(task_submission_doc, "student", None)
	school = getattr(task_submission_doc, "school", None)
	if not student:
		frappe.throw(_("Task Submission is missing student."))
	if not school:
		frappe.throw(_("Task Submission is missing school."))

	return {
		"owner_doctype": "Task Submission",
		"owner_name": task_submission_doc.name,
		"attached_doctype": "Task Submission",
		"attached_name": task_submission_doc.name,
		"organization": _get_organization_from_school(school),
		"school": school,
		"primary_subject_type": "Student",
		"primary_subject_id": student,
		"data_class": _TASK_SUBMISSION_DATA_CLASS,
		"purpose": _TASK_SUBMISSION_PURPOSE,
		"retention_policy": _TASK_SUBMISSION_RETENTION_POLICY,
		"slot": _TASK_SUBMISSION_SLOT,
	}


def assert_task_submission_upload_access(task_submission: str, *, permission_type: str = "write"):
	return _get_task_submission_doc(task_submission, permission_type=permission_type)


def reconcile_task_submission_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
	if payload.get("owner_doctype") != "Task Submission":
		return payload

	task_submission_name = payload.get("owner_name")
	if not task_submission_name:
		frappe.throw(_("Missing required field: owner_name"))

	task_submission_doc = assert_task_submission_upload_access(task_submission_name, permission_type="write")
	authoritative = build_task_submission_upload_contract(task_submission_doc)

	for fieldname, authoritative_value in authoritative.items():
		provided = payload.get(fieldname)
		if provided not in (None, "", authoritative_value):
			frappe.throw(
				_(
					"Task Submission upload field '{0}' does not match the authoritative owner context."
				).format(fieldname)
			)

	return {
		**payload,
		**authoritative,
	}


def validate_task_submission_finalize_context(upload_session_doc) -> dict[str, Any] | None:
	if getattr(upload_session_doc, "owner_doctype", None) != "Task Submission":
		return None

	task_submission_doc = assert_task_submission_upload_access(
		upload_session_doc.owner_name,
		permission_type="write",
	)
	authoritative = build_task_submission_upload_contract(task_submission_doc)

	field_map = {
		"owner_doctype": "owner_doctype",
		"owner_name": "owner_name",
		"attached_doctype": "attached_doctype",
		"attached_name": "attached_name",
		"organization": "organization",
		"school": "school",
		"intended_primary_subject_type": "primary_subject_type",
		"intended_primary_subject_id": "primary_subject_id",
		"intended_data_class": "data_class",
		"intended_purpose": "purpose",
		"intended_retention_policy": "retention_policy",
		"intended_slot": "slot",
	}

	for session_field, authoritative_field in field_map.items():
		if getattr(upload_session_doc, session_field, None) != authoritative[authoritative_field]:
			frappe.throw(
				_(
					"Upload session no longer matches the authoritative Task Submission context for field '{0}'."
				).format(session_field)
			)

	return authoritative


def get_task_submission_context_override(owner_name: str | None) -> dict[str, Any] | None:
	if not owner_name or not frappe.db.exists("Task Submission", owner_name):
		return None

	task_submission = _get_task_submission_doc(owner_name)
	student = getattr(task_submission, "student", None)
	task_name = getattr(task_submission, "task", None) or task_submission.name

	if not student:
		return None

	try:
		from ifitwala_ed.utilities import file_management
	except ImportError:
		return None

	return file_management.build_task_submission_context(
		student=student,
		task_name=task_name,
		settings=file_management.get_settings(),
	)


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

	if payload.get("slot") not in (None, _TASK_SUBMISSION_SLOT):
		frappe.throw(_("Task submission upload currently only supports slot 'submission'."))

	task_submission_doc = assert_task_submission_upload_access(task_submission, permission_type="write")
	authoritative = build_task_submission_upload_contract(task_submission_doc)
	student = payload.get("student")
	if student not in (None, "", authoritative["primary_subject_id"]):
		frappe.throw(_("Student does not match the authoritative Task Submission owner context."))

	return create_upload_session_service(
		{
			**authoritative,
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
	)
