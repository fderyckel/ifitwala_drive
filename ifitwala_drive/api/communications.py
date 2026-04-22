from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.integration.ifitwala_ed_org_communications import (
	issue_org_communication_attachment_download_grant_service,
	issue_org_communication_attachment_preview_grant_service,
	upload_org_communication_attachment_service,
)


@frappe.whitelist()
def upload_org_communication_attachment(
	org_communication: str,
	filename_original: str,
	row_name: str | None = None,
	slot: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	return upload_org_communication_attachment_service(
		compact_payload(
			org_communication=org_communication,
			filename_original=filename_original,
			row_name=row_name,
			slot=slot,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def issue_org_communication_attachment_download_grant(
	org_communication: str,
	row_name: str,
) -> dict[str, Any]:
	return issue_org_communication_attachment_download_grant_service(
		compact_payload(org_communication=org_communication, row_name=row_name)
	)


@frappe.whitelist()
def issue_org_communication_attachment_preview_grant(
	org_communication: str,
	row_name: str,
	derivative_role: str | None = None,
) -> dict[str, Any]:
	return issue_org_communication_attachment_preview_grant_service(
		compact_payload(
			org_communication=org_communication,
			row_name=row_name,
			derivative_role=derivative_role,
		)
	)
