from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from ifitwala_drive.services.files.legacy_access import build_canonical_public_file_url
from ifitwala_drive.services.queueing import resolve_enqueue_queue
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
_PRUNE_QUEUE = "drive_heavy"
_OFFLOAD_JOB_TYPES = ("offload",)
_PRUNE_JOB_TYPES = ("prune_local",)


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


def _parse_json(raw: Any) -> dict[str, Any]:
	value = str(raw or "").strip()
	if not value:
		return {}
	try:
		parsed = json.loads(value)
	except json.JSONDecodeError:
		return {}
	return parsed if isinstance(parsed, dict) else {}


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
		queue=resolve_enqueue_queue(queue_name),
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
	return _parse_json(getattr(job_doc, "payload_json", None))


def _load_file_doc(file_id: str):
	if not frappe.db.exists("File", file_id):
		frappe.throw(_("File does not exist: {0}").format(file_id))
	return frappe.get_doc("File", file_id)


def _load_drive_file_doc(drive_file_id: str | None):
	identifier = str(drive_file_id or "").strip()
	if not identifier or not frappe.db.exists("Drive File", identifier):
		return None
	return frappe.get_doc("Drive File", identifier)


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


def _sha256_hexdigest(content: bytes) -> str:
	return hashlib.sha256(content).hexdigest()


def _owner_context(file_doc, drive_file_doc=None) -> tuple[str | None, str | None]:
	doctype = str(getattr(file_doc, "attached_to_doctype", "") or "").strip() or None
	name = str(getattr(file_doc, "attached_to_name", "") or "").strip() or None
	if doctype and name:
		return doctype, name

	if drive_file_doc is not None:
		doctype = str(getattr(drive_file_doc, "owner_doctype", "") or "").strip() or None
		name = str(getattr(drive_file_doc, "owner_name", "") or "").strip() or None
		return doctype, name

	return None, None


def _read_remote_metadata(*, storage_backend: str | None, object_key: str) -> dict[str, Any]:
	backend_name = str(storage_backend or "").strip()
	if not backend_name:
		return {
			"exists": False,
			"size_bytes": None,
			"checksum": None,
			"verifiable": False,
		}
	storage = get_storage_backend(backend_name)
	return storage.read_object_metadata(object_key=object_key)


def _cleanup_empty_attachment_parents(path: str) -> None:
	target = os.path.abspath(str(path or "").strip())
	if not target:
		return
	roots = [
		os.path.abspath(frappe.get_site_path("private", "files")),
		os.path.abspath(frappe.get_site_path("public", "files")),
	]
	current = os.path.dirname(target)
	while current and current not in roots and any(current.startswith(f"{root}{os.sep}") for root in roots):
		try:
			os.rmdir(current)
		except OSError:
			break
		current = os.path.dirname(current)


