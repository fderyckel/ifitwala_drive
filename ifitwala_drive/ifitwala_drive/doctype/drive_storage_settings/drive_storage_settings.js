frappe.ui.form.on("Drive Storage Settings", {
	refresh(frm) {
		if (frm.is_dirty()) {
			return;
		}

		frm.add_custom_button(__("Test Connection"), async () => {
			const response = await frappe.call({
				method: "ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings.test_storage_connection",
			});
			const message = Object.entries(response.message || {})
				.map(([key, value]) => `${key}: ${value}`)
				.join("<br>");
			frappe.msgprint({
				title: __("Storage Connection"),
				message,
				indicator: "green",
			});
		});
	},
});
