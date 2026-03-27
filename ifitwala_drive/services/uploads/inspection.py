from __future__ import annotations

from typing import Any

import frappe
from frappe import _

_HEAD_BYTES = 2048
_DANGEROUS_MIME_TYPES = {
	"application/javascript",
	"application/x-dosexec",
	"application/x-executable",
	"application/x-elf",
	"application/x-mach-binary",
	"application/x-msdos-program",
	"application/x-msdownload",
	"application/x-php",
	"application/x-shellscript",
	"text/html",
	"text/javascript",
	"text/x-php",
	"text/x-script",
	"text/x-shellscript",
}
_MIME_ALIASES = {
	"application/x-pdf": "application/pdf",
	"image/jpg": "image/jpeg",
}


def inspect_uploaded_bytes(*, storage, upload_session_doc) -> str:
	head = storage.read_temporary_object_head(
		object_key=upload_session_doc.tmp_object_key,
		max_bytes=_HEAD_BYTES,
	)
	if not head:
		frappe.throw(_("Uploaded object is empty or unreadable."))

	detected = _normalize_mime_type(_detect_mime_from_bytes(head))
	if detected in _DANGEROUS_MIME_TYPES:
		frappe.throw(_("Uploaded content type is not allowed for governed files: {0}").format(detected))

	mime_type_hint = _normalize_mime_type(getattr(upload_session_doc, "mime_type_hint", None))
	if mime_type_hint and detected and detected != mime_type_hint:
		frappe.throw(
			_(
				"Uploaded content type does not match the claimed MIME type: expected {0}, detected {1}."
			).format(
				mime_type_hint,
				detected,
			)
		)

	return detected


def _detect_mime_from_bytes(content: bytes) -> str:
	try:
		import magic
	except ImportError as exc:
		raise RuntimeError(
			"python-magic with libmagic is required for governed upload MIME validation."
		) from exc
	except OSError as exc:
		raise RuntimeError("libmagic is required for governed upload MIME validation.") from exc

	if hasattr(magic, "from_buffer"):
		return str(magic.from_buffer(content, mime=True) or "").strip()

	detector = magic.Magic(mime=True)
	return str(detector.from_buffer(content) or "").strip()


def _normalize_mime_type(value: Any) -> str:
	mime_type = str(value or "").strip().lower()
	return _MIME_ALIASES.get(mime_type, mime_type)