def _evaluate_local_prune(
	*,
	file_doc,
	drive_file_doc=None,
	source_path: str,
	storage_backend: str | None,
	destination_object_key: str,
	expected_size_bytes: int | None,
) -> dict[str, Any]:
	file_url = str(getattr(file_doc, "file_url", "") or "").strip()
	local_path = str(source_path or "").strip() or _file_url_to_local_path(file_url)
	is_private = bool(int(getattr(file_doc, "is_private", 0) or 0)) or file_url.startswith(_PRIVATE_PREFIX)
	is_public = file_url.startswith(_PUBLIC_PREFIX) and not is_private

	response = {
		"file_url": file_url,
		"source_path": local_path,
		"is_private": is_private,
		"is_public": is_public,
		"storage_backend": str(storage_backend or "").strip() or None,
		"destination_object_key": str(destination_object_key or "").strip(),
		"local_exists": bool(local_path and os.path.exists(local_path)),
		"local_size_bytes": os.path.getsize(local_path)
		if local_path and os.path.exists(local_path)
		else None,
		"canonical_file_url": None,
		"cleanup_performed": False,
		"cleanup_blocked_reason": None,
	}

	if not local_path:
		response["cleanup_blocked_reason"] = "unsupported_file_url"
		return response
	if not response["local_exists"]:
		response["cleanup_blocked_reason"] = "local_blob_missing"
		return response
	if not is_private:
		if not is_public:
			response["cleanup_blocked_reason"] = "unsupported_file_visibility"
			return response

	remote_metadata = _read_remote_metadata(
		storage_backend=storage_backend,
		object_key=response["destination_object_key"],
	)
	response["remote_verifiable"] = bool(remote_metadata.get("verifiable"))
	response["remote_exists"] = bool(remote_metadata.get("exists"))
	response["remote_size_bytes"] = remote_metadata.get("size_bytes")
	response["remote_checksum"] = remote_metadata.get("checksum")

	if not response["destination_object_key"]:
		response["cleanup_blocked_reason"] = "missing_destination_object_key"
		return response
	if not response["storage_backend"] or response["storage_backend"] == "local":
		response["cleanup_blocked_reason"] = "missing_remote_storage_backend"
		return response
	if not response["remote_verifiable"]:
		response["cleanup_blocked_reason"] = "remote_verification_unavailable"
		return response
	if not response["remote_exists"]:
		response["cleanup_blocked_reason"] = "remote_object_missing"
		return response
	if expected_size_bytes is not None and response["local_size_bytes"] != int(expected_size_bytes):
		response["cleanup_blocked_reason"] = "local_size_changed_since_offload"
		return response
	if (
		response["remote_size_bytes"] is not None
		and response["local_size_bytes"] is not None
		and int(response["remote_size_bytes"]) != int(response["local_size_bytes"])
	):
		response["cleanup_blocked_reason"] = "remote_size_mismatch"
		return response

	if is_private:
		owner_doctype, owner_name = _owner_context(file_doc, drive_file_doc)
		if not owner_doctype or not owner_name or not frappe.db.exists(owner_doctype, owner_name):
			response["cleanup_blocked_reason"] = "private_owner_missing"
			return response
	else:
		file_id = str(getattr(file_doc, "name", "") or "").strip()
		response["canonical_file_url"] = build_canonical_public_file_url(
			file_id=file_id,
			storage_backend=response["storage_backend"],
			object_key=response["destination_object_key"],
		)
		if not response["canonical_file_url"]:
			response["cleanup_blocked_reason"] = "public_file_canonical_url_unavailable"
			return response

	return response


def _remove_local_attachment_path(path: str) -> None:
	os.remove(path)
	_cleanup_empty_attachment_parents(path)


def _attempt_local_prune(
	*,
	file_doc,
	drive_file_doc=None,
	source_path: str,
	storage_backend: str | None,
	destination_object_key: str,
	expected_size_bytes: int | None,
) -> dict[str, Any]:
	evaluation = _evaluate_local_prune(
		file_doc=file_doc,
		drive_file_doc=drive_file_doc,
		source_path=source_path,
		storage_backend=storage_backend,
		destination_object_key=destination_object_key,
		expected_size_bytes=expected_size_bytes,
	)
	if evaluation.get("cleanup_blocked_reason"):
		return evaluation

	if evaluation.get("is_public"):
		file_doc.file_url = evaluation["canonical_file_url"]
		file_doc.save(ignore_permissions=True)

	_remove_local_attachment_path(evaluation["source_path"])
	evaluation["cleanup_performed"] = True
	evaluation["deleted_bytes"] = evaluation.get("local_size_bytes")
	return evaluation


def _query_completed_offload_rows(limit: int) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"Drive Processing Job",
		fields=["name", "file", "drive_file", "payload_json", "result_json", "status"],
		filters={
			"job_type": ["in", list(_OFFLOAD_JOB_TYPES)],
			"status": "completed",
		},
		order_by="modified desc",
		limit_page_length=max(limit, 1),
	)
	results: list[dict[str, Any]] = []
	seen_files: set[str] = set()
	for row in rows or []:
		file_id = str(row.get("file") or "").strip()
		if not file_id or file_id in seen_files:
			continue
		seen_files.add(file_id)
		results.append(dict(row))
	return results[:limit]


def _existing_prune_jobs(file_ids: list[str]) -> dict[str, str]:
	if not file_ids:
		return {}

	rows = frappe.get_all(
		"Drive Processing Job",
		fields=["name", "file", "status"],
		filters={
			"file": ["in", file_ids],
			"job_type": ["in", list(_PRUNE_JOB_TYPES)],
			"status": ["in", ["queued", "running"]],
		},
		limit_page_length=len(file_ids),
	)
	return {
		str(row.get("file") or "").strip(): str(row.get("name") or "").strip()
		for row in (rows or [])
		if str(row.get("file") or "").strip()
	}


