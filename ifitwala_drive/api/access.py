from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.files.access import (
	issue_download_grant_service,
	issue_preview_grant_service,
)


@frappe.whitelist()
def issue_download_grant(**kwargs: Any) -> dict[str, Any]:
	return issue_download_grant_service(kwargs)


@frappe.whitelist()
def issue_preview_grant(**kwargs: Any) -> dict[str, Any]:
	return issue_preview_grant_service(kwargs)
