# ifitwala_drive/ifitwala_drive/api/uploads.py

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.uploads.finalize import finalize_upload_session_service
from ifitwala_drive.services.uploads.sessions import (
	abort_upload_session_service,
	create_upload_session_service,
)


@frappe.whitelist()
def create_upload_session(**kwargs: Any) -> dict[str, Any]:
	"""Create a Drive Upload Session and return an upload target.

	This is the canonical entrypoint for new governed uploads.
	It must fail closed on missing governance context.
	"""
	return create_upload_session_service(kwargs)


@frappe.whitelist()
def finalize_upload_session(**kwargs: Any) -> dict[str, Any]:
	"""Finalize an upload session and create the governed file artifact."""
	return finalize_upload_session_service(kwargs)


@frappe.whitelist()
def abort_upload_session(**kwargs: Any) -> dict[str, Any]:
	"""Abort an upload session and invalidate its temporary upload target."""
	return abort_upload_session_service(kwargs)
