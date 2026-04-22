from __future__ import annotations

from urllib.parse import urlsplit

import frappe

from ifitwala_drive.services.files.legacy_access import resolve_legacy_file_grant


def _request_path() -> str:
	request = getattr(getattr(frappe, "local", None), "request", None)
	if request is None:
		request = getattr(frappe, "request", None)
	if request is None:
		return ""
	path = getattr(request, "path", "") or ""
	return urlsplit(str(path)).path


def _request_method() -> str:
	request = getattr(getattr(frappe, "local", None), "request", None)
	if request is None:
		request = getattr(frappe, "request", None)
	if request is None:
		return ""
	return str(getattr(request, "method", "") or "").upper()


def redirect_migrated_legacy_file_requests() -> None:
	if _request_method() not in {"GET", "HEAD"}:
		return

	request_path = _request_path()
	if not request_path.startswith(("/files/", "/private/files/")):
		return

	grant = resolve_legacy_file_grant(request_path)
	if not grant:
		return

	local_context = getattr(frappe, "local", None)
	if local_context is None:
		return

	response = getattr(local_context, "response", None)
	if response is None:
		response = {}
		local_context.response = response

	response["type"] = "redirect"
	response["location"] = grant["url"]
	response["http_status_code"] = 302
