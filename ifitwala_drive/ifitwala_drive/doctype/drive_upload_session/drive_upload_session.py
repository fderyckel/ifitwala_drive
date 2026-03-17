# ifitwala_drive/ifitwala_drive/doctype/drive_upload_session/drive_upload_session.py

from __future__ import annotations

import secrets

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime
from frappe import _


_ALLOWED_STATUSES = {
	"created",
	"uploading",
	"uploaded",
	"finalizing",
	"completed",
	"aborted",
	"expired",
	"failed",
}

_OPTIONAL_SCHOOL_SUBJECT_TYPES = {"Employee", "Organization"}


class DriveUploadSession(Document):
	"""Authoritative upload-session record for governed Drive uploads.

	This DocType is intentionally lightweight:
	- it does NOT replace File Classification
	- it does NOT finalize governed files by itself
	- it exists to make upload lifecycle explicit, resumable-ready, and auditable

	The final governed file must still be created through the authoritative
	dispatcher / Drive service boundary that creates File + File Classification
	atomically. This preserves the locked Ifitwala_Ed governance contract.
	"""

	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_context()
		self._validate_governance_intent()
		self._validate_owner_contract()
		self._validate_school_requirement()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_status()
		self._validate_required_context()
		self._validate_governance_intent()
		self._validate_owner_contract()
		self._validate_school_requirement()
		self._validate_size_fields()
		self._validate_terminal_state_fields()
		self._validate_links()

	def _set_defaults(self) -> None:
		if not self.session_key:
			self.session_key = secrets.token_urlsafe(24)

		if not self.upload_token:
			self.upload_token = secrets.token_urlsafe(32)

		if not self.created_by_user:
			self.created_by_user = frappe.session.user

		if not self.status:
			self.status = "created"

		if self.is_private is None:
			self.is_private = 1

		if not self.expires_on:
			self.expires_on = add_to_date(now_datetime(), hours=2, as_datetime=True)

		if self.received_size_bytes is None:
			self.received_size_bytes = 0

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive Upload Session: {0}").format(self.status))

	def _validate_required_context(self) -> None:
		required_fields = (
			"attached_doctype",
			"attached_name",
			"owner_doctype",
			"owner_name",
			"organization",
			"filename_original",
		)

		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

	def _validate_governance_intent(self) -> None:
		required_fields = (
			"intended_primary_subject_type",
			"intended_primary_subject_id",
			"intended_data_class",
			"intended_purpose",
			"intended_retention_policy",
			"intended_slot",
		)

		for fieldname in required_fields:
			if not self.get(fieldname):
				frappe.throw(_("Missing required governance intent field: {0}").format(fieldname))

	def _validate_owner_contract(self) -> None:
		"""Ownership must mean business-document owner, never human uploader.

		This reflects the corrected design lock:
		- creator/uploader is audit metadata only
		- subject is who/what the file is about
		- owner is the authoritative business document controlling lifecycle
		"""
		if self.owner_doctype == "User":
			frappe.throw(_("Owner Doctype cannot be User. Use the business document owner instead."))

		if self.owner_name == frappe.session.user:
			# Defensive check. A user string matching owner_name is almost always a modeling bug.
			frappe.throw(_("Owner Name appears to be the current user. Owner must be a business document, not a human uploader."))

	def _validate_school_requirement(self) -> None:
		if not self._is_school_required():
			return

		if not self.school:
			frappe.throw(_("School is required for this upload context."))

	def _validate_size_fields(self) -> None:
		if (self.expected_size_bytes or 0) < 0:
			frappe.throw(_("Expected Size (Bytes) cannot be negative."))

		if (self.received_size_bytes or 0) < 0:
			frappe.throw(_("Received Size (Bytes) cannot be negative."))

		if self.expected_size_bytes and self.received_size_bytes:
			if self.received_size_bytes > self.expected_size_bytes:
				frappe.throw(_("Received Size (Bytes) cannot exceed Expected Size (Bytes)."))

	def _validate_terminal_state_fields(self) -> None:
		if self.status == "completed" and not self.completed_on:
			self.completed_on = now_datetime()

		if self.status == "aborted" and not self.aborted_on:
			self.aborted_on = now_datetime()

	def _validate_links(self) -> None:
		"""These links are optional in early flow, but if present they must exist."""
		link_checks = (
			("organization", "Organization"),
			("school", "School"),
			("folder", "Drive Folder"),
			("created_by_user", "User"),
			("file", "File"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))

	def _is_school_required(self) -> bool:
		try:
			from ifitwala_ed.utilities.file_classification_contract import (
				is_school_required_for_subject_type,
			)
		except ImportError:
			return (self.intended_primary_subject_type or "").strip() not in _OPTIONAL_SCHOOL_SUBJECT_TYPES

		return is_school_required_for_subject_type(self.intended_primary_subject_type)
