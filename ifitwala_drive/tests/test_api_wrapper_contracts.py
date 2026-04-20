from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe() -> None:
	frappe = types.ModuleType("frappe")
	frappe._ = lambda message: message
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.form_dict = {}
	frappe.request = None
	sys.modules["frappe"] = frappe


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def test_submission_wrapper_maps_explicit_payload():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.submissions",
		"ifitwala_drive.services.integration.ifitwala_ed_tasks",
	)
	try:
		_install_fake_frappe()
		recorder = {}
		service_module = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_tasks")

		def _service(payload):
			recorder["payload"] = payload
			return {"status": "ok"}

		service_module.upload_task_submission_artifact_service = _service
		sys.modules["ifitwala_drive.services.integration.ifitwala_ed_tasks"] = service_module

		module = _load_module("ifitwala_drive.api.submissions")
		module.upload_task_submission_artifact(
			task_submission="TSUB-0001",
			filename_original="essay.docx",
			student="STU-0001",
			slot="submission",
			expected_size_bytes=42,
			idempotency_key="retry-submission-001",
		)

		assert recorder["payload"] == {
			"task_submission": "TSUB-0001",
			"filename_original": "essay.docx",
			"student": "STU-0001",
			"slot": "submission",
			"expected_size_bytes": 42,
			"idempotency_key": "retry-submission-001",
		}
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.api.submissions",
			"ifitwala_drive.services.integration.ifitwala_ed_tasks",
		)


def test_admissions_wrapper_maps_explicit_payload():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.admissions",
		"ifitwala_drive.services.integration.ifitwala_ed_admissions",
	)
	try:
		_install_fake_frappe()
		recorder = {}
		service_module = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_admissions")

		def _document_service(payload):
			recorder["document"] = payload
			return {"status": "ok"}

		def _health_service(payload):
			recorder["health"] = payload
			return {"status": "ok"}

		service_module.upload_applicant_document_service = _document_service
		service_module.upload_applicant_profile_image_service = lambda payload: {"status": "ok"}
		service_module.upload_applicant_guardian_image_service = lambda payload: {"status": "ok"}
		service_module.upload_applicant_health_vaccination_proof_service = _health_service
		sys.modules["ifitwala_drive.services.integration.ifitwala_ed_admissions"] = service_module

		module = _load_module("ifitwala_drive.api.admissions")
		module.upload_applicant_document(
			student_applicant="APP-0001",
			filename_original="passport.pdf",
			document_type="Passport",
			item_key="passport_copy",
			idempotency_key="retry-applicant-001",
		)
		module.upload_applicant_health_vaccination_proof(
			student_applicant="APP-0001",
			applicant_health_profile="AHP-0001",
			vaccine_name="MMR",
			date="2020-03-04",
			filename_original="proof.png",
			row_index=0,
		)

		assert recorder["document"] == {
			"student_applicant": "APP-0001",
			"filename_original": "passport.pdf",
			"document_type": "Passport",
			"item_key": "passport_copy",
			"idempotency_key": "retry-applicant-001",
		}
		assert recorder["health"] == {
			"student_applicant": "APP-0001",
			"applicant_health_profile": "AHP-0001",
			"vaccine_name": "MMR",
			"date": "2020-03-04",
			"filename_original": "proof.png",
			"row_index": 0,
		}
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.api.admissions",
			"ifitwala_drive.services.integration.ifitwala_ed_admissions",
		)


