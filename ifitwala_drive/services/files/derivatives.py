from __future__ import annotations

import io
import json
from typing import Any

import frappe
from frappe.utils import now_datetime

from ifitwala_drive.services.storage.base import build_object_key, get_storage_backend

DEFAULT_PREVIEW_DERIVATIVE_ROLE = "viewer_preview"
_IMAGE_PREVIEW_ROLES = ("thumb", "viewer_preview")
_PREVIEW_JOB_STATUSES = ("queued", "running")
_IMAGE_RENDER_ORDER = ("viewer_preview", "thumb")
_SUPPORTED_IMAGE_PREVIEW_MIME_TYPES = {
	"image/jpeg",
	"image/jpg",
	"image/png",
	"image/webp",
}
_IMAGE_DERIVATIVE_SPECS = {
	"thumb": {
		"max_width": 160,
		"quality": 75,
		"output_format": "WEBP",
		"mime_type": "image/webp",
	},
	"viewer_preview": {
		"max_width": 960,
		"quality": 80,
		"output_format": "WEBP",
		"mime_type": "image/webp",
	},
}
_ERROR_CODE_UNSUPPORTED = "unsupported_mime_type"
_ERROR_CODE_GENERATION_FAILED = "preview_generation_failed"
_ERROR_CODE_RUNTIME_MISSING = "preview_runtime_missing"
_ERROR_CODE_SOURCE_READ_FAILED = "source_read_failed"


def resolve_ready_preview_derivative(
	*,
	drive_file_doc,
	derivative_role: str = DEFAULT_PREVIEW_DERIVATIVE_ROLE,
) -> dict[str, Any] | None:
	current_version = str(getattr(drive_file_doc, "current_version", "") or "").strip()
	if not current_version:
		return None

	derivative_id = frappe.db.exists(
		"Drive File Derivative",
		{
			"drive_file": drive_file_doc.name,
			"drive_file_version": current_version,
			"derivative_role": derivative_role,
			"status": "ready",
		},
	)
	if not derivative_id:
		return None

	derivative_doc = frappe.get_doc("Drive File Derivative", derivative_id)
	return {
		"name": derivative_doc.name,
		"derivative_role": getattr(derivative_doc, "derivative_role", None),
		"status": getattr(derivative_doc, "status", None),
		"storage_backend": getattr(derivative_doc, "storage_backend", None)
		or getattr(drive_file_doc, "storage_backend", None),
		"storage_object_key": getattr(derivative_doc, "storage_object_key", None),
		"mime_type": getattr(derivative_doc, "mime_type", None),
	}


def preview_plan_for_mime_type(mime_type: str | None) -> dict[str, Any]:
	normalized = str(mime_type or "").strip().lower()
	if normalized in _SUPPORTED_IMAGE_PREVIEW_MIME_TYPES:
		return {
			"supported": True,
			"preview_status": "pending",
			"derivative_roles": list(_IMAGE_PREVIEW_ROLES),
			"queue_name": "drive_default",
		}

	return {
		"supported": False,
		"preview_status": "not_applicable",
		"derivative_roles": [],
		"queue_name": None,
	}


def _enqueue_preview_job_execution(job_name: str, queue_name: str) -> None:
	enqueue = getattr(frappe, "enqueue", None)
	if not callable(enqueue):
		return

	enqueue(
		"ifitwala_drive.services.files.derivatives.run_preview_job",
		queue=queue_name,
		job_id=f"drive-preview:{job_name}",
		drive_processing_job_id=job_name,
	)


def _ensure_derivative_row(
	*,
	drive_file_id: str,
	drive_file_version_id: str,
	derivative_role: str,
	source_hash: str | None = None,
) -> str:
	filters = {
		"drive_file": drive_file_id,
		"drive_file_version": drive_file_version_id,
		"derivative_role": derivative_role,
	}
	existing = frappe.db.exists("Drive File Derivative", filters)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Drive File Derivative",
			"drive_file": drive_file_id,
			"drive_file_version": drive_file_version_id,
			"derivative_role": derivative_role,
			"status": "pending",
			"source_hash": source_hash,
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except Exception as exc:
		duplicate_error = getattr(frappe, "DuplicateEntryError", None)
		if duplicate_error is None or not isinstance(exc, duplicate_error):
			raise
		existing = frappe.db.exists("Drive File Derivative", filters)
		if existing:
			return existing
		raise
	return doc.name


