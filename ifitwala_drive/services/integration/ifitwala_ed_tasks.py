# ifitwala_drive/ifitwala_drive/services/integration/ifitwala_ed_tasks.py

from __future__ import annotations

from typing import Any, Dict

import frappe
from frappe import _

from ifitwala_drive.services.uploads.sessions import create_upload_session_service


def upload_task_submission_artifact_service(payload: Dict[str, Any]) -> Dict[str, Any]:
	task_submission = payload.get("task_submission")
	student = payload.get("student")
	filename_original = payload.get("filename_original")
	mime_type_hint = payload.get("mime_type_hint")
	expected_size_bytes = payload.get("expected_size_bytes")
	slot = payload.get("slot") or "submission"

	if not task_submission:
		frappe.throw(_("Missing required field: task_submission"))
	if not student:
		frappe.throw(_("Missing required field: student"))
	if not filename_original:
		frappe.throw(_("Missing required field: filename_original"))
	if slot != "submission":
		frappe.throw(_("Task submission upload currently only supports slot 'submission'."))

	if not frappe.db.exists("Task Submission", task_submission):
		frappe.throw(_("Task Submission does not exist: {0}").format(task_submission))

	# Replace these lookups with real authoritative source fields from your schema.
	org, school = frappe.db.get_value(
		"Task Submission",
		task_submission,
		["organization", "school"],
	)

	if not org:
		frappe.throw(_("Task Submission is missing organization."))
	if not school:
		frappe.throw(_("Task Submission is missing school."))

	return create_upload_session_service(
		{
			"owner_doctype": "Task Submission",
			"owner_name": task_submission,
			"attached_doctype": "Task Submission",
			"attached_name": task_submission,
			"organization": org,
			"school": school,
			"primary_subject_type": "student",
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
