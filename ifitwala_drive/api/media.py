from __future__ import annotations

from typing import Any

import frappe

from ifitwala_drive.services.integration.ifitwala_ed_media import (
	upload_employee_image_service,
	upload_organization_logo_service,
	upload_organization_media_asset_service,
	upload_school_gallery_image_service,
	upload_school_logo_service,
	upload_student_image_service,
)


@frappe.whitelist()
def upload_employee_image(**kwargs: Any) -> dict[str, Any]:
	return upload_employee_image_service(kwargs)


@frappe.whitelist()
def upload_student_image(**kwargs: Any) -> dict[str, Any]:
	return upload_student_image_service(kwargs)


@frappe.whitelist()
def upload_organization_logo(**kwargs: Any) -> dict[str, Any]:
	return upload_organization_logo_service(kwargs)


@frappe.whitelist()
def upload_school_logo(**kwargs: Any) -> dict[str, Any]:
	return upload_school_logo_service(kwargs)


@frappe.whitelist()
def upload_school_gallery_image(**kwargs: Any) -> dict[str, Any]:
	return upload_school_gallery_image_service(kwargs)


@frappe.whitelist()
def upload_organization_media_asset(**kwargs: Any) -> dict[str, Any]:
	return upload_organization_media_asset_service(kwargs)
