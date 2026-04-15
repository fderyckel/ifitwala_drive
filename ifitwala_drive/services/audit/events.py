from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import frappe
from frappe.utils import now_datetime


def _json_dumps(payload: dict[str, Any] | None) -> str | None:
	if not payload:
		return None
	return json.dumps(payload, sort_keys=True, default=str)


def record_drive_access_event(
	*,
	drive_file_id: str,
	event_type: str,
	drive_file_version_id: str | None = None,
	metadata: dict[str, Any] | None = None,
	actor: str | None = None,
	request_ip: str | None = None,
	event_on: datetime | None = None,
) -> str | None:
	"""Persist a minimal Drive audit row without blocking the main workflow on audit failures."""
	drive_file_id = str(drive_file_id or "").strip()
	if not drive_file_id:
		return None

	try:
		if not frappe.db.exists("Drive File", drive_file_id):
			return None

		if drive_file_version_id and not frappe.db.exists("Drive File Version", drive_file_version_id):
			drive_file_version_id = None

		doc = frappe.get_doc(
			{
				"doctype": "Drive Access Event",
				"drive_file": drive_file_id,
				"drive_file_version": drive_file_version_id,
				"event_type": event_type,
				"actor": actor or getattr(getattr(frappe, "session", None), "user", None),
				"request_ip": request_ip or getattr(getattr(frappe, "local", None), "request_ip", None),
				"event_on": event_on or now_datetime(),
				"metadata_json": _json_dumps(metadata),
			}
		)
		doc.insert(ignore_permissions=True)
		return getattr(doc, "name", None)
	except Exception:
		return None