def _build_prune_candidate(job_row: dict[str, Any]) -> dict[str, Any]:
	file_doc = _load_file_doc(job_row.get("file"))
	drive_file_doc = _load_drive_file_doc(job_row.get("drive_file"))
	payload = _parse_json(job_row.get("payload_json"))
	result = _parse_json(job_row.get("result_json"))
	destination_object_key = str(
		result.get("destination_object_key") or payload.get("destination_object_key") or ""
	).strip()
	storage_backend = str(
		result.get("storage_backend") or getattr(drive_file_doc, "storage_backend", None) or ""
	).strip()
	evaluation = _evaluate_local_prune(
		file_doc=file_doc,
		drive_file_doc=drive_file_doc,
		source_path=str(payload.get("source_path") or "").strip(),
		storage_backend=storage_backend,
		destination_object_key=destination_object_key,
		expected_size_bytes=result.get("bytes_copied"),
	)
	status = "eligible" if not evaluation.get("cleanup_blocked_reason") else "blocked"
	return {
		"offload_job_id": str(job_row.get("name") or "").strip() or None,
		"file_id": str(getattr(file_doc, "name", "") or "").strip() or None,
		"drive_file_id": str(getattr(drive_file_doc, "name", "") or "").strip() or None,
		"file_url": str(getattr(file_doc, "file_url", "") or "").strip() or None,
		"file_name": str(getattr(file_doc, "file_name", "") or "").strip() or None,
		"storage_backend": storage_backend or None,
		"destination_object_key": destination_object_key or None,
		"source_path": evaluation.get("source_path"),
		"local_exists": evaluation.get("local_exists"),
		"local_size_bytes": evaluation.get("local_size_bytes"),
		"remote_size_bytes": evaluation.get("remote_size_bytes"),
		"remote_verifiable": evaluation.get("remote_verifiable"),
		"is_private": evaluation.get("is_private"),
		"canonical_file_url": evaluation.get("canonical_file_url"),
		"status": status,
		"skip_reason": evaluation.get("cleanup_blocked_reason"),
	}


def _build_prune_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
	summary = {
		"scanned": len(candidates),
		"eligible": 0,
		"blocked": 0,
		"private_files": 0,
		"public_files": 0,
	}
	for candidate in candidates:
		summary[candidate["status"]] = summary.get(candidate["status"], 0) + 1
		if candidate.get("is_private"):
			summary["private_files"] += 1
		else:
			summary["public_files"] += 1
		reason = str(candidate.get("skip_reason") or "").strip()
		if reason:
			summary[reason] = summary.get(reason, 0) + 1
	return summary


def _collect_prune_candidates(settings_doc, *, limit: int | None = None) -> list[dict[str, Any]]:
	batch_size = _settings_batch_size(settings_doc, limit)
	completed_rows = _query_completed_offload_rows(batch_size)
	candidates: list[dict[str, Any]] = []
	for row in completed_rows:
		candidate = _build_prune_candidate(row)
		if candidate.get("is_private") and not _is_enabled(
			getattr(settings_doc, "migrate_private_files", None), default=True
		):
			continue
		if not candidate.get("is_private") and not _is_enabled(
			getattr(settings_doc, "migrate_public_files", None), default=True
		):
			continue
		candidates.append(candidate)
	return candidates


def dry_run_local_prune_service(*, settings_doc=None, limit: int | None = None) -> dict[str, Any]:
	settings_doc = _get_settings_doc(settings_doc)
	_ensure_remote_offload_ready(settings_doc)
	candidates = _collect_prune_candidates(settings_doc, limit=limit)
	summary = _build_prune_summary(candidates)
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


def _enqueue_prune_job_execution(job_name: str, queue_name: str) -> None:
	enqueue = getattr(frappe, "enqueue", None)
	if not callable(enqueue):
		return
	enqueue(
		"ifitwala_drive.services.storage.offload.run_prune_job",
		queue=resolve_enqueue_queue(queue_name),
		job_id=f"drive-prune:{job_name}",
		drive_processing_job_id=job_name,
	)


