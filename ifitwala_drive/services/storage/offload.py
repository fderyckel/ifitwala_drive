from __future__ import annotations

import json
import mimetypes
import os
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.storage.base import (
	build_object_key,
	get_storage_backend,
	resolve_storage_runtime_profile,
)

_PUBLIC_PREFIX = "/files/"
_PRIVATE_PREFIX = "/private/files/"
_DEFAULT_BATCH_SIZE = 100
_SAMPLE_LIMIT = 25
_OFFLOAD_QUEUE = "drive_heavy"
_OFFLOAD_JOB_TYPES = ("offload",)


def _normalize_positive_int(value: Any, *, default: int) -> int:
	try:
		normalized = int(value)
	except (TypeError, ValueError):
		return default
	return normalized if normalized > 0 else default


def _settings_batch_size(settings_doc, explicit_limit: int | None = None) -> int:
	if explicit_limit is not None:
		return _normalize_positive_int(explicit_limit, default=_DEFAULT_BATCH_SIZE)
	return _normalize_positive_int(getattr(settings_doc, "batch_size", None), default=_DEFAULT_BATCH_SIZE)


def _is_enabled(flag: Any, *, default: bool = False) -> bool:
	if flag in (None, ""):
		return default
	return bool(int(flag)) if isinstance(flag, str) and flag.isdigit() else bool(flag)


def _get_settings_doc(settings_doc=None):
	if settings_doc is not None:
		return settings_doc
	return frappe.get_cached_doc("Drive Storage Settings")


def _ensure_remote_offload_ready(settings_doc) -> None:
	profile = resolve_storage_runtime_profile()
	if profile.backend_name == "local" or profile.storage_mode == "local_only":
		frappe.throw(_("Enable a remote storage backend before running attachment offload."))

	settings_backend = str(getattr(settings_doc, "backend_name", "") or "").strip()
	if settings_backend and settings_backend != profile.backend_name:
		frappe.throw(_("Drive Storage Settings do not match the resolved storage runtime profile."))


def _query_local_file_rows(
	*, include_public: bool, include_private: bool, limit: int
) -> list[dict[str, Any]]:
	fields = [
		"name",
		"file_url",
		"is_private",
		"file_name",
		"attached_to_doctype",
		"attached_to_name",
	]

	results: list[dict[str, Any]] = []
	seen: set[str] = set()

	def _extend(url_prefix: str) -> None:
		rows = frappe.get_all(
			"File",
			fields=fields,
			filters={"file_url": ["like", f"{url_prefix}%"]},
			order_by="modified desc",
			limit_page_length=limit,
		)
		for row in rows or []:
			file_id = str(row.get("name") or "").strip()
			if not file_id or file_id in seen:
				continue
			seen.add(file_id)
			results.append(dict(row))

	if include_public:
		_extend(_PUBLIC_PREFIX)
	if include_private:
		_extend(_PRIVATE_PREFIX)

	return results[:limit]


def _query_drive_file_map(file_ids: list[str]) -> dict[str, dict[str, Any]]:
	if not file_ids:
		return {}

	rows = frappe.get_all(
		"Drive File",
		fields=[
			"name",
			"file",
			"storage_backend",
			"storage_object_key",
			"owner_doctype",
			"owner_name",
			"organization",
			"school",
		],
		filters={"file": ["in", file_ids]},
		limit_page_length=len(file_ids),
	)
	return {
		str(row.get("file") or "").strip(): dict(row)
		for row in (rows or [])
		if str(row.get("file") or "").strip()
	}


def _file_url_to_local_path(file_url: str) -> str | None:
	value = str(file_url or "").strip()
	if value.startswith(_PRIVATE_PREFIX):
		relative_path = value[len(_PRIVATE_PREFIX) :].strip("/")
		parts = ["private", "files", *[part for part in relative_path.split("/") if part]]
		return frappe.get_site_path(*parts)

	if value.startswith(_PUBLIC_PREFIX):
		relative_path = value[len(_PUBLIC_PREFIX) :].strip("/")
		parts = ["public", "files", *[part for part in relative_path.split("/") if part]]
		return frappe.get_site_path(*parts)

	return None


