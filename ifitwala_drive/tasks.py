from __future__ import annotations

from ifitwala_drive.services.files.derivatives import (
	prune_stale_derivatives_service,
	reconcile_preview_derivatives_service,
)
from ifitwala_drive.services.uploads.sessions import expire_abandoned_upload_sessions_service


def hourly() -> None:
	expire_abandoned_upload_sessions_service()
	prune_stale_derivatives_service()
	reconcile_preview_derivatives_service()