def _ensure_preview_job(
	*,
	drive_file_doc,
	mime_type: str | None,
	derivative_roles: list[str],
	queue_name: str,
) -> str:
	file_id = str(getattr(drive_file_doc, "file", "") or "").strip()
	drive_file_id = str(getattr(drive_file_doc, "name", "") or "").strip()
	for status in _PREVIEW_JOB_STATUSES:
		existing = frappe.db.exists(
			"Drive Processing Job",
			{
				"job_type": "preview",
				"drive_file": drive_file_id,
				"file": file_id,
				"status": status,
			},
		)
		if existing:
			return existing

	job = frappe.get_doc(
		{
			"doctype": "Drive Processing Job",
			"job_type": "preview",
			"status": "queued",
			"queue_name": queue_name,
			"priority": "normal",
			"drive_file": drive_file_id,
			"file": file_id,
			"payload_json": json.dumps(
				{
					"drive_file_version": getattr(drive_file_doc, "current_version", None),
					"mime_type": mime_type,
					"derivative_roles": derivative_roles,
				},
				sort_keys=True,
			),
		}
	)
	job.insert(ignore_permissions=True)
	_enqueue_preview_job_execution(job.name, queue_name)
	return job.name


def _load_job_payload(job_doc) -> dict[str, Any]:
	try:
		payload = json.loads(getattr(job_doc, "payload_json", None) or "{}")
	except Exception:
		return {}
	return payload if isinstance(payload, dict) else {}


def _sanitize_error_message(exc: Exception) -> str:
	message = " ".join(str(exc or "").split())
	if not message:
		message = exc.__class__.__name__
	return message[:240]


def _mark_job_failed(job_doc, exc: Exception) -> None:
	job_doc.status = "failed"
	job_doc.error_log = _sanitize_error_message(exc)
	job_doc.finished_on = now_datetime()
	job_doc.save(ignore_permissions=True)


def _load_pillow_image_backend():
	try:
		from PIL import Image, ImageOps, UnidentifiedImageError
	except ImportError as exc:
		raise RuntimeError("Drive preview generation requires Pillow for image derivatives.") from exc
	return Image, ImageOps, UnidentifiedImageError


def _render_image_derivative(*, source_content: bytes, derivative_role: str) -> dict[str, Any]:
	spec = _IMAGE_DERIVATIVE_SPECS.get(derivative_role)
	if not spec:
		raise RuntimeError(f"Unsupported image derivative role: {derivative_role}")

	Image, ImageOps, UnidentifiedImageError = _load_pillow_image_backend()
	try:
		with Image.open(io.BytesIO(source_content)) as img:
			img = ImageOps.exif_transpose(img)
			max_width = int(spec["max_width"])
			if img.width > max_width:
				img.thumbnail((max_width, max_width))

			target_mode = "RGBA" if "A" in getattr(img, "getbands", lambda: ())() else "RGB"
			if getattr(img, "mode", None) != target_mode:
				img = img.convert(target_mode)

			buffer = io.BytesIO()
			img.save(
				buffer,
				spec["output_format"],
				optimize=True,
				quality=int(spec["quality"]),
			)
			content = buffer.getvalue()
			return {
				"content": content,
				"mime_type": spec["mime_type"],
				"width": int(getattr(img, "width", 0) or 0) or None,
				"height": int(getattr(img, "height", 0) or 0) or None,
				"size_bytes": len(content),
			}
	except UnidentifiedImageError as exc:
		raise RuntimeError("Drive preview generation could not decode image content.") from exc


def _derivative_sort_key(role: str) -> tuple[int, str]:
	if role in _IMAGE_RENDER_ORDER:
		return (_IMAGE_RENDER_ORDER.index(role), role)
	return (len(_IMAGE_RENDER_ORDER), role)


