from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.integration.ifitwala_ed_tasks import upload_task_resource_service


@frappe.whitelist()
def upload_task_resource(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for governed Task resource uploads."""
	return upload_task_resource_service(kwargs)
