# ifitwala_drive/ifitwala_drive/api/submissions.py

from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.integration.ifitwala_ed_tasks import (
	upload_task_submission_artifact_service,
)


@frappe.whitelist()
def upload_task_submission_artifact(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for task submission uploads."""
	return upload_task_submission_artifact_service(kwargs)
