from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.files.access import (
	issue_download_grant_service,
	issue_preview_grant_service,
)
from ifitwala_drive.services.files.legacy_access import resolve_public_file_redirect


@frappe.whitelist()
def issue_download_grant(
	drive_file_id: str | None = None,
	canonical_ref: str | None = None,
) -> dict[str, Any]:
	return issue_download_grant_service(
		compact_payload(drive_file_id=drive_file_id, canonical_ref=canonical_ref)
	)


@frappe.whitelist()
def issue_preview_grant(
	drive_file_id: str | None = None,
	canonical_ref: str | None = None,
	derivative_role: str | None = None,
) -> dict[str, Any]:
	return issue_preview_grant_service(
		compact_payload(
			drive_file_id=drive_file_id,
			canonical_ref=canonical_ref,
			derivative_role=derivative_role,
		)
	)


@frappe.whitelist(allow_guest=True)
def redirect_public_file(file_id: str | None = None, file_url: str | None = None):
	redirect = resolve_public_file_redirect(file_id=file_id, file_url=file_url)
	response = getattr(frappe.local, "response", None)
	if response is None:
		response = {}
		frappe.local.response = response
	response["type"] = "redirect"
	response["location"] = redirect["url"]
	response["http_status_code"] = 302
	return None
