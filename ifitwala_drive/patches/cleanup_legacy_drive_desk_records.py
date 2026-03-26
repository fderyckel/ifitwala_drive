import frappe


LEGACY_DESK_RECORDS = (
	("Desktop Icon", "Drive"),
	("Workspace Sidebar", "Drive"),
)


def execute():
	for doctype, name in LEGACY_DESK_RECORDS:
		if not frappe.db.exists(doctype, name):
			continue

		doc = frappe.get_doc(doctype, name)
		if getattr(doc, "app", None) != "ifitwala_drive":
			continue

		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
