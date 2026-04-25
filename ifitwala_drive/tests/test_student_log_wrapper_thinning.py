from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeFrappeError(Exception):
	pass


def _install_fake_frappe() -> None:
	frappe = types.ModuleType("frappe")
	frappe._ = lambda message: message
	frappe.throw = lambda message, *args, **kwargs: (_ for _ in ()).throw(FakeFrappeError(message))
	sys.modules["frappe"] = frappe


def test_student_log_upload_wrapper_uses_resolved_generic_session_boundary():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.access",
		"ifitwala_drive.services.folders.resolution",
		"ifitwala_drive.services.integration._ed_delegate",
		"ifitwala_drive.services.integration.ifitwala_ed_bridge",
		"ifitwala_drive.services.integration.ifitwala_ed_student_logs",
		"ifitwala_drive.services.uploads.sessions",
	)
	try:
		_install_fake_frappe()
		recorder: dict[str, object] = {}

		access_module = types.ModuleType("ifitwala_drive.services.files.access")
		access_module._assert_can_issue_download = lambda *args, **kwargs: None
		access_module._assert_can_issue_preview = lambda *args, **kwargs: None
		access_module._issue_grant = lambda *args, **kwargs: {"status": "ok"}
		sys.modules["ifitwala_drive.services.files.access"] = access_module

		folder_module = types.ModuleType("ifitwala_drive.services.folders.resolution")

		def _resolve_student_log_evidence_folder(**kwargs):
			recorder["folder_args"] = kwargs
			return "DRF-SLOG-0001"

		folder_module.resolve_student_log_evidence_folder = _resolve_student_log_evidence_folder
		sys.modules["ifitwala_drive.services.folders.resolution"] = folder_module

		delegate_module = types.ModuleType("ifitwala_drive.services.integration._ed_delegate")
		delegate_module.load_ed_drive_module = lambda module_name: types.SimpleNamespace()
		sys.modules["ifitwala_drive.services.integration._ed_delegate"] = delegate_module

		bridge_module = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_bridge")

		def _reconcile_upload_session_payload(payload):
			recorder.setdefault("reconcile_calls", []).append(dict(payload))
			return {
				**payload,
				"owner_doctype": "Student Log",
				"owner_name": "SLOG-0001",
				"attached_doctype": "Student Log",
				"attached_name": "SLOG-0001",
				"organization": "ORG-0001",
				"school": "SCH-0001",
				"primary_subject_type": "Student",
				"primary_subject_id": "STU-0001",
				"data_class": "safeguarding",
				"purpose": "safeguarding_evidence",
				"retention_policy": "fixed_7y",
				"slot": "student_log_evidence__row_0001",
				"contract_version": "1",
				"row_name": "ROW-0001",
			}

		bridge_module.reconcile_upload_session_payload = _reconcile_upload_session_payload
		sys.modules["ifitwala_drive.services.integration.ifitwala_ed_bridge"] = bridge_module

		sessions_module = types.ModuleType("ifitwala_drive.services.uploads.sessions")

		def _create_resolved_upload_session_service(payload):
			recorder["session_payload"] = dict(payload)
			return {
				"status": "created",
				"workflow_id": payload.get("workflow_id"),
				"workflow_result": payload.get("workflow_result") or {},
			}

		def _create_upload_session_service(_payload):
			raise AssertionError("Wrapper must use the resolved session boundary.")

		sessions_module.create_resolved_upload_session_service = _create_resolved_upload_session_service
		sessions_module.create_upload_session_service = _create_upload_session_service
		sys.modules["ifitwala_drive.services.uploads.sessions"] = sessions_module

		module = importlib.import_module("ifitwala_drive.services.integration.ifitwala_ed_student_logs")
		response = module.upload_student_log_evidence_attachment_service(
			{
				"student_log": "SLOG-0001",
				"row_name": "ROW-0001",
				"slot": "student_log_evidence__row_0001",
				"filename_original": "evidence.pdf",
				"mime_type_hint": "application/pdf",
				"expected_size_bytes": 42,
				"idempotency_key": "retry-student-log-001",
			}
		)

		assert response == {
			"status": "created",
			"workflow_id": "student_log.evidence_attachment",
			"workflow_result": {
				"row_name": "ROW-0001",
				"slot": "student_log_evidence__row_0001",
			},
		}

		assert recorder["reconcile_calls"] == [
			{
				"workflow_id": "student_log.evidence_attachment",
				"workflow_payload": {
					"student_log": "SLOG-0001",
					"row_name": "ROW-0001",
					"slot": "student_log_evidence__row_0001",
				},
				"filename_original": "evidence.pdf",
				"mime_type_hint": "application/pdf",
				"expected_size_bytes": 42,
				"idempotency_key": "retry-student-log-001",
				"upload_source": "Desk",
			}
		]

		reconcile_payload = recorder["reconcile_calls"][0]
		for governance_field in (
			"owner_doctype",
			"owner_name",
			"primary_subject_id",
			"purpose",
			"retention_policy",
		):
			assert governance_field not in reconcile_payload

		assert recorder["folder_args"] == {
			"student": "STU-0001",
			"student_log": "SLOG-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
		}
		assert recorder["session_payload"]["folder"] == "DRF-SLOG-0001"
		assert recorder["session_payload"]["is_private"] == 1
		assert recorder["session_payload"]["owner_doctype"] == "Student Log"
		assert recorder["session_payload"]["workflow_result"] == {
			"row_name": "ROW-0001",
			"slot": "student_log_evidence__row_0001",
		}
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.services.files.access",
			"ifitwala_drive.services.folders.resolution",
			"ifitwala_drive.services.integration._ed_delegate",
			"ifitwala_drive.services.integration.ifitwala_ed_bridge",
			"ifitwala_drive.services.integration.ifitwala_ed_student_logs",
			"ifitwala_drive.services.uploads.sessions",
		)
