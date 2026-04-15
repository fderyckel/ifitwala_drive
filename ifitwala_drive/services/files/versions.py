from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from ifitwala_drive.services.audit.events import record_drive_access_event
from ifitwala_drive.services.concurrency import drive_lock, is_duplicate_entry_error

_ALLOWED_REPLACE_REASONS = {"replace", "system_regeneration"}


def _version_filters(*, drive_file_id: str, version_no: int) -> dict[str, Any]:
	return {"drive_file": drive_file_id, "version_no": version_no}


def _build_version_doc(
	*,
	drive_file_id: str,
	version_no: int,
	file_id: str,
	storage_object_key: str,
	version_reason: str,
	source_version: str | None = None,
	source_file: str | None = None,
	size_bytes: int | None = None,
	mime_type: str | None = None,
	content_hash: str | None = None,
):
	return frappe.get_doc(
		{
			"doctype": "Drive File Version",
			"drive_file": drive_file_id,
			"version_no": version_no,
			"file": file_id,
			"source_version": source_version,
			"source_file": source_file,
			"is_current": 1,
			"version_reason": version_reason,
			"storage_object_key": storage_object_key,
			"size_bytes": size_bytes,
			"mime_type": mime_type,
			"content_hash": content_hash,
		}
	)


def _create_version_row(
	*,
	drive_file_id: str,
	version_no: int,
	file_id: str,
	storage_object_key: str,
	version_reason: str,
	source_version: str | None = None,
	source_file: str | None = None,
	size_bytes: int | None = None,
	mime_type: str | None = None,
	content_hash: str | None = None,
) -> str:
	version = _build_version_doc(
		drive_file_id=drive_file_id,
		version_no=version_no,
		file_id=file_id,
		storage_object_key=storage_object_key,
		version_reason=version_reason,
		source_version=source_version,
		source_file=source_file,
		size_bytes=size_bytes,
		mime_type=mime_type,
		content_hash=content_hash,
	)
	try:
		version.insert(ignore_permissions=True)
	except Exception as exc:
		if not is_duplicate_entry_error(exc):
			raise
		existing = frappe.db.get_value(
			"Drive File Version",
			_version_filters(drive_file_id=drive_file_id, version_no=version_no),
			"name",
		)
		if existing:
			return existing
		raise
	return version.name


def create_initial_drive_file_version(
	*,
	drive_file_id: str,
	file_id: str,
	storage_artifact: dict[str, Any],
	upload_session_doc,
) -> str:
	lock_key = f"drive_file_version_create:{drive_file_id}:1"
	with drive_lock(lock_key, timeout=20):
		existing = frappe.db.get_value(
			"Drive File Version",
			_version_filters(drive_file_id=drive_file_id, version_no=1),
			"name",
		)
		if existing:
			return existing

		return _create_version_row(
			drive_file_id=drive_file_id,
			version_no=1,
			file_id=file_id,
			storage_object_key=storage_artifact["object_key"],
			version_reason="initial_upload",
			size_bytes=getattr(upload_session_doc, "received_size_bytes", None)
			or storage_artifact.get("size_bytes"),
			mime_type=storage_artifact.get("mime_type")
			or getattr(upload_session_doc, "mime_type_hint", None),
			content_hash=getattr(upload_session_doc, "content_hash", None)
			or storage_artifact.get("content_hash"),
		)


def _deactivate_current_version(current_version_id: str | None) -> None:
	current_version_id = str(current_version_id or "").strip()
	if not current_version_id or not frappe.db.exists("Drive File Version", current_version_id):
		return

	current_version_doc = frappe.get_doc("Drive File Version", current_version_id)
	current_version_doc.is_current = 0
	current_version_doc.save(ignore_permissions=True)


def _sync_active_bindings_to_file(drive_file_id: str, *, file_id: str) -> None:
	get_all = getattr(frappe, "get_all", None)
	if not callable(get_all):
		return

	for row in get_all(
		"Drive Binding",
		filters={"drive_file": drive_file_id, "status": "active"},
		fields=["name"],
	):
		binding_id = str(row.get("name") or "").strip()
		if not binding_id:
			continue
		binding_doc = frappe.get_doc("Drive Binding", binding_id)
		binding_doc.file = file_id
		binding_doc.save(ignore_permissions=True)


