from __future__ import annotations

import hashlib
import re

_SYSTEM_KEY_MAX_LENGTH = 140
_COMPACT_PART_MAX_LENGTH = 16


def slugify_folder_title(value: str | None) -> str:
	value = (value or "").strip().lower()
	value = re.sub(r"[^a-z0-9]+", "-", value)
	value = re.sub(r"-{2,}", "-", value).strip("-")
	return value or "folder"


def _compact_part(value: str | None, *, max_length: int = _COMPACT_PART_MAX_LENGTH) -> str:
	value = (value or "").strip()
	if len(value) <= max_length:
		return value

	digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
	prefix_length = max_length - len(digest) - 1
	return f"{value[:prefix_length]}_{digest}"


def build_folder_system_key(
	*,
	title: str,
	parent_drive_folder: str | None,
	owner_doctype: str,
	owner_name: str,
	organization: str,
	school: str | None,
	folder_kind: str,
) -> str:
	title_slug = slugify_folder_title(title)
	parts = (
		organization,
		school or "no-school",
		owner_doctype,
		owner_name,
		parent_drive_folder or "root",
		folder_kind,
		title_slug,
	)
	system_key = "|".join(str(part or "").strip() for part in parts)
	if len(system_key) <= _SYSTEM_KEY_MAX_LENGTH:
		return system_key

	compact_parts = (
		_compact_part(organization),
		_compact_part(school or "no-school"),
		_compact_part(owner_doctype),
		_compact_part(owner_name),
		parent_drive_folder or "root",
		_compact_part(folder_kind),
		_compact_part(title_slug),
	)
	return "|".join(str(part or "").strip() for part in compact_parts)
