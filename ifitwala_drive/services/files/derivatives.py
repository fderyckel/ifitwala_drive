from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timedelta
from typing import Any

import frappe
from frappe.utils import now_datetime

from ifitwala_drive.services.queueing import resolve_enqueue_queue
from ifitwala_drive.services.storage.base import build_object_key, get_storage_backend

DEFAULT_PREVIEW_DERIVATIVE_ROLE = "viewer_preview"
PDF_CARD_DERIVATIVE_ROLE = "pdf_card"
DEFAULT_PDF_PREVIEW_DERIVATIVE_ROLE = "pdf_page_1"
_IMAGE_PREVIEW_ROLES = ("thumb", "viewer_preview")
_PDF_PREVIEW_ROLES = (PDF_CARD_DERIVATIVE_ROLE, DEFAULT_PDF_PREVIEW_DERIVATIVE_ROLE)
_PREVIEW_JOB_STATUSES = ("queued", "running")
_DERIVATIVE_RENDER_ORDER = ("viewer_preview", "card", PDF_CARD_DERIVATIVE_ROLE, "pdf_page_1", "thumb")
_SUPPORTED_IMAGE_PREVIEW_MIME_TYPES = {
	"image/jpeg",
	"image/jpg",
	"image/png",
	"image/webp",
}
_SUPPORTED_PDF_PREVIEW_MIME_TYPES = {"application/pdf"}
_IMAGE_DERIVATIVE_SPECS = {
	"thumb": {
		"max_width": 400,
		"quality": 78,
		"output_format": "WEBP",
		"mime_type": "image/webp",
	},
	"viewer_preview": {
		"max_width": 960,
		"quality": 80,
		"output_format": "WEBP",
		"mime_type": "image/webp",
	},
	"card": {
		"max_width": 400,
		"quality": 78,
		"output_format": "WEBP",
		"mime_type": "image/webp",
	},
}
_PDF_DERIVATIVE_SPECS = {
	"pdf_card": {
		"max_width": 560,
		"output_format": "jpeg",
		"mime_type": "image/jpeg",
		"file_extension": "jpg",
		"jpg_quality": 70,
	},
	"pdf_page_1": {
		"max_width": 960,
		"output_format": "jpeg",
		"mime_type": "image/jpeg",
		"file_extension": "jpg",
		"jpg_quality": 82,
	},
}
_ERROR_CODE_UNSUPPORTED = "unsupported_mime_type"
_ERROR_CODE_GENERATION_FAILED = "preview_generation_failed"
_ERROR_CODE_RUNTIME_MISSING = "preview_runtime_missing"
_ERROR_CODE_SOURCE_READ_FAILED = "source_read_failed"
_STALE_DERIVATIVE_GRACE_DAYS = 30
_FAILED_RECONCILIATION_ERROR_CODES = {
	_ERROR_CODE_UNSUPPORTED,
	_ERROR_CODE_RUNTIME_MISSING,
}


