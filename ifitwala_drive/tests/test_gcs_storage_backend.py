from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime

from ifitwala_drive.services.storage.base import StorageRuntimeProfile


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe():
	frappe = types.ModuleType("frappe")
	frappe.conf = {}
	frappe.get_site_path = lambda *parts: "/tmp/ifitwala_drive_test"
	sys.modules["frappe"] = frappe


def _install_fake_google_cloud_storage(*, objects: dict[str, bytes]):
	class FakeBlob:
		def __init__(self, bucket, name: str):
			self.bucket = bucket
			self.name = name
			self.size = None
			self.md5_hash = None

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

		def reload(self):
			if self.name not in self.bucket.objects:
				raise FileNotFoundError(self.name)
			content = self.bucket.objects[self.name]
			self.size = len(content)
			self.md5_hash = f"md5:{self.name}"

		def download_as_bytes(self, start=0, end=None):
			content = self.bucket.objects[self.name]
			if end is None:
				return content[start:]
			return content[start : end + 1]

		def generate_signed_url(self, version=None, expiration=None, method=None, response_disposition=None):
			self.bucket.signed_requests.append(
				{
					"name": self.name,
					"version": version,
					"expiration": expiration,
					"method": method,
					"response_disposition": response_disposition,
				}
			)
			return f"https://signed.invalid/{self.name}?method={method}"

		def upload_from_string(self, content, content_type=None):
			self.bucket.uploads.append(
				{
					"name": self.name,
					"content": content,
					"content_type": content_type,
				}
			)
			self.bucket.objects[self.name] = content

		def delete(self):
			self.bucket.objects.pop(self.name, None)

	class FakeBucket:
		def __init__(self, name: str):
			self.name = name
			self.objects = objects
			self.sessions: list[dict[str, object]] = []
			self.signed_requests: list[dict[str, object]] = []
			self.uploads: list[dict[str, object]] = []

		def blob(self, name: str):
			return FakeBlob(self, name)

		def copy_blob(self, source_blob, target_bucket, new_name: str):
			target_bucket.objects[new_name] = self.objects[source_blob.name]
			return target_bucket.blob(new_name)

	class FakeCredentials:
		def __init__(self, *, source_path: str):
			self.source_path = source_path
			self.project_id = "credential-project"

	class FakeClient:
		def __init__(self):
			self.buckets: dict[str, FakeBucket] = {}
			self.init_calls: list[dict[str, object]] = []
			self.credential_file_calls: list[str] = []

		def bucket(self, name: str):
			if name not in self.buckets:
				self.buckets[name] = FakeBucket(name)
			return self.buckets[name]

	client = FakeClient()

	def client_factory(project=None, credentials=None):
		client.init_calls.append(
			{
				"project": project,
				"credentials": credentials,
			}
		)
		return client

	class FakeCredentialsFactory:
		@classmethod
		def from_service_account_file(cls, path: str):
			client.credential_file_calls.append(path)
			return FakeCredentials(source_path=path)

	storage_module = types.ModuleType("google.cloud.storage")
	storage_module.Client = client_factory
	cloud_module = types.ModuleType("google.cloud")
	cloud_module.storage = storage_module
	google_module = types.ModuleType("google")
	google_module.cloud = cloud_module
	oauth2_module = types.ModuleType("google.oauth2")
	service_account_module = types.ModuleType("google.oauth2.service_account")
	service_account_module.Credentials = FakeCredentialsFactory
	oauth2_module.service_account = service_account_module
	sys.modules["google"] = google_module
	sys.modules["google.cloud"] = cloud_module
	sys.modules["google.cloud.storage"] = storage_module
	sys.modules["google.oauth2"] = oauth2_module
	sys.modules["google.oauth2.service_account"] = service_account_module
	return client


def test_gcs_storage_backend_resumable_round_trip():
	_purge_modules(
		"frappe",
		"google",
		"google.cloud",
		"google.cloud.storage",
		"google.oauth2",
		"google.oauth2.service_account",
		"ifitwala_drive.services.storage.gcs",
	)
	objects = {"tmp/session-1/essay.pdf": b"%PDF-1.4 test payload"}
	client = _install_fake_google_cloud_storage(objects=objects)
	_install_fake_frappe()
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


def test_gcs_storage_backend_download_grant_defaults_to_signed_url():
	_purge_modules(
		"frappe",
		"google",
		"google.cloud",
		"google.cloud.storage",
		"google.oauth2",
		"google.oauth2.service_account",
		"ifitwala_drive.services.storage.gcs",
	)
	client = _install_fake_google_cloud_storage(objects={})
	_install_fake_frappe()
	module = importlib.import_module("ifitwala_drive.services.storage.gcs")
	backend = module.GCSStorageBackend(
		profile=StorageRuntimeProfile(
			backend_name="gcs",
			provider_family="gcs",
			bucket_or_container="drive-bucket",
			signing_mode="gcs_signed_url",
		)
	)

	grant = backend.issue_download_grant(
		object_key="files/ab/cd/essay.pdf",
		file_url=None,
		expires_on=datetime(2026, 4, 13, 10, 0, 0),
		filename="essay.pdf",
	)

	assert grant == {
		"grant_type": "signed_url",
		"url": "https://signed.invalid/files/ab/cd/essay.pdf?method=GET",
	}
	assert client.bucket("drive-bucket").signed_requests == [
		{
			"name": "files/ab/cd/essay.pdf",
			"version": "v4",
			"expiration": datetime(2026, 4, 13, 10, 0, 0),
			"method": "GET",
			"response_disposition": "attachment; filename=\"essay.pdf\"; filename*=UTF-8''essay.pdf",
		}
	]


