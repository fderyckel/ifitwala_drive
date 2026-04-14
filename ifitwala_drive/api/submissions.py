# ifitwala_drive/ifitwala_drive/api/submissions.py

from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.integration.ifitwala_ed_tasks import (
	upload_task_submission_artifact_service,
)


@frappe.whitelist()
def upload_task_submission_artifact(
	task_submission: str,
	filename_original: str,
	student: str | None = None,
	slot: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
	secondary_subjects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for task submission uploads."""
	return upload_task_submission_artifact_service(
		compact_payload(
			task_submission=task_submission,
			filename_original=filename_original,
			student=student,
			slot=slot,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
			secondary_subjects=secondary_subjects,
		)
	)
