# ifitwala_drive/ifitwala_drive/doctype/drive_file/drive_file.py

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_STATUSES = {"active", "processing", "blocked", "erased", "superseded"}
_ALLOWED_PREVIEW_STATUSES = {"pending", "ready", "failed", "not_applicable"}
_ALLOWED_UPLOAD_SOURCES = {"Desk", "SPA", "API", "Job"}


class DriveFile(Document):
	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_fields()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_required_fields()
		self._validate_status()
		self._validate_preview_status()
		self._validate_upload_source()
		self._validate_links()

	def _set_defaults(self) -> None:
		if not self.status:
			self.status = "active"

		if not self.preview_status:
			self.preview_status = "pending"

		if self.current_version_no is None:
			self.current_version_no = 0

		if self.is_private is None:
			self.is_private = 1

		if not self.display_name and self.file:
			self.display_name = self.file

	def _validate_required_fields(self) -> None:
		required_fields = (
			"file",
			"display_name",
			"attached_doctype",
			"attached_name",
			"owner_doctype",
			"owner_name",
			"organization",
			"primary_subject_type",
			"primary_subject_id",
			"data_class",
			"purpose",
			"retention_policy",
			"slot",
			"storage_backend",
			"storage_object_key",
			"upload_source",
		)

		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive File: {0}").format(self.status))

	def _validate_preview_status(self) -> None:
		if self.preview_status not in _ALLOWED_PREVIEW_STATUSES:
			frappe.throw(_("Invalid preview status for Drive File: {0}").format(self.preview_status))

	def _validate_upload_source(self) -> None:
		if self.upload_source not in _ALLOWED_UPLOAD_SOURCES:
			frappe.throw(_("Invalid upload source for Drive File: {0}").format(self.upload_source))

	def _validate_links(self) -> None:
		link_checks = (
			("file", "File"),
			("folder", "Drive Folder"),
			("current_version", "Drive File Version"),
			("organization", "Organization"),
			("school", "School"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))

