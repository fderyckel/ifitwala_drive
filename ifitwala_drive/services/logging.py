from __future__ import annotations

from typing import Any

import frappe


def log_drive_event(event: str, **payload: Any) -> None:
	"""Emit compact structured logs for Drive boundary actions."""
	logger_factory = getattr(frappe, "logger", None)
	if not logger_factory:
		return

	logger = logger_factory()
	message = {
		"event": event,
		**payload,
	}

	try:
		logger.info(frappe.as_json(message))
	except Exception:
		logger.info(message)
