# ifitwala_drive/ifitwala_drive/doctype/drive_file_derivative/drive_file_derivative.py

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_DERIVATIVE_ROLES = {"thumb", "card", "viewer_preview", "pdf_page_1"}
_ALLOWED_STATUSES = {"pending", "processing", "ready", "failed", "unsupported", "stale"}


class DriveFileDerivative(Document):
	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_fields()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_required_fields()
		self._validate_derivative_role()
		self._validate_status()
		self._validate_links()

	def _set_defaults(self) -> None:
		if not self.status:
			self.status = "pending"

	def _validate_required_fields(self) -> None:
		required_fields = ("drive_file", "drive_file_version", "derivative_role", "status")
		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

		if self.status == "ready":
			for fieldname in ("storage_backend", "storage_object_key"):
				if not self.get(fieldname):
					frappe.throw(_("Missing required field for ready derivative: {0}").format(fieldname))

	def _validate_derivative_role(self) -> None:
		if self.derivative_role not in _ALLOWED_DERIVATIVE_ROLES:
			frappe.throw(
				_("Invalid derivative role for Drive File Derivative: {0}").format(self.derivative_role)
			)

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive File Derivative: {0}").format(self.status))

	def _validate_links(self) -> None:
		link_checks = (
			("drive_file", "Drive File"),
			("drive_file_version", "Drive File Version"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))
