from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.integration.ifitwala_ed_tasks import upload_task_resource_service


@frappe.whitelist()
def upload_task_resource(
	task: str,
	filename_original: str,
	row_name: str | None = None,
	slot: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for governed Task resource uploads."""
	return upload_task_resource_service(
		compact_payload(
			task=task,
			filename_original=filename_original,
			row_name=row_name,
			slot=slot,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			upload_source=upload_source,
		)
	)
