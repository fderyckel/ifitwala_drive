// ifitwala_drive/ifitwala_drive/doctype/drive_binding/drive_binding.js

frappe.ui.form.on("Drive Binding", {
	refresh(frm) {
		if (frm.doc.status !== "active") {
			frm.dashboard.set_headline_alert(__("This binding is not active."), "orange")
		}

		if (frm.doc.is_primary) {
			frm.dashboard.set_headline_alert(
				__("This is the primary reference for its current binding context."),
				"green"
			)
		}
	}
})
