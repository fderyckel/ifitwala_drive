from __future__ import annotations

import hashlib
import os
from typing import Any

from ifitwala_drive.services.storage.base import build_object_key, resolve_storage_runtime_profile


def build_upload_object_key(
	*,
	session_key: str,
	owner_doctype: str,
	owner_name: str,
	attached_doctype: str,
	attached_name: str,
	slot: str,
	filename: str,
) -> str:
	filename = (filename or "upload.bin").strip() or "upload.bin"
	_, extension = os.path.splitext(filename)
	seed = "|".join(
		[
			str(session_key or "").strip(),
			str(owner_doctype or "").strip(),
			str(owner_name or "").strip(),
			str(attached_doctype or "").strip(),
			str(attached_name or "").strip(),
			str(slot or "").strip(),
			filename,
		]
	)
	digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
	normalized_extension = extension.lower()[:16]
	profile = resolve_storage_runtime_profile()
	return build_object_key(
		"files",
		digest[:2],
		digest[2:4],
		f"{digest}{normalized_extension}",
		base_prefix=profile.base_prefix,
	)


def build_upload_session_key(payload: dict[str, Any], *, user: str | None = None) -> str:
	idempotency_key = str(payload.get("idempotency_key") or "").strip()
	if not idempotency_key:
		return _random_session_key()

	seed = "|".join(
		[
			str(user or "").strip(),
			str(payload.get("owner_doctype") or "").strip(),
			str(payload.get("owner_name") or "").strip(),
			str(payload.get("attached_doctype") or "").strip(),
			str(payload.get("attached_name") or "").strip(),
			str(payload.get("slot") or "").strip(),
			str(payload.get("filename_original") or "").strip(),
			idempotency_key,
		]
	)
	return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _random_session_key() -> str:
	import frappe

	return frappe.generate_hash(length=24)
