# ifitwala_drive/ifitwala_drive/doctype/drive_folder/drive_folder.py

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_STATUSES = {"active", "archived", "disabled"}
_ALLOWED_FOLDER_KINDS = {
	"teacher_private",
	"course_shared",
	"organization_media",
	"system_bound",
	"student_workspace",
	"applicant_documents",
	"staff_documents",
	"general_resource",
}


class DriveFolder(Document):
	"""Navigation/container object for Drive browse UX.

	Important:
	- folders are NOT governance truth
	- folders do NOT replace owning-document anchoring
	- file visibility still roots in owning-document visibility
	- folders must remain deterministic, organization-safe, and tree-safe
	"""

	def before_insert(self) -> None:
		self._set_defaults()
		self._sync_path_fields()
		self._validate_required_context()
		self._validate_owner_contract()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_status()
		self._validate_folder_kind()
		self._validate_required_context()
		self._validate_owner_contract()
		self._validate_links()
		self._validate_parent_rules()
		self._sync_path_fields()

	def autoname(self) -> None:
		"""Keep names human-readable but deterministic enough for early v1.

		If duplicate titles under the same parent become a real issue later,
		we can move to a slug + suffix or opaque ID naming pattern.
		"""
		if not self.title:
			frappe.throw(_("Title is required."))

		# Let Frappe's rename/duplicate handling do the rest.
		self.name = self.title.strip()

	def _set_defaults(self) -> None:
		if not self.status:
			self.status = "active"

		if self.is_private is None:
			self.is_private = 1

		if self.is_system_managed is None:
			self.is_system_managed = 0

		if self.allow_descendant_reuse is None:
			self.allow_descendant_reuse = 0

		if self.sort_order is None:
			self.sort_order = 0

		if self.slug:
			self.slug = self._slugify(self.slug)
		else:
			self.slug = self._slugify(self.title)

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive Folder: {0}").format(self.status))

	def _validate_folder_kind(self) -> None:
		if self.folder_kind not in _ALLOWED_FOLDER_KINDS:
			frappe.throw(_("Invalid folder kind for Drive Folder: {0}").format(self.folder_kind))

	def _validate_required_context(self) -> None:
		required_fields = (
			"title",
			"owner_doctype",
			"owner_name",
			"organization",
			"folder_kind",
		)

		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

	def _validate_owner_contract(self) -> None:
		"""Folder ownership must be business-document ownership, never human ownership."""
		if self.owner_doctype == "User":
			frappe.throw(_("Owner Doctype cannot be User. Folder ownership must be a business document."))

		if self.owner_name == frappe.session.user:
			frappe.throw(
				_("Owner Name appears to be the current user. Use the owning business document instead.")
			)

	def _validate_links(self) -> None:
		link_checks = (
			("organization", "Organization"),
			("school", "School"),
			("parent_drive_folder", "Drive Folder"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))

	def _validate_parent_rules(self) -> None:
		"""Keep the tree deterministic and organization-safe."""
		if not self.parent_drive_folder:
			return

		if self.parent_drive_folder == self.name:
			frappe.throw(_("A folder cannot be its own parent."))

		parent = frappe.get_doc("Drive Folder", self.parent_drive_folder)

		if parent.organization != self.organization:
			frappe.throw(_("Parent folder must belong to the same organization."))

		# If the child is school-scoped, parent must either match school or be org-level.
		if self.school and parent.school and parent.school != self.school:
			frappe.throw(_("Parent folder school scope must match the child folder school scope."))

		# Prevent archived/disabled parents from receiving active children.
		if self.status == "active" and parent.status != "active":
			frappe.throw(_("An active folder cannot be placed under a non-active parent folder."))

	def _sync_path_fields(self) -> None:
		if not self.parent_drive_folder:
			self.depth = 0
			self.path_cache = self.slug or self._slugify(self.title)
			return

		parent = frappe.get_cached_doc("Drive Folder", self.parent_drive_folder)
		parent_path = parent.path_cache or self._slugify(parent.title)
		self.depth = (parent.depth or 0) + 1
		self.path_cache = f"{parent_path}/{self.slug}"

	def _slugify(self, value: str | None) -> str:
		value = (value or "").strip().lower()
		value = re.sub(r"[^a-z0-9]+", "-", value)
		value = re.sub(r"-{2,}", "-", value).strip("-")
		return value or "folder"