def test_gcs_storage_backend_service_account_file_credentials():
	_purge_modules(
		"frappe",
		"google",
		"google.cloud",
		"google.cloud.storage",
		"google.oauth2",
		"google.oauth2.service_account",
		"ifitwala_drive.services.storage.gcs",
	)
	client = _install_fake_google_cloud_storage(objects={})
	_install_fake_frappe()
	module = importlib.import_module("ifitwala_drive.services.storage.gcs")
	backend = module.GCSStorageBackend(
		profile=StorageRuntimeProfile(
			backend_name="gcs",
			provider_family="gcs",
			bucket_or_container="drive-bucket",
			project_id="project-a",
			credential_source="service_account_file",
			service_account_file_path="/secrets/gcs.json",
		)
	)

	backend.temporary_object_exists(object_key="files/ab/cd/missing.pdf")

	assert client.credential_file_calls == ["/secrets/gcs.json"]
	assert len(client.init_calls) == 1
	assert client.init_calls[0]["project"] == "project-a"
	assert client.init_calls[0]["credentials"].source_path == "/secrets/gcs.json"


def test_gcs_storage_backend_uses_configured_urls_when_requested():
	_purge_modules(
		"frappe",
		"google",
		"google.cloud",
		"google.cloud.storage",
		"google.oauth2",
		"google.oauth2.service_account",
		"ifitwala_drive.services.storage.gcs",
	)
	_install_fake_google_cloud_storage(objects={})
	_install_fake_frappe()
	module = importlib.import_module("ifitwala_drive.services.storage.gcs")
	backend = module.GCSStorageBackend(
		profile=StorageRuntimeProfile(
			backend_name="gcs",
			provider_family="gcs",
			bucket_or_container="drive-bucket",
			signing_mode="configured_urls",
			download_url_base="https://cdn.invalid/download",
			preview_url_base="https://cdn.invalid/preview",
		)
	)

	download_grant = backend.issue_download_grant(
		object_key="files/ab/cd/essay.pdf",
		file_url=None,
		expires_on=datetime(2026, 4, 13, 10, 0, 0),
		filename="essay.pdf",
	)
	preview_grant = backend.issue_preview_grant(
		object_key="files/ab/cd/essay.pdf",
		file_url=None,
		expires_on=datetime(2026, 4, 13, 10, 0, 0),
		filename="essay.pdf",
	)

	assert download_grant == {
		"grant_type": "signed_url",
		"url": "https://cdn.invalid/download/files/ab/cd/essay.pdf",
	}
	assert preview_grant == {
		"grant_type": "signed_url",
		"url": "https://cdn.invalid/preview/files/ab/cd/essay.pdf",
	}


def test_gcs_storage_backend_write_final_object_uploads_bytes():
	_purge_modules(
		"frappe",
		"google",
		"google.cloud",
		"google.cloud.storage",
		"google.oauth2",
		"google.oauth2.service_account",
		"ifitwala_drive.services.storage.gcs",
	)
	client = _install_fake_google_cloud_storage(objects={})
	_install_fake_frappe()
	module = importlib.import_module("ifitwala_drive.services.storage.gcs")
	backend = module.GCSStorageBackend(
		profile=StorageRuntimeProfile(
			backend_name="gcs",
			provider_family="gcs",
			bucket_or_container="drive-bucket",
			object_url_base="https://objects.invalid",
		)
	)

	artifact = backend.write_final_object(
		object_key="legacy/private/files/archive/report.pdf",
		content=b"report-bytes",
		mime_type="application/pdf",
	)

	assert artifact == {
		"object_key": "legacy/private/files/archive/report.pdf",
		"storage_backend": "gcs",
		"file_url": "https://objects.invalid/legacy/private/files/archive/report.pdf",
	}
	assert client.bucket("drive-bucket").uploads == [
		{
			"name": "legacy/private/files/archive/report.pdf",
			"content": b"report-bytes",
			"content_type": "application/pdf",
		}
	]


def test_gcs_storage_backend_reads_object_metadata():
	_purge_modules(
		"frappe",
		"google",
		"google.cloud",
		"google.cloud.storage",
		"google.oauth2",
		"google.oauth2.service_account",
		"ifitwala_drive.services.storage.gcs",
	)
	_install_fake_frappe()
	_install_fake_google_cloud_storage(objects={"legacy/private/files/archive/report.pdf": b"report-bytes"})
	module = importlib.import_module("ifitwala_drive.services.storage.gcs")
	backend = module.GCSStorageBackend(
		profile=StorageRuntimeProfile(
			backend_name="gcs",
			provider_family="gcs",
			bucket_or_container="drive-bucket",
		)
	)

	metadata = backend.read_object_metadata(object_key="legacy/private/files/archive/report.pdf")

	assert metadata == {
		"exists": True,
		"size_bytes": 12,
		"checksum": "md5:legacy/private/files/archive/report.pdf",
		"verifiable": True,
	}
