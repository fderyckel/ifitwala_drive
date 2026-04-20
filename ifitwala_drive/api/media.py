from __future__ import annotations

import frappe

from ifitwala_drive.api._payloads import compact_payload
from ifitwala_drive.services.integration.ifitwala_ed_media import (
	issue_employee_image_download_grant_service,
	issue_employee_image_preview_grant_service,
	issue_guardian_image_download_grant_service,
	issue_guardian_image_preview_grant_service,
	issue_student_image_download_grant_service,
	issue_student_image_preview_grant_service,
	upload_employee_image_service,
	upload_guardian_image_service,
	upload_organization_logo_service,
	upload_organization_media_asset_service,
	upload_school_gallery_image_service,
	upload_school_logo_service,
	upload_student_image_service,
)


@frappe.whitelist()
def upload_employee_image(
	employee: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_employee_image_service(
		compact_payload(
			employee=employee,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def issue_employee_image_download_grant(
	employee: str,
	file_id: str,
) -> dict[str, object]:
	return issue_employee_image_download_grant_service(
		compact_payload(
			employee=employee,
			file_id=file_id,
		)
	)


@frappe.whitelist()
def issue_employee_image_preview_grant(
	employee: str,
	file_id: str,
	derivative_role: str | None = None,
) -> dict[str, object]:
	return issue_employee_image_preview_grant_service(
		compact_payload(
			employee=employee,
			file_id=file_id,
			derivative_role=derivative_role,
		)
	)


@frappe.whitelist()
def issue_guardian_image_download_grant(
	guardian: str,
	file_id: str,
) -> dict[str, object]:
	return issue_guardian_image_download_grant_service(
		compact_payload(
			guardian=guardian,
			file_id=file_id,
		)
	)


@frappe.whitelist()
def issue_guardian_image_preview_grant(
	guardian: str,
	file_id: str,
	derivative_role: str | None = None,
) -> dict[str, object]:
	return issue_guardian_image_preview_grant_service(
		compact_payload(
			guardian=guardian,
			file_id=file_id,
			derivative_role=derivative_role,
		)
	)


@frappe.whitelist()
def issue_student_image_download_grant(
	student: str,
	file_id: str,
) -> dict[str, object]:
	return issue_student_image_download_grant_service(
		compact_payload(
			student=student,
			file_id=file_id,
		)
	)


@frappe.whitelist()
def issue_student_image_preview_grant(
	student: str,
	file_id: str,
	derivative_role: str | None = None,
) -> dict[str, object]:
	return issue_student_image_preview_grant_service(
		compact_payload(
			student=student,
			file_id=file_id,
			derivative_role=derivative_role,
		)
	)


@frappe.whitelist()
def upload_guardian_image(
	guardian: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_guardian_image_service(
		compact_payload(
			guardian=guardian,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_student_image(
	student: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_student_image_service(
		compact_payload(
			student=student,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_organization_logo(
	organization: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_organization_logo_service(
		compact_payload(
			organization=organization,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_school_logo(
	school: str,
	filename_original: str,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_school_logo_service(
		compact_payload(
			school=school,
			filename_original=filename_original,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_school_gallery_image(
	school: str,
	filename_original: str,
	row_name: str | None = None,
	caption: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_school_gallery_image_service(
		compact_payload(
			school=school,
			filename_original=filename_original,
			row_name=row_name,
			caption=caption,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


@frappe.whitelist()
def upload_organization_media_asset(
	filename_original: str,
	organization: str | None = None,
	school: str | None = None,
	scope: str = "organization",
	media_key: str | None = None,
	mime_type_hint: str | None = None,
	expected_size_bytes: int | str | None = None,
	idempotency_key: str | None = None,
	upload_source: str | None = None,
) -> dict[str, object]:
	return upload_organization_media_asset_service(
		compact_payload(
			filename_original=filename_original,
			organization=organization,
			school=school,
			scope=scope,
			media_key=media_key,
			mime_type_hint=mime_type_hint,
			expected_size_bytes=expected_size_bytes,
			idempotency_key=idempotency_key,
			upload_source=upload_source,
		)
	)


__all__ = (
	"issue_employee_image_download_grant",
	"issue_employee_image_preview_grant",
	"issue_guardian_image_download_grant",
	"issue_guardian_image_preview_grant",
	"issue_student_image_download_grant",
	"issue_student_image_preview_grant",
	"upload_employee_image",
	"upload_guardian_image",
	"upload_organization_logo",
	"upload_organization_media_asset",
	"upload_school_gallery_image",
	"upload_school_logo",
	"upload_student_image",
)