def _get_all(doctype: str, *, filters: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
	get_all = getattr(frappe, "get_all", None)
	if callable(get_all):
		return get_all(doctype, filters=filters, fields=fields)

	db_get_all = getattr(getattr(frappe, "db", None), "get_all", None)
	if callable(db_get_all):
		return db_get_all(doctype, filters=filters, fields=fields)

	return []


def _coerce_datetime(value) -> datetime | None:
	if value is None:
		return None
	if isinstance(value, datetime):
		return value

	try:
		from frappe.utils import get_datetime
	except ImportError:
		get_datetime = None

	if callable(get_datetime):
		try:
			return get_datetime(value)
		except Exception:
			pass

	text = str(value or "").strip()
	if not text:
		return None
	try:
		return datetime.fromisoformat(text)
	except ValueError:
		return None


def _delete_derivative_doc(derivative_id: str) -> None:
	delete_doc = getattr(frappe, "delete_doc", None)
	if callable(delete_doc):
		delete_doc("Drive File Derivative", derivative_id, ignore_permissions=True)
		return

	derivative_doc = frappe.get_doc("Drive File Derivative", derivative_id)
	delete_method = getattr(derivative_doc, "delete", None)
	if callable(delete_method):
		delete_method(ignore_permissions=True)
		return

	# Fallback for constrained runtimes: clear delivery metadata so the row cannot be reused.
	derivative_doc.status = "stale"
	derivative_doc.storage_backend = None
	derivative_doc.storage_object_key = None
	derivative_doc.save(ignore_permissions=True)


def delete_derivative_artifacts_for_drive_file(*, drive_file_id: str) -> int:
	deleted_count = 0
	for row in _get_all(
		"Drive File Derivative",
		filters={"drive_file": drive_file_id},
		fields=["name", "storage_backend", "storage_object_key"],
	):
		derivative_id = str(row.get("name") or "").strip()
		if not derivative_id:
			continue

		storage_object_key = str(row.get("storage_object_key") or "").strip()
		if storage_object_key:
			storage_backend = row.get("storage_backend")
			storage = get_storage_backend(storage_backend)
			storage.delete_object(object_key=storage_object_key)

		_delete_derivative_doc(derivative_id)
		deleted_count += 1

	return deleted_count


def prune_stale_derivatives_service(
	*, grace_days: int = _STALE_DERIVATIVE_GRACE_DAYS, limit: int | None = None
) -> dict[str, Any]:
	if int(grace_days or 0) <= 0:
		raise ValueError("grace_days must be a positive integer.")

	remaining = int(limit or 0) if limit is not None else None
	cutoff = now_datetime() - timedelta(days=int(grace_days))
	pruned_count = 0

	for row in _get_all(
		"Drive File Derivative",
		filters={"status": "stale"},
		fields=["name", "storage_backend", "storage_object_key", "modified"],
	):
		if remaining is not None and remaining <= 0:
			break

		modified_on = _coerce_datetime(row.get("modified"))
		if not modified_on or modified_on > cutoff:
			continue

		derivative_id = str(row.get("name") or "").strip()
		if not derivative_id:
			continue

		storage_object_key = str(row.get("storage_object_key") or "").strip()
		if storage_object_key:
			storage = get_storage_backend(row.get("storage_backend"))
			storage.delete_object(object_key=storage_object_key)

		_delete_derivative_doc(derivative_id)
		pruned_count += 1
		if remaining is not None:
			remaining -= 1

	return {
		"status": "completed",
		"grace_days": int(grace_days),
		"pruned_count": pruned_count,
		"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
	}


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


def _derivative_spec_signature(derivative_role: str) -> str:
	spec = _IMAGE_DERIVATIVE_SPECS.get(derivative_role) or _PDF_DERIVATIVE_SPECS.get(derivative_role)
	if not spec:
		return derivative_role

	parts = [f"{key}={spec[key]}" for key in sorted(spec)]
	return f"{derivative_role}|{'|'.join(parts)}"


def _build_derivative_source_hash(*, content_hash: str | None, derivative_role: str) -> str | None:
	resolved_content_hash = str(content_hash or "").strip()
	if not resolved_content_hash:
		return None

	raw_value = f"{resolved_content_hash}|{_derivative_spec_signature(derivative_role)}"
	return f"sha256:{hashlib.sha256(raw_value.encode('utf-8')).hexdigest()}"


def preview_plan_for_mime_type(mime_type: str | None) -> dict[str, Any]:
	normalized = str(mime_type or "").strip().lower()
	if normalized in _SUPPORTED_IMAGE_PREVIEW_MIME_TYPES:
		return {
			"supported": True,
			"preview_status": "pending",
			"derivative_roles": list(_IMAGE_PREVIEW_ROLES),
			"primary_derivative_role": DEFAULT_PREVIEW_DERIVATIVE_ROLE,
			"queue_name": "drive_default",
		}

	if normalized in _SUPPORTED_PDF_PREVIEW_MIME_TYPES:
		return {
			"supported": True,
			"preview_status": "pending",
			"derivative_roles": list(_PDF_PREVIEW_ROLES),
			"primary_derivative_role": DEFAULT_PDF_PREVIEW_DERIVATIVE_ROLE,
			"queue_name": "drive_default",
		}

	return {
		"supported": False,
		"preview_status": "not_applicable",
		"derivative_roles": [],
		"primary_derivative_role": None,
		"queue_name": None,
	}


def primary_preview_derivative_role_for_mime_type(mime_type: str | None) -> str:
	return str(
		preview_plan_for_mime_type(mime_type).get("primary_derivative_role")
		or DEFAULT_PREVIEW_DERIVATIVE_ROLE
	)


def _is_profile_image_drive_file(drive_file_doc) -> bool:
	return str(getattr(drive_file_doc, "slot", "") or "").strip() == "profile_image"


def preview_plan_for_drive_file(drive_file_doc, mime_type: str | None) -> dict[str, Any]:
	plan = dict(preview_plan_for_mime_type(mime_type))
	if not plan["supported"]:
		return plan

	normalized_mime = str(mime_type or "").strip().lower()
	if normalized_mime in _SUPPORTED_IMAGE_PREVIEW_MIME_TYPES and _is_profile_image_drive_file(
		drive_file_doc
	):
		plan["derivative_roles"] = _ordered_derivative_roles([*(plan.get("derivative_roles") or []), "card"])
	return plan


def _enqueue_preview_job_execution(job_name: str, queue_name: str) -> None:
	enqueue = getattr(frappe, "enqueue", None)
	if not callable(enqueue):
		return

	enqueue(
		"ifitwala_drive.services.files.derivatives.run_preview_job",
		queue=resolve_enqueue_queue(queue_name),
		job_id=f"drive-preview:{job_name}",
		drive_processing_job_id=job_name,
	)


def _schedule_preview_job_execution(job_name: str, queue_name: str) -> None:
	after_commit = getattr(getattr(frappe, "db", None), "after_commit", None)
	add = getattr(after_commit, "add", None)
	if callable(add):
		add(lambda: _enqueue_preview_job_execution(job_name, queue_name))
		return
	_enqueue_preview_job_execution(job_name, queue_name)


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
	_schedule_preview_job_execution(job.name, queue_name)
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


def _load_pymupdf_backend():
	try:
		import pymupdf
	except ImportError:
		try:
			import fitz as pymupdf
		except ImportError as exc:
			raise RuntimeError("Drive preview generation requires PyMuPDF for PDF derivatives.") from exc
	return pymupdf


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
				"file_extension": "webp",
				"width": int(getattr(img, "width", 0) or 0) or None,
				"height": int(getattr(img, "height", 0) or 0) or None,
				"size_bytes": len(content),
				"page_count": None,
			}
	except UnidentifiedImageError as exc:
		raise RuntimeError("Drive preview generation could not decode image content.") from exc


