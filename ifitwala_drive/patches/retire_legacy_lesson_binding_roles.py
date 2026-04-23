from __future__ import annotations

import frappe

_RETIRED_ROLES = ("lesson_resource", "lesson_activity_resource")
_REPLACEMENT_ROLE = "supporting_material"
_PRESERVED_STATUSES = {"inactive", "superseded"}


def execute():
	if not frappe.db.table_exists("Drive Binding"):
		return

	legacy_rows = frappe.get_all(
		"Drive Binding",
		filters={"binding_role": ["in", list(_RETIRED_ROLES)]},
		fields=["name", "status"],
		order_by="creation asc, name asc",
		limit=0,
	)
	for row in legacy_rows or []:
		name = str(row.get("name") or "").strip()
		if not name:
			continue

		values = {
			"binding_role": _REPLACEMENT_ROLE,
			"is_primary": 0,
			"primary_key": None,
		}
		status = str(row.get("status") or "").strip()
		if status == "active":
			values["status"] = "superseded"
		elif status not in _PRESERVED_STATUSES:
			values["status"] = "superseded"

		frappe.db.set_value("Drive Binding", name, values, update_modified=False)
