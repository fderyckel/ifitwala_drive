import frappe


DRIVE_DOCTYPES = (
	"Drive Upload Session",
	"Drive File",
	"Drive File Version",
	"Drive Folder",
	"Drive Binding",
	"Drive Processing Job",
)

TARGET_MODULE = "Ifitwala Drive"


def execute():
	for doctype in DRIVE_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue

		current_module = frappe.db.get_value("DocType", doctype, "module")
		if current_module == TARGET_MODULE:
			continue

		frappe.db.set_value(
			"DocType",
			doctype,
			"module",
			TARGET_MODULE,
			update_modified=False,
		)
