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
_MACH_O_SIGNATURES = (
	b"\xfe\xed\xfa\xce",
	b"\xce\xfa\xed\xfe",
	b"\xfe\xed\xfa\xcf",
	b"\xcf\xfa\xed\xfe",
	b"\xca\xfe\xba\xbe",
	b"\xbe\xba\xfe\xca",
)
_HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx"}
_HEIF_BRANDS = {b"mif1", b"msf1"}
_AVIF_BRANDS = {b"avif", b"avis"}


def inspect_uploaded_bytes(*, storage, upload_session_doc) -> str:
	head = storage.read_temporary_object_head(
		object_key=upload_session_doc.tmp_object_key,
		max_bytes=_HEAD_BYTES,
	)
	if not head:
		frappe.throw(_("Uploaded object is empty or unreadable."))

	detected = _normalize_mime_type(_detect_mime_from_bytes(head))
	if not detected:
		frappe.throw(_("Uploaded content type could not be determined for governed file validation."))
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
		magic = _load_magic_module()
		return _detect_mime_with_magic(content, magic)
	except (ImportError, OSError):
		detected = _detect_mime_from_signatures(content)
		if detected:
			return detected
		raise RuntimeError(
			"Unable to validate uploaded content type: install python-magic with libmagic, "
			"or upload a file type supported by signature-based validation."
		)


def _load_magic_module():
	import magic

	return magic


def _detect_mime_with_magic(content: bytes, magic_module) -> str:
	if hasattr(magic_module, "from_buffer"):
		return str(magic_module.from_buffer(content, mime=True) or "").strip()

	detector = magic_module.Magic(mime=True)
	return str(detector.from_buffer(content) or "").strip()


def _detect_mime_from_signatures(content: bytes) -> str:
	data = bytes(content or b"")
	if not data:
		return ""

	if data.startswith(b"%PDF-"):
		return "application/pdf"
	if data.startswith(b"\xff\xd8\xff"):
		return "image/jpeg"
	if data.startswith(b"\x89PNG\r\n\x1a\n"):
		return "image/png"
	if data.startswith((b"GIF87a", b"GIF89a")):
		return "image/gif"
	if data.startswith(b"BM"):
		return "image/bmp"
	if data.startswith((b"II*\x00", b"MM\x00*")):
		return "image/tiff"
	if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
		return "image/webp"
	if len(data) >= 12 and data[4:8] == b"ftyp":
		brand = data[8:12]
		if brand in _HEIC_BRANDS:
			return "image/heic"
		if brand in _HEIF_BRANDS:
			return "image/heif"
		if brand in _AVIF_BRANDS:
			return "image/avif"

	if data.startswith(b"MZ"):
		return "application/x-dosexec"
	if data.startswith(b"\x7fELF"):
		return "application/x-elf"
	if data.startswith(_MACH_O_SIGNATURES):
		return "application/x-mach-binary"

	text_prefix = data[:256].lstrip().lower()
	if text_prefix.startswith(b"#!"):
		return "text/x-shellscript"
	if text_prefix.startswith(b"<?php") or b"<?php" in text_prefix[:128]:
		return "text/x-php"
	if (
		text_prefix.startswith((b"<!doctype html", b"<html", b"<script"))
		or b"<html" in text_prefix[:128]
		or b"<script" in text_prefix[:128]
	):
		return "text/html"

	return ""


def _normalize_mime_type(value: Any) -> str:
	mime_type = str(value or "").strip().lower()
	return _MIME_ALIASES.get(mime_type, mime_type)
