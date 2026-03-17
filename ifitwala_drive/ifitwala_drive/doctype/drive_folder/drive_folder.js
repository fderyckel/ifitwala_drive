// ifitwala_drive/ifitwala_drive/doctype/drive_folder/drive_folder.js

frappe.ui.form.on("Drive Folder", {
	refresh(frm) {
		if (frm.doc.path_cache) {
			frm.dashboard.set_headline_alert(
				__("Browse Path: {0}", [frm.doc.path_cache]),
				"blue"
			)
		}

		if (frm.doc.status !== "active") {
			frm.dashboard.set_headline_alert(
				__("This folder is not active."),
				"orange"
			)
		}
	},

	title(frm) {
		if (!frm.doc.slug && frm.doc.title) {
			frm.set_value("slug", slugify_folder_value(frm.doc.title))
		}
	}
})

function slugify_folder_value(value) {
	return (value || "")
		.toLowerCase()
		.trim()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/-{2,}/g, "-")
		.replace(/^-+|-+$/g, "") || "folder"
}
