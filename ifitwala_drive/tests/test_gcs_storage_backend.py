from __future__ import annotations

import importlib
import sys
import types

from ifitwala_drive.services.storage.base import StorageRuntimeProfile


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_google_cloud_storage(*, objects: dict[str, bytes]):
	class FakeBlob:
		def __init__(self, bucket, name: str):
			self.bucket = bucket
			self.name = name

		def create_resumable_upload_session(self, content_type=None, size=None):
			self.bucket.sessions.append(
				{
					"name": self.name,
					"content_type": content_type,
					"size": size,
				}
			)
			return f"https://upload.invalid/{self.name}"

		def exists(self):
			return self.name in self.bucket.objects

		def download_as_bytes(self, start=0, end=None):
			content = self.bucket.objects[self.name]
			if end is None:
				return content[start:]
			return content[start : end + 1]

		def delete(self):
			self.bucket.objects.pop(self.name, None)

	class FakeBucket:
		def __init__(self, name: str):
			self.name = name
			self.objects = objects
			self.sessions: list[dict[str, object]] = []

		def blob(self, name: str):
			return FakeBlob(self, name)

		def copy_blob(self, source_blob, target_bucket, new_name: str):
			target_bucket.objects[new_name] = self.objects[source_blob.name]
			return target_bucket.blob(new_name)

	class FakeClient:
		def __init__(self):
			self.buckets: dict[str, FakeBucket] = {}

		def bucket(self, name: str):
			if name not in self.buckets:
				self.buckets[name] = FakeBucket(name)
			return self.buckets[name]

	client = FakeClient()
	storage_module = types.ModuleType("google.cloud.storage")
	storage_module.Client = lambda: client
	cloud_module = types.ModuleType("google.cloud")
	cloud_module.storage = storage_module
	google_module = types.ModuleType("google")
	google_module.cloud = cloud_module
	sys.modules["google"] = google_module
	sys.modules["google.cloud"] = cloud_module
	sys.modules["google.cloud.storage"] = storage_module
	return client


def test_gcs_storage_backend_resumable_round_trip():
	_purge_modules("google", "google.cloud", "google.cloud.storage", "ifitwala_drive.services.storage.gcs")
	objects = {"tmp/session-1/essay.pdf": b"%PDF-1.4 test payload"}
	client = _install_fake_google_cloud_storage(objects=objects)
	module = importlib.import_module("ifitwala_drive.services.storage.gcs")
	backend = module.GCSStorageBackend(
		profile=StorageRuntimeProfile(
			backend_name="gcs",
			provider_family="gcs",
			bucket_or_container="drive-bucket",
			object_url_base="https://objects.invalid",
		)
	)

	target = backend.create_temporary_upload_target(
		session_key="session-1",
		filename="essay.pdf",
		mime_type="application/pdf",
		expected_size_bytes=20,
		upload_token="token-1",
		object_key_hint="tmp/session-1/essay.pdf",
	)

	assert target["upload_strategy"] == "resumable_put"
	assert target["upload_target"]["method"] == "PUT"
	assert target["upload_target"]["url"] == "https://upload.invalid/tmp/session-1/essay.pdf"
	assert target["upload_target"]["headers"]["Content-Type"] == "application/pdf"
	assert client.bucket("drive-bucket").sessions == [
		{
			"name": "tmp/session-1/essay.pdf",
			"content_type": "application/pdf",
			"size": 20,
		}
	]

	assert backend.temporary_object_exists(object_key="tmp/session-1/essay.pdf") is True
	assert backend.read_temporary_object_head(object_key="tmp/session-1/essay.pdf", max_bytes=4) == b"%PDF"

	artifact = backend.finalize_temporary_object(
		object_key="tmp/session-1/essay.pdf",
		final_key="files/ab/cd/essay.pdf",
	)

	assert artifact == {
		"object_key": "files/ab/cd/essay.pdf",
		"storage_backend": "gcs",
		"file_url": "https://objects.invalid/files/ab/cd/essay.pdf",
	}
	assert "tmp/session-1/essay.pdf" not in objects
	assert objects["files/ab/cd/essay.pdf"] == b"%PDF-1.4 test payload"