def test_access_and_upload_wrappers_map_explicit_payloads():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.access",
		"ifitwala_drive.api.erasure",
		"ifitwala_drive.api.files",
		"ifitwala_drive.api.uploads",
		"ifitwala_drive.services.audit.erasure",
		"ifitwala_drive.services.files.access",
		"ifitwala_drive.services.files.versions",
		"ifitwala_drive.services.files.legacy_access",
		"ifitwala_drive.services.logging",
		"ifitwala_drive.services.storage.base",
		"ifitwala_drive.services.uploads.finalize",
		"ifitwala_drive.services.uploads.sessions",
	)
	try:
		_install_fake_frappe()
		recorder: dict[str, object] = {}

		access_module = types.ModuleType("ifitwala_drive.services.files.access")
		access_module.issue_download_grant_service = lambda payload: recorder.setdefault(
			"download", payload
		) or {"status": "ok"}
		access_module.issue_preview_grant_service = lambda payload: recorder.setdefault(
			"preview", payload
		) or {"status": "ok"}
		sys.modules["ifitwala_drive.services.files.access"] = access_module

		versions_module = types.ModuleType("ifitwala_drive.services.files.versions")
		versions_module.replace_drive_file_version_service = lambda payload: recorder.setdefault(
			"replace", payload
		) or {"status": "ok"}
		sys.modules["ifitwala_drive.services.files.versions"] = versions_module

		erasure_module = types.ModuleType("ifitwala_drive.services.audit.erasure")
		erasure_module.create_drive_erasure_request_service = lambda payload: recorder.setdefault(
			"erasure_create", payload
		) or {"status": "ok"}
		erasure_module.execute_drive_erasure_request_service = lambda payload: recorder.setdefault(
			"erasure_execute", payload
		) or {"status": "ok"}
		sys.modules["ifitwala_drive.services.audit.erasure"] = erasure_module

		legacy_module = types.ModuleType("ifitwala_drive.services.files.legacy_access")
		legacy_module.resolve_public_file_redirect = lambda **kwargs: {"url": "https://example.invalid"}
		sys.modules["ifitwala_drive.services.files.legacy_access"] = legacy_module

		logging_module = types.ModuleType("ifitwala_drive.services.logging")
		logging_module.log_drive_event = lambda *args, **kwargs: None
		sys.modules["ifitwala_drive.services.logging"] = logging_module

		storage_module = types.ModuleType("ifitwala_drive.services.storage.base")
		storage_module.get_storage_backend = lambda *args, **kwargs: None
		sys.modules["ifitwala_drive.services.storage.base"] = storage_module

		finalize_module = types.ModuleType("ifitwala_drive.services.uploads.finalize")
		finalize_module.finalize_upload_session_service = lambda payload: recorder.setdefault(
			"finalize", payload
		) or {"status": "ok"}
		sys.modules["ifitwala_drive.services.uploads.finalize"] = finalize_module

		sessions_module = types.ModuleType("ifitwala_drive.services.uploads.sessions")
		sessions_module.create_upload_session_service = lambda payload: recorder.setdefault(
			"create", payload
		) or {"status": "ok"}
		sessions_module.abort_upload_session_service = lambda payload: recorder.setdefault(
			"abort", payload
		) or {"status": "ok"}
		sessions_module.load_upload_contract = lambda *args, **kwargs: {"upload_strategy": "proxy_post"}
		sys.modules["ifitwala_drive.services.uploads.sessions"] = sessions_module

		access_api = _load_module("ifitwala_drive.api.access")
		erasure_api = _load_module("ifitwala_drive.api.erasure")
		files_api = _load_module("ifitwala_drive.api.files")
		uploads_api = _load_module("ifitwala_drive.api.uploads")

		access_api.issue_download_grant(canonical_ref="drv:ORG-0001:DF-0001")
		access_api.issue_preview_grant(drive_file_id="DF-0002", derivative_role="thumb")
		erasure_api.create_drive_erasure_request(
			data_subject_type="Student",
			data_subject_id="STU-0001",
			scope="slot_only",
			request_reason="GDPR",
			slot_filter="submission",
		)
		erasure_api.execute_drive_erasure_request(erasure_request_id="DER-0001")
		files_api.replace_drive_file_version(
			drive_file_id="DF-0001",
			new_file_artifact={
				"file_id": "FILE-0002",
				"storage_object_key": "files/ab/cd/object-v2.docx",
			},
			reason="replace",
		)
		uploads_api.create_upload_session(
			workflow_id="task.submission",
			workflow_payload={"task_submission": "TSUB-0001", "student": "STU-0001"},
			filename_original="essay.docx",
			idempotency_key="retry-upload-001",
		)
		uploads_api.finalize_upload_session(upload_session_id="DUS-0001", received_size_bytes=42)
		uploads_api.abort_upload_session(upload_session_id="DUS-0001")

		assert recorder["download"] == {"canonical_ref": "drv:ORG-0001:DF-0001"}
		assert recorder["preview"] == {"drive_file_id": "DF-0002", "derivative_role": "thumb"}
		assert recorder["erasure_create"] == {
			"data_subject_type": "Student",
			"data_subject_id": "STU-0001",
			"scope": "slot_only",
			"request_reason": "GDPR",
			"slot_filter": "submission",
		}
		assert recorder["erasure_execute"] == {"erasure_request_id": "DER-0001"}
		assert recorder["replace"] == {
			"drive_file_id": "DF-0001",
			"new_file_artifact": {
				"file_id": "FILE-0002",
				"storage_object_key": "files/ab/cd/object-v2.docx",
			},
			"reason": "replace",
		}
		assert recorder["create"] == {
			"workflow_id": "task.submission",
			"workflow_payload": {"task_submission": "TSUB-0001", "student": "STU-0001"},
			"filename_original": "essay.docx",
			"idempotency_key": "retry-upload-001",
		}
		assert recorder["finalize"] == {"upload_session_id": "DUS-0001", "received_size_bytes": 42}
		assert recorder["abort"] == {"upload_session_id": "DUS-0001"}
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.api.access",
			"ifitwala_drive.api.erasure",
			"ifitwala_drive.api.files",
			"ifitwala_drive.api.uploads",
			"ifitwala_drive.services.audit.erasure",
			"ifitwala_drive.services.files.access",
			"ifitwala_drive.services.files.versions",
			"ifitwala_drive.services.files.legacy_access",
			"ifitwala_drive.services.logging",
			"ifitwala_drive.services.storage.base",
			"ifitwala_drive.services.uploads.finalize",
			"ifitwala_drive.services.uploads.sessions",
		)


