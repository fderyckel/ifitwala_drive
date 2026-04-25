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


def test_org_communication_upload_wrapper_uses_generic_workflow_session_boundary():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.files.access",
		"ifitwala_drive.services.integration._ed_delegate",
		"ifitwala_drive.services.integration.ifitwala_ed_org_communications",
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

		delegate_module = types.ModuleType("ifitwala_drive.services.integration._ed_delegate")
		delegate_module.load_ed_drive_module = lambda module_name: types.SimpleNamespace()
		sys.modules["ifitwala_drive.services.integration._ed_delegate"] = delegate_module

		sessions_module = types.ModuleType("ifitwala_drive.services.uploads.sessions")

		def _create_upload_session_service(payload):
			recorder["session_payload"] = dict(payload)
			return {
				"status": "created",
				"workflow_id": payload.get("workflow_id"),
				"workflow_payload": payload.get("workflow_payload") or {},
			}

		sessions_module.create_upload_session_service = _create_upload_session_service
		sys.modules["ifitwala_drive.services.uploads.sessions"] = sessions_module

		module = importlib.import_module("ifitwala_drive.services.integration.ifitwala_ed_org_communications")
		response = module.upload_org_communication_attachment_service(
			{
				"org_communication": "COMM-0001",
				"row_name": "row-0001",
				"slot": "communication_attachment__row_0001",
				"filename_original": "announcement.pdf",
				"mime_type_hint": "application/pdf",
				"expected_size_bytes": 42,
				"idempotency_key": "retry-org-communication-001",
			}
		)

		assert response == {
			"status": "created",
			"workflow_id": "org_communication.attachment",
			"workflow_payload": {
				"org_communication": "COMM-0001",
				"row_name": "row-0001",
				"slot": "communication_attachment__row_0001",
			},
		}
		session_payload = recorder["session_payload"]
		assert session_payload == {
			"workflow_id": "org_communication.attachment",
			"workflow_payload": {
				"org_communication": "COMM-0001",
				"row_name": "row-0001",
				"slot": "communication_attachment__row_0001",
			},
			"filename_original": "announcement.pdf",
			"mime_type_hint": "application/pdf",
			"expected_size_bytes": 42,
			"idempotency_key": "retry-org-communication-001",
			"upload_source": "SPA",
		}
		for governance_field in (
			"owner_doctype",
			"owner_name",
			"primary_subject_id",
			"purpose",
			"retention_policy",
		):
			assert governance_field not in session_payload
	finally:
		_purge_modules(
			"frappe",
			"ifitwala_drive.services.files.access",
			"ifitwala_drive.services.integration._ed_delegate",
			"ifitwala_drive.services.integration.ifitwala_ed_org_communications",
			"ifitwala_drive.services.uploads.sessions",
		)