def _build_legacy_object_key(file_url: str) -> str:
	profile = resolve_storage_runtime_profile()
	value = str(file_url or "").strip()
	if value.startswith(_PRIVATE_PREFIX):
		relative_path = value[len(_PRIVATE_PREFIX) :].strip("/")
		return build_object_key(
			"legacy",
			"private",
			"files",
			*[part for part in relative_path.split("/") if part],
			base_prefix=profile.base_prefix,
		)

	if value.startswith(_PUBLIC_PREFIX):
		relative_path = value[len(_PUBLIC_PREFIX) :].strip("/")
		return build_object_key(
			"legacy",
			"public",
			"files",
			*[part for part in relative_path.split("/") if part],
			base_prefix=profile.base_prefix,
		)

	frappe.throw(_("Unsupported local File URL for offload: {0}").format(value))


def _build_candidate(file_row: dict[str, Any], drive_row: dict[str, Any] | None) -> dict[str, Any]:
	file_url = str(file_row.get("file_url") or "").strip()
	file_id = str(file_row.get("name") or "").strip()
	local_path = _file_url_to_local_path(file_url)
	local_exists = bool(local_path and os.path.exists(local_path))
	local_size_bytes = os.path.getsize(local_path) if local_exists and local_path else None

	attachment_kind = "governed_drive_file" if drive_row else "legacy_file_attachment"
	destination_object_key = (
		str(drive_row.get("storage_object_key") or "").strip()
		if drive_row
		else _build_legacy_object_key(file_url)
	)
	if not destination_object_key:
		destination_object_key = _build_legacy_object_key(file_url)

	status = "eligible"
	skip_reason = None
	if not local_path:
		status = "skipped"
		skip_reason = "unsupported_file_url"
	elif not local_exists:
		status = "missing_local_blob"
		skip_reason = "local_blob_missing"
	elif drive_row and str(drive_row.get("storage_backend") or "").strip() not in {"", "local"}:
		status = "already_remote"
		skip_reason = "drive_file_already_remote"

	return {
		"file_id": file_id,
		"file_url": file_url,
		"file_name": str(file_row.get("file_name") or "").strip() or None,
		"is_private": int(bool(file_row.get("is_private"))),
		"attached_to_doctype": str(file_row.get("attached_to_doctype") or "").strip() or None,
		"attached_to_name": str(file_row.get("attached_to_name") or "").strip() or None,
		"attachment_kind": attachment_kind,
		"drive_file_id": str(drive_row.get("name") or "").strip() or None if drive_row else None,
		"drive_storage_backend": str(drive_row.get("storage_backend") or "").strip() or None
		if drive_row
		else None,
		"destination_object_key": destination_object_key,
		"local_path": local_path,
		"local_exists": local_exists,
		"local_size_bytes": local_size_bytes,
		"status": status,
		"skip_reason": skip_reason,
		"owner_doctype": str(drive_row.get("owner_doctype") or "").strip() or None if drive_row else None,
		"owner_name": str(drive_row.get("owner_name") or "").strip() or None if drive_row else None,
		"organization": str(drive_row.get("organization") or "").strip() or None if drive_row else None,
		"school": str(drive_row.get("school") or "").strip() or None if drive_row else None,
	}


def _collect_candidates(settings_doc, *, limit: int | None = None) -> list[dict[str, Any]]:
	batch_size = _settings_batch_size(settings_doc, limit)
	include_public = _is_enabled(getattr(settings_doc, "migrate_public_files", None), default=True)
	include_private = _is_enabled(getattr(settings_doc, "migrate_private_files", None), default=True)
	rows = _query_local_file_rows(
		include_public=include_public,
		include_private=include_private,
		limit=batch_size,
	)
	drive_map = _query_drive_file_map([str(row.get("name") or "").strip() for row in rows])
	return [_build_candidate(row, drive_map.get(str(row.get("name") or "").strip())) for row in rows]


