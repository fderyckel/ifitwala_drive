from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_SCOPES = {"all", "files_only", "slot_only"}
_ALLOWED_STATUSES = {"draft", "approved", "executing", "completed", "blocked"}


class DriveErasureRequest(Document):
	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_fields()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_required_fields()
		self._validate_scope()
		self._validate_status()
		self._validate_links()

	def _set_defaults(self) -> None:
		if not self.requested_by:
			self.requested_by = getattr(getattr(frappe, "session", None), "user", None)

		if not self.scope:
			self.scope = "files_only"

		if not self.status:
			self.status = "draft"

		if self.result_deleted_count is None:
			self.result_deleted_count = 0

		if self.result_blocked_count is None:
			self.result_blocked_count = 0

	def _validate_required_fields(self) -> None:
		for fieldname in ("data_subject_type", "data_subject_id", "scope", "status"):
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

	def _validate_scope(self) -> None:
		if self.scope not in _ALLOWED_SCOPES:
			frappe.throw(_("Invalid scope for Drive Erasure Request: {0}").format(self.scope))
		if self.scope == "slot_only" and not self.slot_filter:
			frappe.throw(_("Slot Filter is required when Drive Erasure Request scope is slot_only."))

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive Erasure Request: {0}").format(self.status))

	def _validate_links(self) -> None:
		if self.requested_by and not frappe.db.exists("User", self.requested_by):
			frappe.throw(_("User does not exist: {0}").format(self.requested_by))
