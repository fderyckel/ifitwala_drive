from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import frappe

ifitwala_ed_media = importlib.import_module("ifitwala_drive.services.integration.ifitwala_ed_media")


def _build_api_wrapper(
	method_name: str,
	service_callable: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
	@frappe.whitelist()
	def _wrapper(**kwargs: Any) -> dict[str, Any]:
		return service_callable(kwargs)

	_wrapper.__name__ = method_name
	_wrapper.__qualname__ = method_name
	_wrapper.__doc__ = f"Workflow-aware wrapper for `{method_name}`."
	return _wrapper


for _method_name, _service_callable in ifitwala_ed_media.MEDIA_API_SERVICE_EXPORTS.items():
	globals()[_method_name] = _build_api_wrapper(_method_name, _service_callable)

__all__ = tuple(ifitwala_ed_media.MEDIA_API_SERVICE_EXPORTS)
