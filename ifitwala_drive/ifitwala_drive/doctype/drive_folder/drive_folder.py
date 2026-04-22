# ifitwala_drive/ifitwala_drive/doctype/drive_folder/drive_folder.py

from __future__ import annotations

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document

from ifitwala_drive.services.folders.key_builder import build_folder_system_key, slugify_folder_title

_ALLOWED_STATUSES = {"active", "archived", "disabled"}
_ALLOWED_FOLDER_KINDS = {
	"teacher_private",
	"course_shared",
	"organization_media",
	"system_bound",
	"student_workspace",
	"guardian_workspace",
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
		"""Use a stable scoped identifier and keep `title` as the human-facing label."""
		if not self.title:
			frappe.throw(_("Title is required."))

		self._set_defaults()
		self.name = self._build_name()

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
			self.slug = slugify_folder_title(self.slug)
		else:
			self.slug = slugify_folder_title(self.title)

		self.system_key = self._build_system_key()

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
			self.path_cache = self.slug or slugify_folder_title(self.title)
			return

		parent = frappe.get_cached_doc("Drive Folder", self.parent_drive_folder)
		parent_path = parent.path_cache or slugify_folder_title(parent.title)
		self.depth = (parent.depth or 0) + 1
		self.path_cache = f"{parent_path}/{self.slug}"

	def _build_system_key(self) -> str:
		return build_folder_system_key(
			title=self.title,
			parent_drive_folder=self.parent_drive_folder,
			owner_doctype=self.owner_doctype,
			owner_name=self.owner_name,
			organization=self.organization,
			school=self.school,
			folder_kind=self.folder_kind,
		)

	def _build_name(self) -> str:
		digest = hashlib.sha1(self.system_key.encode("utf-8")).hexdigest()[:16].upper()
		return f"DRF-{digest}"
