from __future__ import annotations

from typing import Any


def compact_payload(**kwargs: Any) -> dict[str, Any]:
	return {key: value for key, value in kwargs.items() if value is not None}
