from __future__ import annotations

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.audit.erasure import (
	create_drive_erasure_request_service,
	execute_drive_erasure_request_service,
)


@frappe.whitelist()
def create_drive_erasure_request(
	data_subject_type: str,
	data_subject_id: str,
	scope: str | None = None,
	request_reason: str | None = None,
	slot_filter: str | None = None,
) -> dict[str, object]:
	return create_drive_erasure_request_service(
		compact_payload(
			data_subject_type=data_subject_type,
			data_subject_id=data_subject_id,
			scope=scope,
			request_reason=request_reason,
			slot_filter=slot_filter,
		)
	)


@frappe.whitelist()
def execute_drive_erasure_request(
	erasure_request_id: str,
	metadata_filters: dict[str, object] | str | None = None,
	decision_items: list[dict[str, object]] | str | None = None,
) -> dict[str, object]:
	return execute_drive_erasure_request_service(
		compact_payload(
			erasure_request_id=erasure_request_id,
			metadata_filters=metadata_filters,
			decision_items=decision_items,
		)
	)
