from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.files.versions import replace_drive_file_version_service


@frappe.whitelist()
def replace_drive_file_version(
	drive_file_id: str,
	new_file_artifact: dict[str, Any],
	reason: str | None = None,
) -> dict[str, Any]:
	return replace_drive_file_version_service(
		{
			"drive_file_id": drive_file_id,
			"new_file_artifact": new_file_artifact,
			"reason": reason,
		}
	)
