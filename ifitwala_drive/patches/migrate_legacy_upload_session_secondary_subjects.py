from __future__ import annotations

import frappe

_FIELDS = [
	"parent",
	"parentfield",
	"parenttype",
	"idx",
	"subject_type",
	"subject_id",
	"role",
]


def _row_key(row: dict) -> tuple:
	return (
		row.get("parent"),
		row.get("parentfield") or "secondary_subjects",
		row.get("parenttype") or "Drive Upload Session",
		row.get("subject_type"),
		row.get("subject_id"),
		row.get("role") or "referenced",
	)


def execute():
	if not frappe.db.table_exists("File Classification Subject"):
		return
	if not frappe.db.table_exists("Drive Upload Session Subject"):
		return

	legacy_rows = frappe.get_all(
		"File Classification Subject",
		filters={"parenttype": "Drive Upload Session"},
		fields=_FIELDS,
		limit=100000,
	)
	if not legacy_rows:
		return

	existing_rows = frappe.get_all(
		"Drive Upload Session Subject",
		fields=_FIELDS,
		limit=100000,
	)
	existing_keys = {_row_key(row) for row in existing_rows}

	for row in legacy_rows:
		if _row_key(row) in existing_keys:
			continue

		frappe.get_doc(
			{
				"doctype": "Drive Upload Session Subject",
				"parent": row.get("parent"),
				"parentfield": row.get("parentfield") or "secondary_subjects",
				"parenttype": row.get("parenttype") or "Drive Upload Session",
				"idx": row.get("idx") or 0,
				"subject_type": row.get("subject_type"),
				"subject_id": row.get("subject_id"),
				"role": row.get("role") or "referenced",
			}
		).insert(ignore_permissions=True)
