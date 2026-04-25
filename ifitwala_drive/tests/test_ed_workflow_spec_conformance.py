from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _ensure_ed_repo_on_path() -> None:
	ed_repo_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed"
	if not ed_repo_root.exists():
		raise AssertionError(f"Ifitwala_Ed repo not found at expected path: {ed_repo_root}")
	ed_repo_root_text = str(ed_repo_root)
	if ed_repo_root_text not in sys.path:
		sys.path.insert(0, ed_repo_root_text)


class FakeFrappeError(Exception):
	pass


class FakeDoc:
	_insert_count = 0

	def __init__(self, data: dict[str, Any] | None = None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def get(self, key: str, default: Any = None) -> Any:
		return getattr(self, key, default)

	def insert(self, ignore_permissions: bool = False):
		if not getattr(self, "name", None):
			FakeDoc._insert_count += 1
			self.name = f"DUS-{FakeDoc._insert_count:04d}"
		return self


class FakeDB:
	def exists(self, doctype: str, name: Any = None) -> bool:
		return True

	def get_value(self, doctype: str, filters: Any, fieldname: Any = None, **kwargs):
		if doctype == "Drive Upload Session":
			return None
		return None


def _install_fake_frappe() -> None:
	FakeDoc._insert_count = 0
	frappe = types.ModuleType("frappe")
	frappe._ = lambda message: message
	frappe.throw = lambda message, *args, **kwargs: (_ for _ in ()).throw(FakeFrappeError(message))
	frappe.db = FakeDB()
	frappe.session = types.SimpleNamespace(user="teacher@example.com")
	frappe.local = types.SimpleNamespace(request_ip="127.0.0.1")
	frappe.generate_hash = lambda length=24: "x" * length
	frappe.get_doc = lambda data, *args, **kwargs: FakeDoc(data) if isinstance(data, dict) else FakeDoc()
	frappe.as_json = lambda value, indent=None: json.dumps(value, sort_keys=True)
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
	sys.modules["frappe"] = frappe

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: "2026-04-25 09:00:00"
	sys.modules["frappe.utils"] = utils
	frappe.utils = utils


def _contract(
	*,
	owner_doctype: str,
	owner_name: str,
	primary_subject_type: str,
	primary_subject_id: str,
	data_class: str,
	purpose: str,
	retention_policy: str,
	slot: str,
	attached_doctype: str | None = None,
	attached_name: str | None = None,
	organization: str = "ORG-0001",
	school: str | None = "SCH-0001",
) -> dict[str, Any]:
	return {
		"owner_doctype": owner_doctype,
		"owner_name": owner_name,
		"attached_doctype": attached_doctype or owner_doctype,
		"attached_name": attached_name or owner_name,
		"organization": organization,
		"school": school,
		"primary_subject_type": primary_subject_type,
		"primary_subject_id": primary_subject_id,
		"data_class": data_class,
		"purpose": purpose,
		"retention_policy": retention_policy,
		"slot": slot,
	}


SAMPLE_CONTRACTS: tuple[tuple[str, str, dict[str, Any]], ...] = (
	(
		"task.submission",
		"default",
		_contract(
			owner_doctype="Task Submission",
			owner_name="TSUB-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="assessment",
			purpose="assessment_submission",
			retention_policy="until_school_exit_plus_6m",
			slot="submission",
		),
	),
	(
		"task.feedback_export",
		"default",
		_contract(
			owner_doctype="Task Submission",
			owner_name="TSUB-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="assessment",
			purpose="assessment_feedback",
			retention_policy="until_school_exit_plus_6m",
			slot="feedback_export__released__student",
		),
	),
	(
		"supporting_material.file",
		"default",
		_contract(
			owner_doctype="Supporting Material",
			owner_name="MAT-0001",
			primary_subject_type="Organization",
			primary_subject_id="ORG-0001",
			data_class="academic",
			purpose="learning_resource",
			retention_policy="until_program_end_plus_1y",
			slot="material_file",
		),
	),
	(
		"admissions.applicant_document",
		"default",
		_contract(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Applicant Document Item",
			attached_name="ADI-0001",
			primary_subject_type="Student Applicant",
			primary_subject_id="APP-0001",
			data_class="legal",
			purpose="identification_document",
			retention_policy="until_school_exit_plus_6m",
			slot="identity_passport_passport_copy",
		),
	),
	(
		"admissions.applicant_profile_image",
		"default",
		_contract(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			primary_subject_type="Student Applicant",
			primary_subject_id="APP-0001",
			data_class="identity_image",
			purpose="applicant_profile_display",
			retention_policy="until_school_exit_plus_6m",
			slot="profile_image",
		),
	),
	(
		"admissions.applicant_guardian_image",
		"default",
		_contract(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Student Applicant Guardian",
			attached_name="GUARDIAN-ROW-0001",
			primary_subject_type="Student Applicant",
			primary_subject_id="APP-0001",
			data_class="identity_image",
			purpose="applicant_profile_display",
			retention_policy="until_school_exit_plus_6m",
			slot="guardian_profile_image__guardian_row_0001",
		),
	),
	(
		"admissions.applicant_health_vaccination",
		"default",
		_contract(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Applicant Health Profile",
			attached_name="AHP-0001",
			primary_subject_type="Student Applicant",
			primary_subject_id="APP-0001",
			data_class="safeguarding",
			purpose="medical_record",
			retention_policy="until_school_exit_plus_6m",
			slot="health_vaccination_proof_mmr_2020_01_01",
		),
	),
	(
		"student.export_file",
		"portfolio",
		_contract(
			owner_doctype="Student",
			owner_name="STU-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="academic",
			purpose="portfolio_export",
			retention_policy="immediate_on_request",
			slot="portfolio_export_pdf",
		),
	),
	(
		"student.export_file",
		"journal",
		_contract(
			owner_doctype="Student",
			owner_name="STU-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="academic",
			purpose="journal_export",
			retention_policy="immediate_on_request",
			slot="journal_export_pdf",
		),
	),
	(
		"student_patient.vaccination_proof",
		"default",
		_contract(
			owner_doctype="Student Patient",
			owner_name="SPAT-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="safeguarding",
			purpose="medical_record",
			retention_policy="until_school_exit_plus_6m",
			slot="health_vaccination_proof_mmr_2020_01_01",
		),
	),
	(
		"student.promoted_admissions_document",
		"default",
		_contract(
			owner_doctype="Student",
			owner_name="STU-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="legal",
			purpose="identification_document",
			retention_policy="until_school_exit_plus_6m",
			slot="admissions_identity_passport_passport_copy",
		),
	),
	(
		"org_communication.attachment",
		"default",
		_contract(
			owner_doctype="Org Communication",
			owner_name="COMM-0001",
			primary_subject_type="Organization",
			primary_subject_id="ORG-0001",
			data_class="administrative",
			purpose="administrative",
			retention_policy="fixed_7y",
			slot="communication_attachment__row_0001",
		),
	),
	(
		"student_log.evidence_attachment",
		"default",
		_contract(
			owner_doctype="Student Log",
			owner_name="SLOG-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="safeguarding",
			purpose="safeguarding_evidence",
			retention_policy="fixed_7y",
			slot="student_log_evidence__row_0001",
		),
	),
	(
		"media.employee_profile_image",
		"default",
		_contract(
			owner_doctype="Employee",
			owner_name="EMP-0001",
			primary_subject_type="Employee",
			primary_subject_id="EMP-0001",
			data_class="identity_image",
			purpose="employee_profile_display",
			retention_policy="employment_duration_plus_grace",
			slot="profile_image",
			school=None,
		),
	),
	(
		"media.student_profile_image",
		"default",
		_contract(
			owner_doctype="Student",
			owner_name="STU-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="identity_image",
			purpose="student_profile_display",
			retention_policy="until_school_exit_plus_6m",
			slot="profile_image",
		),
	),
	(
		"media.guardian_profile_image",
		"default",
		_contract(
			owner_doctype="Guardian",
			owner_name="GUARD-0001",
			primary_subject_type="Guardian",
			primary_subject_id="GUARD-0001",
			data_class="identity_image",
			purpose="guardian_profile_display",
			retention_policy="until_school_exit_plus_6m",
			slot="profile_image",
			school=None,
		),
	),
	(
		"organization_media.organization_logo",
		"default",
		_contract(
			owner_doctype="Organization",
			owner_name="ORG-0001",
			primary_subject_type="Organization",
			primary_subject_id="ORG-0001",
			data_class="operational",
			purpose="organization_public_media",
			retention_policy="immediate_on_request",
			slot="organization_logo__org_0001",
			school=None,
		),
	),
	(
		"organization_media.school_logo",
		"default",
		_contract(
			owner_doctype="Organization",
			owner_name="ORG-0001",
			primary_subject_type="Organization",
			primary_subject_id="ORG-0001",
			data_class="operational",
			purpose="organization_public_media",
			retention_policy="immediate_on_request",
			slot="school_logo__sch_0001",
		),
	),
	(
		"organization_media.school_gallery_image",
		"default",
		_contract(
			owner_doctype="Organization",
			owner_name="ORG-0001",
			primary_subject_type="Organization",
			primary_subject_id="ORG-0001",
			data_class="operational",
			purpose="organization_public_media",
			retention_policy="immediate_on_request",
			slot="school_gallery_image__row_0001",
		),
	),
	(
		"organization_media.asset",
		"default",
		_contract(
			owner_doctype="Organization",
			owner_name="ORG-0001",
			primary_subject_type="Organization",
			primary_subject_id="ORG-0001",
			data_class="operational",
			purpose="organization_public_media",
			retention_policy="immediate_on_request",
			slot="organization_media__homepage_hero",
			school=None,
		),
	),
)

_SAMPLE_BY_KEY = {
	(workflow_id, sample_name): contract for workflow_id, sample_name, contract in SAMPLE_CONTRACTS
}


def _sample_payload(workflow_id: str, sample_name: str = "default") -> dict[str, Any]:
	return {
		"workflow_id": workflow_id,
		"workflow_payload": {"sample_name": sample_name},
		"filename_original": f"{workflow_id.replace('.', '_')}_{sample_name}.pdf",
		"mime_type_hint": "application/pdf",
		"expected_size_bytes": 42,
		"idempotency_key": f"{workflow_id}:{sample_name}",
		"upload_source": "Unit Test",
	}


def _install_fake_storage() -> None:
	storage_module = types.ModuleType("ifitwala_drive.services.storage.base")

	class FakeStorage:
		backend_name = "unit_test"

		def create_temporary_upload_target(self, **kwargs):
			return {
				"upload_strategy": "proxy_post",
				"upload_target": {
					"url": "/api/method/ifitwala_drive.api.uploads.upload_session_blob",
				},
				"object_key": kwargs.get("object_key_hint") or "tmp/unit-test-object",
			}

	storage_module.get_storage_backend = lambda *args, **kwargs: FakeStorage()
	storage_module.resolve_storage_runtime_profile = lambda: types.SimpleNamespace(base_prefix=None)
	storage_module.build_object_key = lambda *parts, base_prefix=None: "/".join(
		str(part).strip("/") for part in parts if str(part or "").strip("/")
	)
	sys.modules["ifitwala_drive.services.storage.base"] = storage_module


def _install_fake_bridge() -> None:
	bridge_module = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_bridge")

	def _reconcile_upload_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
		workflow_id = str(payload.get("workflow_id") or "").strip()
		workflow_payload = payload.get("workflow_payload")
		if not isinstance(workflow_payload, dict):
			workflow_payload = {}
		sample_name = str(workflow_payload.get("sample_name") or "default").strip() or "default"
		contract = dict(_SAMPLE_BY_KEY[(workflow_id, sample_name)])
		return {
			**contract,
			"workflow_id": workflow_id,
			"contract_version": "1",
			"workflow_payload": workflow_payload,
			"filename_original": payload.get("filename_original"),
			"mime_type_hint": payload.get("mime_type_hint"),
			"expected_size_bytes": payload.get("expected_size_bytes"),
			"idempotency_key": payload.get("idempotency_key"),
			"upload_source": payload.get("upload_source"),
		}

	bridge_module.reconcile_upload_session_payload = _reconcile_upload_session_payload
	sys.modules["ifitwala_drive.services.integration.ifitwala_ed_bridge"] = bridge_module


def _install_fake_logging() -> None:
	logging_module = types.ModuleType("ifitwala_drive.services.logging")
	logging_module.log_drive_event = lambda *args, **kwargs: None
	sys.modules["ifitwala_drive.services.logging"] = logging_module


@pytest.fixture(autouse=True)
def _clean_modules():
	_purge_modules("frappe", "ifitwala_drive.services", "ifitwala_ed")
	yield
	_purge_modules("frappe", "ifitwala_drive.services", "ifitwala_ed")


def test_conformance_samples_cover_every_ed_governed_upload_spec():
	_install_fake_frappe()
	_ensure_ed_repo_on_path()
	workflow_specs = importlib.import_module("ifitwala_ed.integrations.drive.workflow_specs")

	actual = {spec.workflow_id for spec in workflow_specs.iter_upload_specs()}
	expected = {workflow_id for workflow_id, _sample_name, _contract in SAMPLE_CONTRACTS}

	assert expected == actual
	assert all(spec.contract_version for spec in workflow_specs.iter_upload_specs())


@pytest.mark.parametrize("workflow_id,sample_name,contract", SAMPLE_CONTRACTS)
def test_drive_validation_accepts_every_ed_workflow_sample(
	workflow_id: str,
	sample_name: str,
	contract: dict[str, Any],
):
	_install_fake_frappe()
	_ensure_ed_repo_on_path()
	validation = importlib.import_module("ifitwala_drive.services.uploads.validation")
	payload = {
		**contract,
		"workflow_id": workflow_id,
		"contract_version": "1",
		"filename_original": f"{workflow_id.replace('.', '_')}_{sample_name}.pdf",
	}

	validation.validate_create_session_payload(payload)


@pytest.mark.parametrize("workflow_id,sample_name,_contract", SAMPLE_CONTRACTS)
def test_generic_create_upload_session_accepts_every_ed_workflow_sample(
	workflow_id: str,
	sample_name: str,
	_contract: dict[str, Any],
):
	_install_fake_frappe()
	_ensure_ed_repo_on_path()
	_install_fake_bridge()
	_install_fake_storage()
	_install_fake_logging()
	sessions = importlib.import_module("ifitwala_drive.services.uploads.sessions")

	response = sessions.create_upload_session_service(_sample_payload(workflow_id, sample_name))

	assert response["status"] == "created"
	assert response["workflow_id"] == workflow_id
	assert response["contract_version"] == "1"
	assert response["upload_strategy"] == "proxy_post"
	assert "/private/" not in json.dumps(response, sort_keys=True)


@pytest.mark.parametrize(
	"module_name",
	(
		"ifitwala_ed.integrations.drive.bridge",
		"ifitwala_ed.integrations.drive.admissions",
		"ifitwala_ed.integrations.drive.media",
		"ifitwala_ed.integrations.drive.materials",
		"ifitwala_ed.integrations.drive.org_communications",
		"ifitwala_ed.integrations.drive.student_logs",
		"ifitwala_ed.integrations.drive.tasks",
	),
)
def test_drive_delegate_allowlist_covers_current_ed_bridge_modules(module_name: str):
	_install_fake_frappe()
	for package_name in (
		"ifitwala_ed",
		"ifitwala_ed.integrations",
		"ifitwala_ed.integrations.drive",
	):
		package = types.ModuleType(package_name)
		package.__path__ = []
		sys.modules[package_name] = package
	target_module = types.ModuleType(module_name)
	sys.modules[module_name] = target_module

	delegate = importlib.import_module("ifitwala_drive.services.integration._ed_delegate")

	assert delegate.load_ed_drive_module(module_name) is target_module
