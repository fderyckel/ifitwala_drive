from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

_ALLOWED_EVENT_TYPES = {
	"upload",
	"replace",
	"download_grant",
	"preview_open",
	"delete",
	"erase",
	"bind",
	"unbind",
}


class DriveAccessEvent(Document):
	def before_insert(self) -> None:
		self._set_defaults()
		self._validate_required_fields()

	def validate(self) -> None:
		self._set_defaults()
		self._validate_required_fields()
		self._validate_event_type()
		self._validate_json_fields()
		self._validate_links()

	def _set_defaults(self) -> None:
		if not self.actor:
			self.actor = getattr(getattr(frappe, "session", None), "user", None)

		if not self.event_on:
			self.event_on = now_datetime()

		if not self.request_ip:
			self.request_ip = getattr(getattr(frappe, "local", None), "request_ip", None)

	def _validate_required_fields(self) -> None:
		for fieldname in ("drive_file", "event_type"):
			if not self.get(fieldname):
				frappe.throw(_("Missing required field: {0}").format(fieldname))

	def _validate_event_type(self) -> None:
		if self.event_type not in _ALLOWED_EVENT_TYPES:
			frappe.throw(_("Invalid event type for Drive Access Event: {0}").format(self.event_type))

	def _validate_json_fields(self) -> None:
		if not self.metadata_json:
			return
		try:
			json.loads(self.metadata_json)
		except Exception:
			frappe.throw(_("Metadata JSON must contain valid JSON."))

	def _validate_links(self) -> None:
		link_checks = (
			("drive_file", "Drive File"),
			("drive_file_version", "Drive File Version"),
			("actor", "User"),
		)

		for fieldname, doctype in link_checks:
			value = self.get(fieldname)
			if value and not frappe.db.exists(doctype, value):
				frappe.throw(_("{0} does not exist: {1}").format(doctype, value))
