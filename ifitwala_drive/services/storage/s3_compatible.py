from __future__ import annotations

from ifitwala_drive.services.storage.remote import ConfiguredRemoteStorageBackend


class S3CompatibleStorageBackend(ConfiguredRemoteStorageBackend):
	backend_name = "s3_compatible"
	grant_type = "signed_url"
	default_upload_strategy = "signed_put"
