from __future__ import annotations

import importlib

import frappe
from frappe import _


def load_ed_drive_module(module_name: str):
	try:
		if module_name in {
			"ifitwala_ed.integrations.drive.bridge",
			"ifitwala_ed.integrations.drive.admissions",
			"ifitwala_ed.integrations.drive.media",
			"ifitwala_ed.integrations.drive.materials",
			"ifitwala_ed.integrations.drive.org_communications",
			"ifitwala_ed.integrations.drive.tasks",
		}:
			return importlib.import_module(module_name)
	except ImportError as exc:
		frappe.throw(
			_(
				"Ifitwala_Ed Drive bridge module '{0}' is unavailable. Ensure the Ed app is installed with the matching bridge implementation: {1}"
			).format(module_name, exc)
		)

	frappe.throw(_("Unsupported Ifitwala_Ed Drive bridge module: {0}").format(module_name))
