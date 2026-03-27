from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.integration._ed_delegate import load_ed_drive_module

_ED_MODULE = "ifitwala_ed.integrations.drive.bridge"


def _call_delegate(name: str, *args, **kwargs):
	module = load_ed_drive_module(_ED_MODULE)
	callable_obj = getattr(module, name, None)
	if not callable(callable_obj):
		frappe.throw(_("Ifitwala_Ed Drive bridge is missing delegate: {0}").format(name))
	return callable_obj(*args, **kwargs)


def reconcile_upload_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
	return _call_delegate("reconcile_upload_session_payload", payload)


def resolve_finalize_contract(upload_session_doc) -> dict[str, Any]:
	return _call_delegate("resolve_finalize_contract", upload_session_doc)


def run_post_finalize(upload_session_doc, created_file) -> dict[str, Any]:
	return _call_delegate("run_post_finalize", upload_session_doc, created_file)