def _validate_replace_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
	drive_file_id = str(payload.get("drive_file_id") or "").strip()
	if not drive_file_id:
		frappe.throw(_("Missing required field: drive_file_id"))
	if not frappe.db.exists("Drive File", drive_file_id):
		frappe.throw(_("Drive File does not exist: {0}").format(drive_file_id))

	new_file_artifact = payload.get("new_file_artifact")
	if not isinstance(new_file_artifact, dict):
		frappe.throw(_("Missing required field: new_file_artifact"))

	for fieldname in ("file_id", "storage_object_key"):
		if not new_file_artifact.get(fieldname):
			frappe.throw(_("Missing required new_file_artifact field: {0}").format(fieldname))

	reason = str(payload.get("reason") or "replace").strip()
	if reason not in _ALLOWED_REPLACE_REASONS:
		frappe.throw(_("Invalid replace reason: {0}").format(reason))

	return drive_file_id, new_file_artifact


def replace_drive_file_version_service(payload: dict[str, Any]) -> dict[str, Any]:
	drive_file_id, new_file_artifact = _validate_replace_payload(payload)

	with drive_lock(f"drive_file_replace:{drive_file_id}", timeout=30):
		drive_file = frappe.get_doc("Drive File", drive_file_id)
		owner_doc = frappe.get_doc(drive_file.owner_doctype, drive_file.owner_name)
		if hasattr(owner_doc, "check_permission"):
			owner_doc.check_permission("write")

		if drive_file.status != "active":
			frappe.throw(_("Drive File is not replaceable in status: {0}").format(drive_file.status))
		if int(getattr(drive_file, "legal_hold", 0) or 0):
			frappe.throw(_("Drive File cannot be replaced while legal hold is active."))
		if getattr(drive_file, "erasure_state", "active") != "active":
			frappe.throw(
				_("Drive File cannot be replaced while erasure state is {0}.").format(
					drive_file.erasure_state
				)
			)

		next_version_no = int(getattr(drive_file, "current_version_no", 0) or 0) + 1
		current_version_id = getattr(drive_file, "current_version", None)
		current_file_id = getattr(drive_file, "file", None)

		version_id = _create_version_row(
			drive_file_id=drive_file.name,
			version_no=next_version_no,
			file_id=new_file_artifact["file_id"],
			storage_object_key=new_file_artifact["storage_object_key"],
			version_reason=str(payload.get("reason") or "replace").strip(),
			source_version=current_version_id,
			source_file=current_file_id,
			size_bytes=new_file_artifact.get("size_bytes"),
			mime_type=new_file_artifact.get("mime_type"),
			content_hash=new_file_artifact.get("content_hash"),
		)

		_deactivate_current_version(current_version_id)

		drive_file.file = new_file_artifact["file_id"]
		drive_file.display_name = new_file_artifact.get("filename_original") or drive_file.display_name
		drive_file.storage_object_key = new_file_artifact["storage_object_key"]
		if new_file_artifact.get("content_hash"):
			drive_file.content_hash = new_file_artifact["content_hash"]
		drive_file.current_version = version_id
		drive_file.current_version_no = next_version_no
		drive_file.preview_status = "pending"
		drive_file.save(ignore_permissions=True)

		_sync_active_bindings_to_file(drive_file.name, file_id=new_file_artifact["file_id"])

	record_drive_access_event(
		drive_file_id=drive_file.name,
		drive_file_version_id=version_id,
		event_type="replace",
		metadata={
			"reason": payload.get("reason") or "replace",
			"current_version_no": next_version_no,
			"source_version": current_version_id,
		},
	)

	return {
		"drive_file_id": drive_file.name,
		"drive_file_version_id": version_id,
		"current_version_no": next_version_no,
		"status": drive_file.status,
	}