def _ordered_derivative_roles(derivative_roles: list[str]) -> list[str]:
	normalized_roles: list[str] = []
	for role in derivative_roles:
		candidate = str(role or "").strip()
		if not candidate or candidate in normalized_roles:
			continue
		normalized_roles.append(candidate)
	return sorted(normalized_roles, key=_derivative_sort_key)


def _resolve_derivative_doc(
	*,
	drive_file_id: str,
	drive_file_version_id: str,
	derivative_role: str,
	source_hash: str | None = None,
):
	derivative_id = _ensure_derivative_row(
		drive_file_id=drive_file_id,
		drive_file_version_id=drive_file_version_id,
		derivative_role=derivative_role,
		source_hash=source_hash,
	)
	return frappe.get_doc("Drive File Derivative", derivative_id)


def _build_derivative_object_key(
	*,
	storage,
	drive_file_id: str,
	drive_file_version_id: str,
	derivative_role: str,
) -> str:
	base_prefix = getattr(getattr(storage, "profile", None), "base_prefix", None)
	return build_object_key(
		"derivatives",
		drive_file_id,
		drive_file_version_id,
		f"{derivative_role}.webp",
		base_prefix=base_prefix,
	)


def _set_derivative_ready(
	*,
	derivative_doc,
	storage_artifact: dict[str, Any],
	rendered: dict[str, Any],
	source_hash: str | None,
) -> None:
	derivative_doc.status = "ready"
	derivative_doc.storage_backend = storage_artifact.get("storage_backend")
	derivative_doc.storage_object_key = storage_artifact.get("object_key")
	derivative_doc.mime_type = rendered.get("mime_type")
	derivative_doc.size_bytes = rendered.get("size_bytes")
	derivative_doc.width = rendered.get("width")
	derivative_doc.height = rendered.get("height")
	derivative_doc.page_count = None
	derivative_doc.generated_on = now_datetime()
	derivative_doc.source_hash = source_hash
	derivative_doc.error_code = None
	derivative_doc.error_message_sanitized = None
	derivative_doc.save(ignore_permissions=True)


def _mark_derivative_failed(
	*, derivative_doc, error_code: str, exc: Exception, source_hash: str | None
) -> None:
	derivative_doc.status = "failed"
	derivative_doc.source_hash = source_hash
	derivative_doc.error_code = error_code
	derivative_doc.error_message_sanitized = _sanitize_error_message(exc)
	derivative_doc.save(ignore_permissions=True)


def _mark_derivative_unsupported(*, derivative_doc, source_hash: str | None, message: str) -> None:
	derivative_doc.status = "unsupported"
	derivative_doc.source_hash = source_hash
	derivative_doc.error_code = _ERROR_CODE_UNSUPPORTED
	derivative_doc.error_message_sanitized = message[:240]
	derivative_doc.save(ignore_permissions=True)


def mark_version_derivatives_stale(*, drive_file_id: str, drive_file_version_id: str | None) -> int:
	version_id = str(drive_file_version_id or "").strip()
	if not version_id:
		return 0

	get_all = getattr(frappe, "get_all", None)
	if not callable(get_all):
		return 0

	stale_count = 0
	for row in get_all(
		"Drive File Derivative",
		filters={"drive_file": drive_file_id, "drive_file_version": version_id},
		fields=["name", "status"],
	):
		derivative_id = str(row.get("name") or "").strip()
		if not derivative_id or row.get("status") == "stale":
			continue
		doc = frappe.get_doc("Drive File Derivative", derivative_id)
		doc.status = "stale"
		doc.save(ignore_permissions=True)
		stale_count += 1
	return stale_count