def test_communications_wrapper_maps_explicit_payload():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.communications",
		"ifitwala_drive.services.integration.ifitwala_ed_org_communications",
	)
	try:
		_install_fake_frappe()
		recorder = {}
		service_module = types.ModuleType(
			"ifitwala_drive.services.integration.ifitwala_ed_org_communications"
		)

		def _upload_service(payload):
			recorder["upload"] = payload
			return {"status": "ok"}

		def _download_service(payload):
			recorder["download"] = payload
			return {"status": "ok"}

		def _preview_service(payload):
			recorder["preview"] = payload
			return {"status": "ok"}

		service_module.upload_org_communication_attachment_service = _upload_service
		service_module.issue_org_communication_attachment_download_grant_service = _download_service
		service_module.issue_org_communication_attachment_preview_grant_service = _preview_service
		sys.modules["ifitwala_drive.services.integration.ifitwala_ed_org_communications"] = service_module

		module = _load_module("ifitwala_drive.api.communications")
		module.upload_org_communication_attachment(
			org_communication="COMM-0001",
			filename_original="announcement.pdf",
			row_name="ROW-0001",
			idempotency_key="retry-comm-001",
		)
		module.issue_org_communication_attachment_download_grant(
			org_communication="COMM-0001",
			row_name="ROW-0001",
		)
		module.issue_org_communication_attachment_preview_grant(
			org_communication="COMM-0001",
			row_name="ROW-0001",
			derivative_role="thumb",
		)

		assert recorder["upload"] == {
			"org_communication": "COMM-0001",
			"filename_original": "announcement.pdf",
			"row_name": "ROW-0001",
			"idempotency_key": "retry-comm-001",
		}
		assert recorder["download"] == {
			"org_communication": "COMM-0001",
			"row_name": "ROW-0001",
		}
		assert recorder["preview"] == {
			"org_communication": "COMM-0001",
			"row_name": "ROW-0001",
			"derivative_role": "thumb",
		}
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.api.communications",
			"ifitwala_drive.services.integration.ifitwala_ed_org_communications",
		)


def test_materials_wrapper_maps_grant_payload():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.materials",
		"ifitwala_drive.services.integration.ifitwala_ed_materials",
	)
	try:
		_install_fake_frappe()
		recorder = {}
		service_module = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_materials")

		service_module.upload_supporting_material_service = lambda payload: recorder.setdefault(
			"upload", payload
		) or {"status": "ok"}
		service_module.issue_supporting_material_download_grant_service = lambda payload: recorder.setdefault(
			"download", payload
		) or {"status": "ok"}
		service_module.issue_supporting_material_preview_grant_service = lambda payload: recorder.setdefault(
			"preview", payload
		) or {"status": "ok"}
		sys.modules["ifitwala_drive.services.integration.ifitwala_ed_materials"] = service_module

		module = _load_module("ifitwala_drive.api.materials")
		module.upload_supporting_material(
			material="MAT-0001",
			filename_original="worksheet.pdf",
			idempotency_key="retry-mat-001",
		)
		module.issue_supporting_material_download_grant(
			material="MAT-0001",
			placement="MAT-PLC-1",
			drive_file_id="DF-0001",
		)
		module.issue_supporting_material_preview_grant(
			material="MAT-0001",
			placement="MAT-PLC-1",
			drive_file_id="DF-0001",
			derivative_role="thumb",
		)

		assert recorder["upload"] == {
			"material": "MAT-0001",
			"filename_original": "worksheet.pdf",
			"idempotency_key": "retry-mat-001",
		}
		assert recorder["download"] == {
			"material": "MAT-0001",
			"placement": "MAT-PLC-1",
			"drive_file_id": "DF-0001",
		}
		assert recorder["preview"] == {
			"material": "MAT-0001",
			"placement": "MAT-PLC-1",
			"drive_file_id": "DF-0001",
			"derivative_role": "thumb",
		}
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.api.materials",
			"ifitwala_drive.services.integration.ifitwala_ed_materials",
		)
