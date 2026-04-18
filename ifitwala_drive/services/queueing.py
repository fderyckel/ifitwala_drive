from __future__ import annotations

from typing import Any

import frappe

_DRIVE_QUEUE_FALLBACKS = {
	"drive_short": "short",
	"drive_default": "default",
	"drive_heavy": "long",
}
_FRAPPE_DEFAULT_QUEUES = {"short", "default", "long"}


def resolve_enqueue_queue(queue_name: str | None) -> str:
	"""Map Drive semantic queues onto a valid Frappe runtime queue.

	Drive keeps its own semantic queue classes on Drive Processing Job rows.
	At enqueue time, prefer a same-named custom worker queue when the site has
	explicitly configured one; otherwise fall back to the standard Frappe queues
	so uploads do not fail on sites that only run short/default/long workers.
	"""

	normalized = str(queue_name or "").strip()
	if not normalized:
		return "default"

	if normalized in _FRAPPE_DEFAULT_QUEUES:
		return normalized

	if _is_runtime_queue_configured(normalized):
		return normalized

	return _DRIVE_QUEUE_FALLBACKS.get(normalized, normalized)


def _is_runtime_queue_configured(queue_name: str) -> bool:
	get_conf = getattr(frappe, "get_conf", None)
	if not callable(get_conf):
		return False

	try:
		conf = get_conf() or {}
	except Exception:
		return False

	workers = _extract_workers_config(conf)
	return queue_name in workers


def _extract_workers_config(conf: Any) -> dict[str, Any]:
	if isinstance(conf, dict):
		workers = conf.get("workers")
		return workers if isinstance(workers, dict) else {}

	getter = getattr(conf, "get", None)
	if callable(getter):
		workers = getter("workers")
		if isinstance(workers, dict):
			return workers

	workers = getattr(conf, "workers", None)
	return workers if isinstance(workers, dict) else {}
