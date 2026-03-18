from __future__ import annotations

from contextlib import nullcontext

import frappe

_LOCK_PREFIX = "ifitwala_drive"


def drive_lock(lock_key: str, *, timeout: int = 30):
	cache_factory = getattr(frappe, "cache", None)
	if not callable(cache_factory):
		return nullcontext()

	try:
		cache = cache_factory()
	except Exception:
		return nullcontext()

	if not cache or not hasattr(cache, "lock"):
		return nullcontext()

	return cache.lock(f"{_LOCK_PREFIX}:{lock_key}", timeout=timeout)
