from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.integration.ifitwala_ed_org_communications import (
	upload_org_communication_attachment_service,
)


@frappe.whitelist()
def upload_org_communication_attachment(**kwargs: Any) -> dict[str, Any]:
	return upload_org_communication_attachment_service(kwargs)
