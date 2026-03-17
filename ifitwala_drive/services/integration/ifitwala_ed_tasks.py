# ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_tasks.py

from __future__ import annotations

from typing import Any, Dict

import frappe
from frappe import _

from ifitwala_drive.services.uploads.sessions import create_upload_session_service


def _get_task_submission_doc(task_submission: str):
	if not frappe.db.exists("Task Submission", task_submission):
		frappe.throw(_("Task Submission does not exist: {0}").format(task_submission))

	return frappe.get_doc("Task Submission", task_submission)


def _get_organization_from_school(school: str | None) -> str:
	if not school:
		frappe.throw(_("Task Submission is missing school."))

	organization = frappe.db.get_value("School", school, "organization")
	if not organization:
		frappe.throw(_("Task Submission school is missing organization."))

	return organization


def get_task_submission_context_override(owner_name: str | None) -> Dict[str, Any] | None:
	if not owner_name or not frappe.db.exists("Task Submission", owner_name):
		return None

	task_submission = frappe.get_doc("Task Submission", owner_name)
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


def upload_task_submission_artifact_service(payload: Dict[str, Any]) -> Dict[str, Any]:
	task_submission = payload.get("task_submission")
	student = payload.get("student")
	filename_original = payload.get("filename_original")
	mime_type_hint = payload.get("mime_type_hint")
	expected_size_bytes = payload.get("expected_size_bytes")

	if not task_submission:
		frappe.throw(_("Missing required field: task_submission"))
	if not student:
		frappe.throw(_("Missing required field: student"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))

	if payload.get("slot") not in (None, "submission"):
		frappe.throw(_("Task submission upload currently only supports slot 'submission'."))

	task_submission_doc = _get_task_submission_doc(task_submission)
	submission_student = getattr(task_submission_doc, "student", None)
	school = getattr(task_submission_doc, "school", None)

	if not submission_student:
		frappe.throw(_("Task Submission is missing student."))

	if submission_student != student:
		frappe.throw(_("Student does not match the authoritative Task Submission owner context."))

	organization = _get_organization_from_school(school)

	return create_upload_session_service(
		{
			"owner_doctype": "Task Submission",
			"owner_name": task_submission,
			"attached_doctype": "Task Submission",
			"attached_name": task_submission,
			"organization": organization,
			"school": school,
			"primary_subject_type": "Student",
			"primary_subject_id": student,
			"data_class": "assessment",
			"purpose": "assessment_submission",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": "submission",
			"filename_original": filename_original,
			"mime_type_hint": mime_type_hint,
			"expected_size_bytes": expected_size_bytes,
			"is_private": 1,
			"upload_source": payload.get("upload_source") or "SPA",
			"secondary_subjects": payload.get("secondary_subjects") or [],
		}
	)
