from __future__ import annotations

import frappe
from frappe import _


def load_ed_drive_module(module_name: str):
	try:
		if module_name == "ifitwala_ed.integrations.drive.bridge":
			from ifitwala_ed.integrations.drive import bridge as ed_bridge_module

			return ed_bridge_module
		if module_name == "ifitwala_ed.integrations.drive.admissions":
			from ifitwala_ed.integrations.drive import admissions as ed_admissions_module

			return ed_admissions_module
		if module_name == "ifitwala_ed.integrations.drive.media":
			from ifitwala_ed.integrations.drive import media as ed_media_module

			return ed_media_module
		if module_name == "ifitwala_ed.integrations.drive.materials":
			from ifitwala_ed.integrations.drive import materials as ed_materials_module

			return ed_materials_module
		if module_name == "ifitwala_ed.integrations.drive.org_communications":
			from ifitwala_ed.integrations.drive import org_communications as ed_org_communications_module

			return ed_org_communications_module
		if module_name == "ifitwala_ed.integrations.drive.tasks":
			from ifitwala_ed.integrations.drive import tasks as ed_tasks_module

			return ed_tasks_module
	except ImportError as exc:
		frappe.throw(
			_(
				"Ifitwala_Ed Drive bridge module '{0}' is unavailable. Ensure the Ed app is installed with the matching bridge implementation: {1}"
			).format(module_name, exc)
		)

	frappe.throw(_("Unsupported Ifitwala_Ed Drive bridge module: {0}").format(module_name))