def run_preview_job(*, drive_processing_job_id: str) -> dict[str, Any]:
	job_doc = frappe.get_doc("Drive Processing Job", drive_processing_job_id)
	payload = _load_job_payload(job_doc)
	job_doc.status = "running"
	job_doc.started_on = now_datetime()
	job_doc.error_log = None
	job_doc.save(ignore_permissions=True)

	drive_file_doc = None
	drive_file_version_id = None
	derivative_roles = _ordered_derivative_roles(payload.get("derivative_roles") or [])
	if not derivative_roles:
		derivative_roles = list(_IMAGE_PREVIEW_ROLES)
	source_hash = None

	try:
		drive_file_doc = frappe.get_doc("Drive File", job_doc.drive_file)
		drive_file_version_id = (
			str(payload.get("drive_file_version") or "").strip()
			or str(getattr(drive_file_doc, "current_version", "") or "").strip()
		)
		current_version_id = str(getattr(drive_file_doc, "current_version", "") or "").strip()
		if drive_file_version_id and current_version_id and drive_file_version_id != current_version_id:
			result = {
				"status": "blocked",
				"reason": "stale_version",
				"requested_version": drive_file_version_id,
				"current_version": current_version_id,
			}
			job_doc.result_json = json.dumps(result, sort_keys=True)
			job_doc.status = "blocked"
			job_doc.finished_on = now_datetime()
			job_doc.save(ignore_permissions=True)
			return result

		drive_file_version_doc = frappe.get_doc("Drive File Version", current_version_id)
		mime_type = (
			str(getattr(drive_file_version_doc, "mime_type", None) or payload.get("mime_type") or "")
			.strip()
			.lower()
			or None
		)
		plan = preview_plan_for_mime_type(mime_type)
		source_hash = (
			str(getattr(drive_file_version_doc, "content_hash", "") or "").strip()
			or str(getattr(drive_file_doc, "content_hash", "") or "").strip()
			or None
		)

		if not plan["supported"]:
			for derivative_role in derivative_roles:
				derivative_doc = _resolve_derivative_doc(
					drive_file_id=drive_file_doc.name,
					drive_file_version_id=current_version_id,
					derivative_role=derivative_role,
					source_hash=source_hash,
				)
				_mark_derivative_unsupported(
					derivative_doc=derivative_doc,
					source_hash=source_hash,
					message=f"Preview generation is not supported for MIME type {mime_type or 'unknown'}.",
				)
			drive_file_doc.preview_status = "not_applicable"
			drive_file_doc.save(ignore_permissions=True)
			result = {
				"status": "completed",
				"preview_status": drive_file_doc.preview_status,
				"mime_type": mime_type,
				"ready_roles": [],
				"failed_roles": [],
				"unsupported_roles": derivative_roles,
			}
			job_doc.result_json = json.dumps(result, sort_keys=True)
			job_doc.status = "completed"
			job_doc.finished_on = now_datetime()
			job_doc.save(ignore_permissions=True)
			return result

		storage = get_storage_backend(getattr(drive_file_doc, "storage_backend", None))
		source_object_key = str(
			getattr(drive_file_version_doc, "storage_object_key", None)
			or getattr(drive_file_doc, "storage_object_key", None)
			or ""
		).strip()
		source_content = storage.read_final_object(object_key=source_object_key)

		ready_roles: list[str] = []
		failed_roles: list[dict[str, str]] = []
		artifacts: list[dict[str, Any]] = []
		for derivative_role in derivative_roles:
			derivative_doc = _resolve_derivative_doc(
				drive_file_id=drive_file_doc.name,
				drive_file_version_id=current_version_id,
				derivative_role=derivative_role,
				source_hash=source_hash,
			)
			derivative_doc.status = "processing"
			derivative_doc.error_code = None
			derivative_doc.error_message_sanitized = None
			derivative_doc.save(ignore_permissions=True)

			try:
				rendered = _render_image_derivative(
					source_content=source_content,
					derivative_role=derivative_role,
				)
				storage_artifact = storage.write_final_object(
					object_key=_build_derivative_object_key(
						storage=storage,
						drive_file_id=drive_file_doc.name,
						drive_file_version_id=current_version_id,
						derivative_role=derivative_role,
					),
					content=rendered["content"],
					mime_type=rendered["mime_type"],
				)
				_set_derivative_ready(
					derivative_doc=derivative_doc,
					storage_artifact=storage_artifact,
					rendered=rendered,
					source_hash=source_hash,
				)
				ready_roles.append(derivative_role)
				artifacts.append(
					{
						"derivative_role": derivative_role,
						"storage_backend": storage_artifact.get("storage_backend"),
						"storage_object_key": storage_artifact.get("object_key"),
						"mime_type": rendered.get("mime_type"),
						"width": rendered.get("width"),
						"height": rendered.get("height"),
						"size_bytes": rendered.get("size_bytes"),
					}
				)
			except Exception as exc:
				error_code = _ERROR_CODE_RUNTIME_MISSING
				if "Pillow" not in _sanitize_error_message(exc):
					error_code = _ERROR_CODE_GENERATION_FAILED
				_mark_derivative_failed(
					derivative_doc=derivative_doc,
					error_code=error_code,
					exc=exc,
					source_hash=source_hash,
				)
				failed_roles.append(
					{
						"derivative_role": derivative_role,
						"error_code": error_code,
						"error_message": _sanitize_error_message(exc),
					}
				)

		drive_file_doc.preview_status = (
			"ready" if DEFAULT_PREVIEW_DERIVATIVE_ROLE in ready_roles else "failed"
		)
		drive_file_doc.save(ignore_permissions=True)

		result = {
			"status": "completed" if DEFAULT_PREVIEW_DERIVATIVE_ROLE in ready_roles else "failed",
			"preview_status": drive_file_doc.preview_status,
			"mime_type": mime_type,
			"ready_roles": ready_roles,
			"failed_roles": failed_roles,
			"artifacts": artifacts,
		}
		job_doc.result_json = json.dumps(result, sort_keys=True)
		job_doc.status = "completed" if DEFAULT_PREVIEW_DERIVATIVE_ROLE in ready_roles else "failed"
		job_doc.finished_on = now_datetime()
		job_doc.error_log = (
			None
			if job_doc.status == "completed"
			else "Preview generation did not produce a ready viewer derivative."
		)
		job_doc.save(ignore_permissions=True)
		return result
	except Exception as exc:
		if drive_file_doc and drive_file_version_id:
			for derivative_role in derivative_roles:
				derivative_doc = _resolve_derivative_doc(
					drive_file_id=drive_file_doc.name,
					drive_file_version_id=drive_file_version_id,
					derivative_role=derivative_role,
					source_hash=source_hash,
				)
				if getattr(derivative_doc, "status", None) != "ready":
					_mark_derivative_failed(
						derivative_doc=derivative_doc,
						error_code=_ERROR_CODE_SOURCE_READ_FAILED,
						exc=exc,
						source_hash=source_hash,
					)
			drive_file_doc.preview_status = "failed"
			drive_file_doc.save(ignore_permissions=True)
		_mark_job_failed(job_doc, exc)
		raise