def enqueue_local_prune_jobs_service(*, settings_doc=None, limit: int | None = None) -> dict[str, Any]:
	settings_doc = _get_settings_doc(settings_doc)
	_ensure_remote_offload_ready(settings_doc)
	candidates = _collect_prune_candidates(settings_doc, limit=limit)
	eligible = [candidate for candidate in candidates if candidate["status"] == "eligible"]
	existing_jobs = _existing_prune_jobs([candidate["file_id"] for candidate in eligible])

	queued_jobs: list[dict[str, Any]] = []
	skipped_existing = 0
	for candidate in eligible:
		if candidate["file_id"] in existing_jobs:
			skipped_existing += 1
			continue

		job = frappe.get_doc(
			{
				"doctype": "Drive Processing Job",
				"job_type": "prune_local",
				"status": "queued",
				"queue_name": _PRUNE_QUEUE,
				"priority": "normal",
				"drive_file": candidate["drive_file_id"],
				"file": candidate["file_id"],
				"payload_json": json.dumps(
					{
						"offload_job_id": candidate["offload_job_id"],
						"source_path": candidate["source_path"],
						"destination_object_key": candidate["destination_object_key"],
						"storage_backend": candidate["storage_backend"],
						"verified_remote_size_bytes": candidate["remote_size_bytes"],
					},
					sort_keys=True,
				),
			}
		)
		job.insert(ignore_permissions=True)
		_enqueue_prune_job_execution(job.name, job.queue_name)
		queued_jobs.append(
			{
				"job_id": job.name,
				"file_id": candidate["file_id"],
				"drive_file_id": candidate["drive_file_id"],
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


def run_prune_job(*, drive_processing_job_id: str) -> dict[str, Any]:
	job_doc = frappe.get_doc("Drive Processing Job", drive_processing_job_id)
	payload = _load_job_payload(job_doc)
	job_doc.status = "running"
	job_doc.started_on = now_datetime()
	job_doc.error_log = None
	job_doc.save(ignore_permissions=True)

	try:
		file_doc = _load_file_doc(job_doc.file)
		drive_file_doc = _load_drive_file_doc(getattr(job_doc, "drive_file", None))
		evaluation = _attempt_local_prune(
			file_doc=file_doc,
			drive_file_doc=drive_file_doc,
			source_path=str(payload.get("source_path") or "").strip(),
			storage_backend=str(payload.get("storage_backend") or "").strip()
			or getattr(drive_file_doc, "storage_backend", None),
			destination_object_key=str(payload.get("destination_object_key") or "").strip()
			or getattr(drive_file_doc, "storage_object_key", None),
			expected_size_bytes=payload.get("verified_remote_size_bytes"),
		)
		result = {
			"file_url": getattr(file_doc, "file_url", None),
			"source_path": evaluation.get("source_path"),
			"cleanup_performed": bool(evaluation.get("cleanup_performed")),
			"cleanup_blocked_reason": evaluation.get("cleanup_blocked_reason"),
			"deleted_bytes": evaluation.get("deleted_bytes"),
			"destination_object_key": evaluation.get("destination_object_key"),
			"storage_backend": evaluation.get("storage_backend"),
			"remote_size_bytes": evaluation.get("remote_size_bytes"),
		}
		job_doc.result_json = json.dumps(result, sort_keys=True)
		job_doc.status = "completed" if result["cleanup_performed"] else "blocked"
		job_doc.finished_on = now_datetime()
		job_doc.save(ignore_permissions=True)
		return result
	except Exception as exc:
		_mark_job_failed(job_doc, exc)
		raise


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
			"source_sha256": _sha256_hexdigest(content),
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
			drive_file_doc = None
			result["drive_file_updated"] = False

		if result["cleanup_eligible"]:
			prune_result = _attempt_local_prune(
				file_doc=file_doc,
				drive_file_doc=drive_file_doc,
				source_path=source_path,
				storage_backend=storage_artifact.get("storage_backend"),
				destination_object_key=storage_artifact.get("object_key"),
				expected_size_bytes=len(content),
			)
			result["cleanup_performed"] = bool(prune_result.get("cleanup_performed"))
			result["cleanup_blocked_reason"] = prune_result.get("cleanup_blocked_reason")
		else:
			result["cleanup_performed"] = False

		job_doc.result_json = json.dumps(result, sort_keys=True)
		job_doc.status = "completed"
		job_doc.finished_on = now_datetime()
		job_doc.save(ignore_permissions=True)
		return result
	except Exception as exc:
		_mark_job_failed(job_doc, exc)
		raise
