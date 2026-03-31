from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.integration.ifitwala_ed_materials import (
	upload_supporting_material_service,
)


@frappe.whitelist()
def upload_supporting_material(**kwargs: Any) -> dict[str, Any]:
	"""Workflow-aware wrapper for Supporting Material uploads."""
	return upload_supporting_material_service(kwargs)