def _build_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
	summary = {
		"scanned": len(candidates),
		"eligible": 0,
		"already_remote": 0,
		"missing_local_blob": 0,
		"skipped": 0,
		"governed_drive_files": 0,
		"legacy_file_attachments": 0,
		"private_files": 0,
		"public_files": 0,
	}
	for candidate in candidates:
		summary[candidate["status"]] = summary.get(candidate["status"], 0) + 1
		if candidate["attachment_kind"] == "governed_drive_file":
			summary["governed_drive_files"] += 1
		else:
			summary["legacy_file_attachments"] += 1
		if candidate["is_private"]:
			summary["private_files"] += 1
		else:
			summary["public_files"] += 1
	return summary


def _store_offload_summary(
	settings_doc, *, summary: dict[str, Any], status: str, timestamp_field: str
) -> None:
	settings_doc.migration_summary_json = json.dumps(summary, sort_keys=True, indent=2)
	settings_doc.migration_status = status
	setattr(settings_doc, timestamp_field, now_datetime())
	settings_doc.save(ignore_permissions=True)


def dry_run_attachment_offload_service(*, settings_doc=None, limit: int | None = None) -> dict[str, Any]:
	settings_doc = _get_settings_doc(settings_doc)
	_ensure_remote_offload_ready(settings_doc)
	candidates = _collect_candidates(settings_doc, limit=limit)
	summary = _build_summary(candidates)
	response = {
		"summary": summary,
		"candidates": candidates[:_SAMPLE_LIMIT],
		"truncated": len(candidates) > _SAMPLE_LIMIT,
	}
	_store_offload_summary(
		settings_doc,
		summary=response,
		status="dry_run_ready",
		timestamp_field="last_validation_on",
	)
	return response


def _existing_offload_jobs(file_ids: list[str]) -> dict[str, str]:
	if not file_ids:
		return {}

	rows = frappe.get_all(
		"Drive Processing Job",
		fields=["name", "file", "status"],
		filters={
			"file": ["in", file_ids],
			"job_type": ["in", list(_OFFLOAD_JOB_TYPES)],
			"status": ["in", ["queued", "running"]],
		},
		limit_page_length=len(file_ids),
	)
	return {
		str(row.get("file") or "").strip(): str(row.get("name") or "").strip()
		for row in (rows or [])
		if str(row.get("file") or "").strip()
	}


def _build_job_payload(candidate: dict[str, Any], *, delete_local_after_verification: bool) -> dict[str, Any]:
	return {
		"attachment_kind": candidate["attachment_kind"],
		"source_file_url": candidate["file_url"],
		"source_path": candidate["local_path"],
		"destination_object_key": candidate["destination_object_key"],
		"delete_local_after_verification": bool(delete_local_after_verification),
	}


def _enqueue_job_execution(job_name: str, queue_name: str) -> None:
	enqueue = getattr(frappe, "enqueue", None)
	if not callable(enqueue):
		return

	enqueue(
		"ifitwala_drive.services.storage.offload.run_offload_job",
		queue=queue_name,
		job_id=f"drive-offload:{job_name}",
		drive_processing_job_id=job_name,
	)


def enqueue_attachment_offload_jobs_service(*, settings_doc=None, limit: int | None = None) -> dict[str, Any]:
	settings_doc = _get_settings_doc(settings_doc)
	_ensure_remote_offload_ready(settings_doc)
	candidates = _collect_candidates(settings_doc, limit=limit)
	eligible = [candidate for candidate in candidates if candidate["status"] == "eligible"]
	existing_jobs = _existing_offload_jobs([candidate["file_id"] for candidate in eligible])
	delete_local_after_verification = _is_enabled(
		getattr(settings_doc, "delete_local_after_verification", None),
		default=False,
	)

	queued_jobs: list[dict[str, Any]] = []
	skipped_existing = 0

	for candidate in eligible:
		if candidate["file_id"] in existing_jobs:
			skipped_existing += 1
			continue

		job = frappe.get_doc(
			{
				"doctype": "Drive Processing Job",
				"job_type": "offload",
				"status": "queued",
				"queue_name": _OFFLOAD_QUEUE,
				"priority": "normal",
				"drive_file": candidate["drive_file_id"],
				"file": candidate["file_id"],
				"owner_doctype": candidate["owner_doctype"],
				"owner_name": candidate["owner_name"],
				"organization": candidate["organization"],
				"school": candidate["school"],
				"payload_json": json.dumps(
					_build_job_payload(
						candidate,
						delete_local_after_verification=delete_local_after_verification,
					),
					sort_keys=True,
				),
			}
		)
		job.insert(ignore_permissions=True)
		_enqueue_job_execution(job.name, job.queue_name)
		queued_jobs.append(
			{
				"job_id": job.name,
				"file_id": candidate["file_id"],
				"drive_file_id": candidate["drive_file_id"],
				"attachment_kind": candidate["attachment_kind"],
				"destination_object_key": candidate["destination_object_key"],
			}
		)

	response = {
		"summary": {
			"eligible": len(eligible),
			"queued": len(queued_jobs),
			"skipped_existing": skipped_existing,
		},
		"queued_jobs": queued_jobs,
	}
	_store_offload_summary(
		settings_doc,
		summary=response,
		status="queued" if queued_jobs else "dry_run_ready",
		timestamp_field="last_migration_on",
	)
	return response


