# ifitwala_drive/ifitwala_drive/doctype/drive_file_version/drive_file_version.py

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_VERSION_REASONS = {"initial_upload", "replace", "derivative", "system_regeneration"}


class DriveFileVersion(Document):
	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_fields()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_required_fields()
		self._validate_version_reason()
		self._validate_links()

	def _set_defaults(self) -> None:
		if self.is_current is None:
			self.is_current = 1

		if not self.version_reason:
			self.version_reason = "initial_upload"

	def _validate_required_fields(self) -> None:
		required_fields = ("drive_file", "version_no", "file", "storage_object_key")
		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

		if int(self.version_no) < 1:
			frappe.throw(_("Version No must be at least 1."))

	def _validate_version_reason(self) -> None:
		if self.version_reason not in _ALLOWED_VERSION_REASONS:
			frappe.throw(_("Invalid version reason for Drive File Version: {0}").format(self.version_reason))

	def _validate_links(self) -> None:
		link_checks = (
			("drive_file", "Drive File"),
			("file", "File"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))
