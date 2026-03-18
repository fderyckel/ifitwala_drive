# ifitwala_drive/ifitwala_drive/doctype/drive_binding/drive_binding.py

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_STATUSES = {"active", "inactive", "superseded"}
_ALLOWED_BINDING_ROLES = {
	"task_resource",
	"submission_artifact",
	"feedback_attachment",
	"applicant_document",
	"portfolio_evidence",
	"organization_media",
	"employee_image",
	"student_image",
	"lesson_resource",
	"lesson_activity_resource",
	"general_reference",
}


class DriveBinding(Document):
	"""Reference/binding record between a governed file and a business context.

	Important:
	- Binding is NOT ownership.
	- A file still has exactly one authoritative business-document owner.
	- Bindings only support contextual UX, reuse, and domain workflows.
	"""

	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_fields()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_required_fields()
		self._validate_status()
		self._validate_binding_role()
		self._validate_links()
		self._validate_binding_target_exists()
		self._validate_primary_uniqueness()
		self._sync_context_from_drive_file()

	def _set_defaults(self) -> None:
		if not self.status:
			self.status = "active"

		if self.is_primary is None:
			self.is_primary = 0

		if self.sort_order is None:
			self.sort_order = 0

		self.primary_key = self._build_primary_key()

	def _validate_required_fields(self) -> None:
		required_fields = (
			"drive_file",
			"file",
			"binding_doctype",
			"binding_name",
			"binding_role",
			"slot",
		)

		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive Binding: {0}").format(self.status))

	def _validate_binding_role(self) -> None:
		if self.binding_role not in _ALLOWED_BINDING_ROLES:
			frappe.throw(_("Invalid binding role for Drive Binding: {0}").format(self.binding_role))

	def _validate_links(self) -> None:
		link_checks = (
			("drive_file", "Drive File"),
			("file", "File"),
			("organization", "Organization"),
			("school", "School"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))

	def _validate_binding_target_exists(self) -> None:
		if not frappe.db.exists(self.binding_doctype, self.binding_name):
			frappe.throw(
				_("Binding target does not exist: {0} {1}").format(self.binding_doctype, self.binding_name)
			)

	def _validate_primary_uniqueness(self) -> None:
		"""Only one active primary binding per drive_file + target + role + slot."""
		if not self.is_primary or self.status != "active":
			return

		conflict_name = frappe.db.get_value(
			"Drive Binding",
			{
				"name": ["!=", self.name or ""],
				"drive_file": self.drive_file,
				"binding_doctype": self.binding_doctype,
				"binding_name": self.binding_name,
				"binding_role": self.binding_role,
				"slot": self.slot,
				"is_primary": 1,
				"status": "active",
			},
			"name",
		)

		if conflict_name:
			frappe.throw(
				_(
					"There is already an active primary binding for this file, target, role, and slot: {0}"
				).format(conflict_name)
			)

	def _sync_context_from_drive_file(self) -> None:
		"""Drive Binding should inherit org/school context from the governed file.

		This keeps bindings context-safe without pretending they own governance.
		"""
		if not self.drive_file:
			return

		drive_file = frappe.get_cached_doc("Drive File", self.drive_file)

		if not self.organization:
			self.organization = drive_file.organization

		if not self.school:
			self.school = drive_file.school

		# Defensive consistency checks.
		if self.organization and drive_file.organization and self.organization != drive_file.organization:
			frappe.throw(_("Drive Binding organization must match the Drive File organization."))

		if self.school and drive_file.school and self.school != drive_file.school:
			frappe.throw(_("Drive Binding school must match the Drive File school."))

	def _build_primary_key(self) -> str | None:
		if not self.is_primary or self.status != "active":
			return None

		parts = (
			self.drive_file,
			self.binding_doctype,
			self.binding_name,
			self.binding_role,
			self.slot,
		)
		return "|".join(str(part or "").strip() for part in parts)
