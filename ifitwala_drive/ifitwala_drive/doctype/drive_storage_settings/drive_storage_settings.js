frappe.ui.form.on("Drive Storage Settings", {
	refresh(frm) {
		if (frm.is_dirty()) {
			return;
		}

		frm.add_custom_button(__("Dry Run Attachment Offload"), async () => {
			const response = await frappe.call({
				method: "ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings.dry_run_attachment_offload",
			});
			const summary = response.message?.summary || {};
			const message = Object.entries(summary)
				.map(([key, value]) => `${key}: ${value}`)
				.join("<br>");
			frappe.msgprint({
				title: __("Attachment Offload Dry Run"),
				message,
				indicator: "blue",
			});
			frm.reload_doc();
		});

		frm.add_custom_button(__("Queue Offload Jobs"), async () => {
			const response = await frappe.call({
				method: "ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings.enqueue_attachment_offload_jobs",
			});
			const summary = response.message?.summary || {};
			const message = Object.entries(summary)
				.map(([key, value]) => `${key}: ${value}`)
				.join("<br>");
			frappe.msgprint({
				title: __("Attachment Offload"),
				message,
				indicator: "orange",
			});
			frm.reload_doc();
		});

		frm.add_custom_button(__("Dry Run Local Prune"), async () => {
			const response = await frappe.call({
				method: "ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings.dry_run_local_prune",
			});
			const summary = response.message?.summary || {};
			const message = Object.entries(summary)
				.map(([key, value]) => `${key}: ${value}`)
				.join("<br>");
			frappe.msgprint({
				title: __("Local Prune Dry Run"),
				message,
				indicator: "blue",
			});
			frm.reload_doc();
		});

		frm.add_custom_button(__("Queue Local Prune Jobs"), async () => {
			const response = await frappe.call({
				method: "ifitwala_drive.ifitwala_drive.doctype.drive_storage_settings.drive_storage_settings.enqueue_local_prune_jobs",
			});
			const summary = response.message?.summary || {};
			const message = Object.entries(summary)
				.map(([key, value]) => `${key}: ${value}`)
				.join("<br>");
			frappe.msgprint({
				title: __("Local Prune"),
				message,
				indicator: "orange",
			});
			frm.reload_doc();
		});

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
