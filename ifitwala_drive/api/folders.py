from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.folders.browse import (
	list_context_files_service,
	list_folder_items_service,
)


@frappe.whitelist()
def list_folder_items(**kwargs: Any) -> dict[str, Any]:
	return list_folder_items_service(kwargs)


@frappe.whitelist()
def list_context_files(**kwargs: Any) -> dict[str, Any]:
	return list_context_files_service(kwargs)