def sync_preview_pipeline_for_current_version(
	*,
	drive_file_doc,
	mime_type: str | None,
) -> dict[str, Any]:
	plan = preview_plan_for_mime_type(mime_type)
	drive_file_doc.preview_status = plan["preview_status"]
	if not plan["supported"]:
		return {
			"preview_status": drive_file_doc.preview_status,
			"derivative_ids": [],
			"drive_processing_job_id": None,
		}

	drive_file_id = str(getattr(drive_file_doc, "name", "") or "").strip()
	drive_file_version_id = str(getattr(drive_file_doc, "current_version", "") or "").strip()
	source_hash = str(getattr(drive_file_doc, "content_hash", "") or "").strip() or None
	derivative_ids = [
		_ensure_derivative_row(
			drive_file_id=drive_file_id,
			drive_file_version_id=drive_file_version_id,
			derivative_role=role,
			source_hash=source_hash,
		)
		for role in plan["derivative_roles"]
	]
	job_id = _ensure_preview_job(
		drive_file_doc=drive_file_doc,
		mime_type=mime_type,
		derivative_roles=plan["derivative_roles"],
		queue_name=plan["queue_name"],
	)
	return {
		"preview_status": drive_file_doc.preview_status,
		"derivative_ids": derivative_ids,
		"drive_processing_job_id": job_id,
	}