def _render_pdf_derivative(*, source_content: bytes, derivative_role: str) -> dict[str, Any]:
	spec = _PDF_DERIVATIVE_SPECS.get(derivative_role)
	if not spec:
		raise RuntimeError(f"Unsupported PDF derivative role: {derivative_role}")

	pymupdf = _load_pymupdf_backend()
	with pymupdf.open(stream=source_content, filetype="pdf") as document:
		if document.page_count < 1:
			raise RuntimeError("Drive preview generation could not find a PDF page to render.")

		page = document.load_page(0)
		page_width = float(getattr(page.rect, "width", 0) or 0)
		scale = 1.0
		if page_width > 0:
			scale = min(2.0, float(spec["max_width"]) / page_width)
			if scale <= 0:
				scale = 1.0

		pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
		render_options: dict[str, Any] = {}
		if str(spec.get("output_format") or "").strip().lower() in {"jpg", "jpeg"}:
			render_options["jpg_quality"] = int(spec.get("jpg_quality") or 95)
		content = pixmap.tobytes(spec["output_format"], **render_options)
		return {
			"content": content,
			"mime_type": spec["mime_type"],
			"file_extension": spec["file_extension"],
			"width": int(getattr(pixmap, "width", 0) or 0) or None,
			"height": int(getattr(pixmap, "height", 0) or 0) or None,
			"size_bytes": len(content),
			"page_count": int(document.page_count or 0) or None,
		}


def _render_derivative(
	*,
	source_content: bytes,
	derivative_role: str,
	mime_type: str | None,
) -> dict[str, Any]:
	normalized_mime = str(mime_type or "").strip().lower()
	if derivative_role in _IMAGE_DERIVATIVE_SPECS:
		return _render_image_derivative(source_content=source_content, derivative_role=derivative_role)
	if derivative_role in _PDF_DERIVATIVE_SPECS or normalized_mime in _SUPPORTED_PDF_PREVIEW_MIME_TYPES:
		return _render_pdf_derivative(source_content=source_content, derivative_role=derivative_role)
	raise RuntimeError(
		f"Unsupported derivative role for MIME type {normalized_mime or 'unknown'}: {derivative_role}"
	)


