from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.integration.ifitwala_ed_materials import (
	upload_supporting_material_service,
)


@frappe.whitelist()
def upload_supporting_material(
	material: str,
	filename_original: str,
	slot: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, Any]:
	"""Workflow-aware wrapper for Supporting Material uploads."""
	return upload_supporting_material_service(
		compact_payload(
			material=material,
			filename_original=filename_original,
			slot=slot,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)
