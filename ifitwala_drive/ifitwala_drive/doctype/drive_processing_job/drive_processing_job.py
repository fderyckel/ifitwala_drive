# ifitwala_drive/ifitwala_drive/doctype/drive_processing_job/drive_processing_job.py

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


_ALLOWED_JOB_TYPES = {
	"preview",
	"derivative",
	"scan",
	"index",
	"reconcile",
	"erasure",
}

_ALLOWED_STATUSES = {
	"queued",
	"running",
	"completed",
	"failed",
	"blocked",
	"cancelled",
}

_ALLOWED_QUEUES = {
	"drive_short",
	"drive_default",
	"drive_heavy",
}

_ALLOWED_PRIORITIES = {
	"low",
	"normal",
	"high",
}


class DriveProcessingJob(Document):
	"""Explicit async work tracker for Drive.

	This DocType exists to:
	- keep heavy file work off the hot request path
	- make retries and failures visible
	- preserve business-document context even for background jobs

	It must not become a second workflow engine.
	"""

	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_targets()
		self._sync_context_from_drive_file()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_job_type()
		self._validate_status()
		self._validate_queue()
		self._validate_priority()
		self._validate_required_targets()
		self._validate_attempts()
		self._validate_json_fields()
		self._validate_links()
		self._sync_context_from_drive_file()
		self._apply_status_timestamps()

	def _set_defaults(self) -> None:
		if not self.status:
			self.status = "queued"

		if not self.queue_name:
			self.queue_name = "drive_default"

		if not self.priority:
			self.priority = "normal"

		if self.attempt_count is None:
			self.attempt_count = 0

		if self.max_attempts is None:
			self.max_attempts = 3

		if not self.requested_by:
			self.requested_by = frappe.session.user

		if not self.scheduled_on:
			self.scheduled_on = now_datetime()

	def _validate_job_type(self) -> None:
		if self.job_type not in _ALLOWED_JOB_TYPES:
			frappe.throw(_("Invalid job type for Drive Processing Job: {0}").format(self.job_type))

	def _validate_status(self) -> None:
		if self.status not in _ALLOWED_STATUSES:
			frappe.throw(_("Invalid status for Drive Processing Job: {0}").format(self.status))

	def _validate_queue(self) -> None:
		if self.queue_name not in _ALLOWED_QUEUES:
			frappe.throw(_("Invalid queue name for Drive Processing Job: {0}").format(self.queue_name))

	def _validate_priority(self) -> None:
		if self.priority not in _ALLOWED_PRIORITIES:
			frappe.throw(_("Invalid priority for Drive Processing Job: {0}").format(self.priority))

	def _validate_required_targets(self) -> None:
		if not self.drive_file and not self.file:
			frappe.throw(_("Drive Processing Job requires at least one target: Drive File or File."))

	def _validate_attempts(self) -> None:
		if self.attempt_count < 0:
			frappe.throw(_("Attempt Count cannot be negative."))

		if self.max_attempts < 1:
			frappe.throw(_("Max Attempts must be at least 1."))

		if self.attempt_count > self.max_attempts:
			frappe.throw(_("Attempt Count cannot exceed Max Attempts."))

	def _validate_json_fields(self) -> None:
		for fieldname in ("payload_json", "result_json"):
			value = self.get(fieldname)
			if not value:
				continue
			try:
				json.loads(value)
			except Exception:
				frappe.throw(_("{0} must contain valid JSON.").format(self.meta.get_label(fieldname)))

	def _validate_links(self) -> None:
		link_checks = (
			("drive_file", "Drive File"),
			("file", "File"),
			("organization", "Organization"),
			("school", "School"),
			("requested_by", "User"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))

	def _sync_context_from_drive_file(self) -> None:
		"""Inherit business context from the governed file whenever possible.

		This preserves the corrected ownership model:
		- business document owner, not human creator
		- background jobs stay tied to the file's real context
		"""
		if not self.drive_file or not frappe.db.exists("Drive File", self.drive_file):
			return

		drive_file = frappe.get_cached_doc("Drive File", self.drive_file)

		if not self.file and getattr(drive_file, "file", None):
			self.file = drive_file.file

		if not self.organization and getattr(drive_file, "organization", None):
			self.organization = drive_file.organization

		if not self.school and getattr(drive_file, "school", None):
			self.school = drive_file.school

		if not self.owner_doctype and getattr(drive_file, "owner_doctype", None):
			self.owner_doctype = drive_file.owner_doctype

		if not self.owner_name and getattr(drive_file, "owner_name", None):
			self.owner_name = drive_file.owner_name

	def _apply_status_timestamps(self) -> None:
		if self.status == "running" and not self.started_on:
			self.started_on = now_datetime()

		if self.status in {"completed", "failed", "blocked", "cancelled"} and not self.finished_on:
			self.finished_on = now_datetime()