def _load_job_payload(job_doc) -> dict[str, Any]:
	raw = str(getattr(job_doc, "payload_json", "") or "").strip()
	if not raw:
		return {}
	parsed = json.loads(raw)
	return parsed if isinstance(parsed, dict) else {}


def _load_file_doc(file_id: str):
	if not frappe.db.exists("File", file_id):
		frappe.throw(_("File does not exist: {0}").format(file_id))
	return frappe.get_doc("File", file_id)


def _guess_mime_type(*, file_name: str | None, file_url: str | None) -> str | None:
	for candidate in (file_name, file_url):
		guessed, _ = mimetypes.guess_type(str(candidate or "").strip())
		if guessed:
			return guessed
	return None


def _mark_job_failed(job_doc, exc: Exception) -> None:
	job_doc.status = "failed"
	job_doc.error_log = str(exc)
	job_doc.finished_on = now_datetime()
	job_doc.save(ignore_permissions=True)


def run_offload_job(*, drive_processing_job_id: str) -> dict[str, Any]:
	job_doc = frappe.get_doc("Drive Processing Job", drive_processing_job_id)
	payload = _load_job_payload(job_doc)
	job_doc.status = "running"
	job_doc.started_on = now_datetime()
	job_doc.error_log = None
	job_doc.save(ignore_permissions=True)

	try:
		file_doc = _load_file_doc(job_doc.file)
		source_path = str(payload.get("source_path") or "").strip() or _file_url_to_local_path(
			getattr(file_doc, "file_url", None)
		)
		if not source_path or not os.path.exists(source_path):
			raise FileNotFoundError(source_path or getattr(file_doc, "file_url", None) or job_doc.file)

		with open(source_path, "rb") as handle:
			content = handle.read()

		storage = get_storage_backend()
		storage_artifact = storage.write_final_object(
			object_key=str(payload.get("destination_object_key") or "").strip(),
			content=content,
			mime_type=_guess_mime_type(
				file_name=getattr(file_doc, "file_name", None),
				file_url=getattr(file_doc, "file_url", None),
			),
		)

		result = {
			"attachment_kind": payload.get("attachment_kind"),
			"bytes_copied": len(content),
			"storage_backend": storage_artifact.get("storage_backend"),
			"destination_object_key": storage_artifact.get("object_key"),
			"destination_file_url": storage_artifact.get("file_url"),
			"cleanup_eligible": bool(payload.get("delete_local_after_verification")),
		}

		if getattr(job_doc, "drive_file", None):
			drive_file_doc = frappe.get_doc("Drive File", job_doc.drive_file)
			drive_file_doc.storage_backend = storage_artifact.get("storage_backend")
			drive_file_doc.storage_object_key = storage_artifact.get("object_key")
			drive_file_doc.save(ignore_permissions=True)
			result["drive_file_updated"] = True
		else:
			result["drive_file_updated"] = False

		job_doc.result_json = json.dumps(result, sort_keys=True)
		job_doc.status = "completed"
		job_doc.finished_on = now_datetime()
		job_doc.save(ignore_permissions=True)
		return result
	except Exception as exc:
		_mark_job_failed(job_doc, exc)
		raise
