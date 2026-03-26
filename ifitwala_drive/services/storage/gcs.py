from __future__ import annotations

from ifitwala_drive.services.storage.remote import ConfiguredRemoteStorageBackend


class GCSStorageBackend(ConfiguredRemoteStorageBackend):
	backend_name = "gcs"
	grant_type = "signed_url"
	default_upload_strategy = "signed_put"