def _derivative_sort_key(role: str) -> tuple[int, str]:
	if role in _DERIVATIVE_RENDER_ORDER:
		return (_DERIVATIVE_RENDER_ORDER.index(role), role)
	return (len(_DERIVATIVE_RENDER_ORDER), role)


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
	file_extension: str | None = None,
) -> str:
	base_prefix = getattr(getattr(storage, "profile", None), "base_prefix", None)
	normalized_extension = str(file_extension or "webp").strip().lstrip(".") or "webp"
	return build_object_key(
		"derivatives",
		drive_file_id,
		drive_file_version_id,
		f"{derivative_role}.{normalized_extension}",
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
	derivative_doc.page_count = rendered.get("page_count")
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

	stale_count = 0
	for row in _get_all(
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
		plan = preview_plan_for_drive_file(drive_file_doc, mime_type)
		primary_derivative_role = str(plan.get("primary_derivative_role") or DEFAULT_PREVIEW_DERIVATIVE_ROLE)
		source_hash = (
			str(getattr(drive_file_version_doc, "content_hash", "") or "").strip()
			or str(getattr(drive_file_doc, "content_hash", "") or "").strip()
			or None
		)

		if not plan["supported"]:
			for derivative_role in derivative_roles:
				derivative_source_hash = _build_derivative_source_hash(
					content_hash=source_hash,
					derivative_role=derivative_role,
				)
				derivative_doc = _resolve_derivative_doc(
					drive_file_id=drive_file_doc.name,
					drive_file_version_id=current_version_id,
					derivative_role=derivative_role,
					source_hash=derivative_source_hash,
				)
				_mark_derivative_unsupported(
					derivative_doc=derivative_doc,
					source_hash=derivative_source_hash,
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
			derivative_source_hash = _build_derivative_source_hash(
				content_hash=source_hash,
				derivative_role=derivative_role,
			)
			derivative_doc = _resolve_derivative_doc(
				drive_file_id=drive_file_doc.name,
				drive_file_version_id=current_version_id,
				derivative_role=derivative_role,
				source_hash=derivative_source_hash,
			)
			derivative_doc.status = "processing"
			derivative_doc.error_code = None
			derivative_doc.error_message_sanitized = None
			derivative_doc.save(ignore_permissions=True)

			try:
				rendered = _render_derivative(
					source_content=source_content,
					derivative_role=derivative_role,
					mime_type=mime_type,
				)
				storage_artifact = storage.write_final_object(
					object_key=_build_derivative_object_key(
						storage=storage,
						drive_file_id=drive_file_doc.name,
						drive_file_version_id=current_version_id,
						derivative_role=derivative_role,
						file_extension=rendered.get("file_extension"),
					),
					content=rendered["content"],
					mime_type=rendered["mime_type"],
				)
				_set_derivative_ready(
					derivative_doc=derivative_doc,
					storage_artifact=storage_artifact,
					rendered=rendered,
					source_hash=derivative_source_hash,
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
				if all(
					runtime_name not in _sanitize_error_message(exc) for runtime_name in ("Pillow", "PyMuPDF")
				):
					error_code = _ERROR_CODE_GENERATION_FAILED
				_mark_derivative_failed(
					derivative_doc=derivative_doc,
					error_code=error_code,
					exc=exc,
					source_hash=derivative_source_hash,
				)
				failed_roles.append(
					{
						"derivative_role": derivative_role,
						"error_code": error_code,
						"error_message": _sanitize_error_message(exc),
					}
				)

		drive_file_doc.preview_status = "ready" if primary_derivative_role in ready_roles else "failed"
		drive_file_doc.save(ignore_permissions=True)

		result = {
			"status": "completed" if primary_derivative_role in ready_roles else "failed",
			"preview_status": drive_file_doc.preview_status,
			"mime_type": mime_type,
			"ready_roles": ready_roles,
			"failed_roles": failed_roles,
			"artifacts": artifacts,
		}
		job_doc.result_json = json.dumps(result, sort_keys=True)
		job_doc.status = "completed" if primary_derivative_role in ready_roles else "failed"
		job_doc.finished_on = now_datetime()
		job_doc.error_log = (
			None
			if job_doc.status == "completed"
			else f"Preview generation did not produce a ready {primary_derivative_role} derivative."
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
	plan = preview_plan_for_drive_file(drive_file_doc, mime_type)
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
			source_hash=_build_derivative_source_hash(content_hash=source_hash, derivative_role=role),
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


def _preview_job_activity_timestamp(job_row: dict[str, Any]) -> datetime | None:
	for fieldname in ("finished_on", "started_on", "modified", "creation"):
		resolved = _coerce_datetime(job_row.get(fieldname))
		if resolved is not None:
			return resolved
	return None


def _preview_job_state_for_drive_file(*, drive_file_id: str, now: datetime, cooldown_minutes: int) -> str:
	cutoff = now - timedelta(minutes=max(int(cooldown_minutes or 0), 0))
	latest_activity: datetime | None = None
	latest_status = ""

	for row in _get_all(
		"Drive Processing Job",
		filters={"job_type": "preview", "drive_file": drive_file_id},
		fields=["name", "status", "finished_on", "started_on", "modified", "creation"],
	):
		status = str(row.get("status") or "").strip().lower()
		if status in _PREVIEW_JOB_STATUSES:
			return "active"
		activity_on = _preview_job_activity_timestamp(row)
		if activity_on is None:
			continue
		if latest_activity is None or activity_on > latest_activity:
			latest_activity = activity_on
			latest_status = status

	if latest_activity is not None and latest_activity >= cutoff:
		return "cooldown"
	if latest_status == "failed":
		return "failed"
	return "idle"


def _should_retry_failed_derivative(row: dict[str, Any]) -> bool:
	error_code = str(row.get("error_code") or "").strip()
	return error_code not in _FAILED_RECONCILIATION_ERROR_CODES


def reconcile_preview_derivatives_service(
	*,
	limit: int = 100,
	stalled_minutes: int = 20,
	cooldown_minutes: int = 60,
) -> dict[str, Any]:
	resolved_limit = max(int(limit or 0), 0)
	resolved_stalled_minutes = max(int(stalled_minutes or 0), 1)
	resolved_cooldown_minutes = max(int(cooldown_minutes or 0), 0)
	now = now_datetime()

	scanned = 0
	requeued = 0
	skipped_active = 0
	skipped_cooldown = 0
	skipped_terminal = 0
	reasons: dict[str, int] = {}

	for row in _get_all(
		"Drive File",
		filters={"status": "active"},
		fields=["name", "current_version", "preview_status", "content_hash"],
	):
		if resolved_limit and scanned >= resolved_limit:
			break

		drive_file_id = str(row.get("name") or "").strip()
		current_version = str(row.get("current_version") or "").strip()
		if not drive_file_id or not current_version:
			continue

		mime_type = frappe.db.get_value("Drive File Version", current_version, "mime_type")
		drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
		plan = preview_plan_for_drive_file(drive_file_doc, mime_type)
		if not plan["supported"]:
			continue

		derivative_rows = {
			str(candidate.get("derivative_role") or "").strip(): candidate
			for candidate in _get_all(
				"Drive File Derivative",
				filters={"drive_file": drive_file_id, "drive_file_version": current_version},
				fields=["name", "derivative_role", "status", "modified", "error_code", "source_hash"],
			)
		}
		expected_roles = [str(role or "").strip() for role in plan["derivative_roles"]]

		reconcile_reason = ""
		for derivative_role in expected_roles:
			derivative_row = derivative_rows.get(derivative_role)
			if not derivative_row:
				reconcile_reason = f"missing:{derivative_role}"
				break

			status = str(derivative_row.get("status") or "").strip().lower()
			modified_on = _coerce_datetime(derivative_row.get("modified"))
			is_stalled = modified_on is None or modified_on <= now - timedelta(
				minutes=resolved_stalled_minutes
			)
			if status in {"pending", "processing"} and is_stalled:
				reconcile_reason = f"stalled:{derivative_role}"
				break
			if status == "failed" and is_stalled and _should_retry_failed_derivative(derivative_row):
				reconcile_reason = f"retry_failed:{derivative_role}"
				break
			if status in {"unsupported"}:
				reconcile_reason = ""
				break

			expected_source_hash = _build_derivative_source_hash(
				content_hash=str(row.get("content_hash") or "").strip() or None,
				derivative_role=derivative_role,
			)
			resolved_source_hash = str(derivative_row.get("source_hash") or "").strip() or None
			if status == "ready" and expected_source_hash and resolved_source_hash != expected_source_hash:
				reconcile_reason = f"outdated:{derivative_role}"
				break

		if not reconcile_reason and str(row.get("preview_status") or "").strip().lower() == "pending":
			reconcile_reason = "missing_job"

		if not reconcile_reason:
			continue

		scanned += 1
		job_state = _preview_job_state_for_drive_file(
			drive_file_id=drive_file_id,
			now=now,
			cooldown_minutes=resolved_cooldown_minutes,
		)
		if job_state == "active":
			skipped_active += 1
			continue
		if job_state == "cooldown":
			skipped_cooldown += 1
			continue
		if job_state == "failed" and reconcile_reason.startswith("retry_failed:"):
			skipped_terminal += 1
			continue

		drive_file_doc = frappe.get_doc("Drive File", drive_file_id)
		sync_preview_pipeline_for_current_version(
			drive_file_doc=drive_file_doc,
			mime_type=mime_type,
		)
		drive_file_doc.save(ignore_permissions=True)
		requeued += 1
		reasons[reconcile_reason] = reasons.get(reconcile_reason, 0) + 1

	return {
		"status": "completed",
		"scanned": scanned,
		"requeued": requeued,
		"skipped_active": skipped_active,
		"skipped_cooldown": skipped_cooldown,
		"skipped_terminal": skipped_terminal,
		"reasons": reasons,
	}
