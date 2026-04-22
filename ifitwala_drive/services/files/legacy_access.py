from __future__ import annotations

import json
import os
from datetime import timedelta
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.storage.base import (
	get_storage_backend,
	normalize_storage_backend_name,
	resolve_storage_runtime_profile,
)

_PUBLIC_PREFIX = "/files/"
_PRIVATE_PREFIX = "/private/files/"
_GRANT_TTL_MINUTES = 10


def _normalize_file_url(file_url: str | None) -> str:
	path = urlsplit(str(file_url or "").strip()).path
	path = unquote(path or "").strip()
	if path.startswith((_PUBLIC_PREFIX, _PRIVATE_PREFIX)):
		return path
	return ""


def _file_url_to_local_path(file_url: str) -> str | None:
	value = _normalize_file_url(file_url)
	if value.startswith(_PRIVATE_PREFIX):
		relative_path = value[len(_PRIVATE_PREFIX) :].strip("/")
		parts = ["private", "files", *[part for part in relative_path.split("/") if part]]
		return frappe.get_site_path(*parts)

	if value.startswith(_PUBLIC_PREFIX):
		relative_path = value[len(_PUBLIC_PREFIX) :].strip("/")
		parts = ["public", "files", *[part for part in relative_path.split("/") if part]]
		return frappe.get_site_path(*parts)

	return None


def _parse_json(raw: Any) -> dict[str, Any]:
	value = str(raw or "").strip()
	if not value:
		return {}
	try:
		parsed = json.loads(value)
	except json.JSONDecodeError:
		return {}
	return parsed if isinstance(parsed, dict) else {}


def _get_file_row(file_url: str) -> dict[str, Any] | None:
	rows = frappe.get_all(
		"File",
		fields=[
			"name",
			"file_url",
			"file_name",
			"is_private",
			"attached_to_doctype",
			"attached_to_name",
		],
		filters={"file_url": file_url},
		limit_page_length=1,
	)
	if not rows:
		return None
	return dict(rows[0])


def _get_file_row_by_id(file_id: str) -> dict[str, Any] | None:
	rows = frappe.get_all(
		"File",
		fields=[
			"name",
			"file_url",
			"file_name",
			"is_private",
			"attached_to_doctype",
			"attached_to_name",
		],
		filters={"name": file_id},
		limit_page_length=1,
	)
	if not rows:
		return None
	return dict(rows[0])


def _assert_can_read_private_file(file_row: dict[str, Any]) -> None:
	doctype = str(file_row.get("attached_to_doctype") or "").strip()
	name = str(file_row.get("attached_to_name") or "").strip()
	if not doctype or not name:
		frappe.throw(
			_("Private file cannot be served without an authorized owning document: {0}").format(
				file_row.get("name") or file_row.get("file_url")
			)
		)

	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} does not exist: {1}").format(doctype, name))

	doc = frappe.get_doc(doctype, name)
	if hasattr(doc, "check_permission"):
		doc.check_permission("read")


def _resolve_from_drive_file(file_id: str) -> dict[str, Any] | None:
	rows = frappe.get_all(
		"Drive File",
		fields=["name", "storage_backend", "storage_object_key"],
		filters={"file": file_id},
		limit_page_length=1,
	)
	for row in rows or []:
		backend_name = normalize_storage_backend_name(row.get("storage_backend"))
		object_key = str(row.get("storage_object_key") or "").strip()
		if object_key and backend_name != "local":
			return {
				"storage_backend": backend_name,
				"object_key": object_key,
				"source": "drive_file",
				"drive_file_id": str(row.get("name") or "").strip() or None,
			}
	return None


def _resolve_from_offload_jobs(file_id: str) -> dict[str, Any] | None:
	rows = frappe.get_all(
		"Drive Processing Job",
		fields=["name", "payload_json", "result_json"],
		filters={
			"file": file_id,
			"job_type": "offload",
			"status": "completed",
		},
		order_by="modified desc",
		limit_page_length=5,
	)
	profile_backend = normalize_storage_backend_name(resolve_storage_runtime_profile().backend_name)
	for row in rows or []:
		payload = _parse_json(row.get("payload_json"))
		result = _parse_json(row.get("result_json"))
		object_key = str(
			result.get("destination_object_key") or payload.get("destination_object_key") or ""
		).strip()
		backend_name = normalize_storage_backend_name(result.get("storage_backend"))
		if backend_name == "local" and profile_backend != "local":
			backend_name = profile_backend
		if object_key and backend_name != "local":
			return {
				"storage_backend": backend_name,
				"object_key": object_key,
				"source": "offload_job",
				"job_id": str(row.get("name") or "").strip() or None,
			}
	return None


