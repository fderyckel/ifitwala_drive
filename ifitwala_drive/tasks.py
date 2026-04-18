from __future__ import annotations

from ifitwala_drive.services.files.derivatives import prune_stale_derivatives_service


def hourly() -> None:
	prune_stale_derivatives_service()