def _resolve_remote_artifact(file_row: dict[str, Any]) -> dict[str, Any] | None:
	file_id = str(file_row.get("name") or "").strip()
	if not file_id:
		return None
	return _resolve_from_drive_file(file_id) or _resolve_from_offload_jobs(file_id)


def build_canonical_public_file_url(*, file_id: str, storage_backend: str, object_key: str) -> str | None:
	backend_name = normalize_storage_backend_name(storage_backend)
	if not file_id or not object_key or backend_name == "local":
		return None
	storage = get_storage_backend(backend_name)
	public_url = storage.build_public_object_url(object_key=object_key)
	if public_url:
		return public_url
	return (
		"/api/method/ifitwala_drive.api.access.redirect_public_file"
		f"?file_id={quote(str(file_id).strip(), safe='')}"
	)


def _format_datetime(value) -> str:
	return value.strftime("%Y-%m-%d %H:%M:%S")


def resolve_legacy_file_grant(file_url: str | None) -> dict[str, Any] | None:
	normalized_file_url = _normalize_file_url(file_url)
	if not normalized_file_url:
		return None

	local_path = _file_url_to_local_path(normalized_file_url)
	if local_path and os.path.exists(local_path):
		return None

	file_row = _get_file_row(normalized_file_url)
	if not file_row:
		return None

	is_private = bool(int(file_row.get("is_private") or 0))
	if is_private:
		_assert_can_read_private_file(file_row)

	remote_artifact = _resolve_remote_artifact(file_row)
	if not remote_artifact:
		return None

	storage = get_storage_backend(remote_artifact["storage_backend"])
	expires_on = now_datetime() + timedelta(minutes=_GRANT_TTL_MINUTES)
	grant = storage.issue_download_grant(
		object_key=remote_artifact["object_key"],
		file_url=None,
		expires_on=expires_on,
		filename=str(file_row.get("file_name") or "").strip() or None,
	)

	redirect_url = str(grant.get("url") or "").strip()
	if (
		not redirect_url
		or redirect_url == normalized_file_url
		or redirect_url.startswith((_PUBLIC_PREFIX, _PRIVATE_PREFIX))
	):
		frappe.throw(
			_("Configured storage backend cannot issue a remote read grant for migrated file: {0}").format(
				normalized_file_url
			)
		)

	return {
		"file_id": str(file_row.get("name") or "").strip() or None,
		"file_url": normalized_file_url,
		"is_private": is_private,
		"grant_type": str(grant.get("grant_type") or "").strip() or None,
		"url": redirect_url,
		"expires_on": _format_datetime(expires_on),
		"storage_backend": remote_artifact["storage_backend"],
		"object_key": remote_artifact["object_key"],
		"source": remote_artifact["source"],
	}


def resolve_public_file_redirect(
	*, file_id: str | None = None, file_url: str | None = None
) -> dict[str, Any]:
	identifier = str(file_id or "").strip()
	file_row = _get_file_row_by_id(identifier) if identifier else None
	if not file_row and file_url:
		file_row = _get_file_row(_normalize_file_url(file_url))
	if not file_row:
		frappe.throw(_("Public file does not exist."))
	if bool(int(file_row.get("is_private") or 0)):
		frappe.throw(_("Public redirect is not allowed for private files: {0}").format(file_row.get("name")))

	remote_artifact = _resolve_remote_artifact(file_row)
	if not remote_artifact:
		frappe.throw(_("No remote artifact is available for public file: {0}").format(file_row.get("name")))

	storage = get_storage_backend(remote_artifact["storage_backend"])
	url = storage.build_public_object_url(object_key=remote_artifact["object_key"])
	grant_type = "public_url"
	expires_on = None
	if not url:
		expires_on = now_datetime() + timedelta(minutes=_GRANT_TTL_MINUTES)
		grant = storage.issue_download_grant(
			object_key=remote_artifact["object_key"],
			file_url=None,
			expires_on=expires_on,
			filename=str(file_row.get("file_name") or "").strip() or None,
		)
		url = str(grant.get("url") or "").strip()
		grant_type = str(grant.get("grant_type") or "").strip() or "download_grant"

	if not url or url.startswith((_PUBLIC_PREFIX, _PRIVATE_PREFIX)):
		frappe.throw(
			_("Configured storage backend cannot issue a public redirect for file: {0}").format(
				file_row.get("name")
			)
		)

	response = {
		"file_id": str(file_row.get("name") or "").strip() or None,
		"file_url": str(file_row.get("file_url") or "").strip() or None,
		"url": url,
		"grant_type": grant_type,
		"storage_backend": remote_artifact["storage_backend"],
		"object_key": remote_artifact["object_key"],
		"source": remote_artifact["source"],
	}
	if expires_on is not None:
		response["expires_on"] = _format_datetime(expires_on)
	return response
