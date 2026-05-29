from __future__ import annotations

import ast
import importlib
import json
import os
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _ensure_ed_repo_on_path() -> None:
	ed_repo_root = _find_ed_repo_root()
	ed_repo_root_text = str(ed_repo_root)
	if ed_repo_root_text not in sys.path:
		sys.path.insert(0, ed_repo_root_text)


def _find_ed_repo_root() -> Path:
	candidate_roots = []
	if os.environ.get("IFITWALA_ED_REPO"):
		candidate_roots.append(Path(os.environ["IFITWALA_ED_REPO"]).expanduser())
	candidate_roots.extend(
		(
			Path(__file__).resolve().parents[2].parent / "ifitwala_ed",
			Path.cwd() / "ifitwala_ed",
		)
	)

	for ed_repo_root in candidate_roots:
		if (ed_repo_root / "ifitwala_ed" / "integrations" / "drive" / "workflow_specs.py").exists():
			return ed_repo_root

	searched = ", ".join(str(path) for path in candidate_roots)
	raise AssertionError(
		f"Ifitwala_Ed repo not found. Set IFITWALA_ED_REPO or provide a sibling checkout. Searched: {searched}"
	)


class FakeFrappeError(Exception):
	pass


class FakeDoc:
	_insert_count = 0
	_inserted_docs: ClassVar[list["FakeDoc"]] = []

	def __init__(self, data: dict[str, Any] | None = None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def get(self, key: str, default: Any = None) -> Any:
		return getattr(self, key, default)

	def insert(self, ignore_permissions: bool = False):
		if not getattr(self, "name", None):
			FakeDoc._insert_count += 1
			self.name = f"DUS-{FakeDoc._insert_count:04d}"
		FakeDoc._inserted_docs.append(self)
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
	FakeDoc._inserted_docs = []
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
		"expense_claim.receipt",
		"default",
		_contract(
			owner_doctype="Expense Claim",
			owner_name="EXP-0001",
			primary_subject_type="Employee",
			primary_subject_id="EMP-0001",
			data_class="financial",
			purpose="administrative",
			retention_policy="fixed_7y",
			slot="expense_claim_receipt__row_0001",
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
		"student_referral.attachment",
		"default",
		_contract(
			owner_doctype="Student Referral",
			owner_name="SRF-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="safeguarding",
			purpose="safeguarding_evidence",
			retention_policy="fixed_7y",
			slot="student_referral_attachment__row_0001",
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

EXPECTED_WRAPPER_WORKFLOWS: dict[str, str] = {
	"upload_applicant_document_service": "admissions.applicant_document",
	"upload_applicant_guardian_image_service": "admissions.applicant_guardian_image",
	"upload_applicant_health_vaccination_proof_service": "admissions.applicant_health_vaccination",
	"upload_applicant_profile_image_service": "admissions.applicant_profile_image",
	"upload_employee_image_service": "media.employee_profile_image",
	"upload_guardian_image_service": "media.guardian_profile_image",
	"upload_org_communication_attachment_service": "org_communication.attachment",
	"upload_organization_logo_service": "organization_media.organization_logo",
	"upload_organization_media_asset_service": "organization_media.asset",
	"upload_school_gallery_image_service": "organization_media.school_gallery_image",
	"upload_school_logo_service": "organization_media.school_logo",
	"upload_student_image_service": "media.student_profile_image",
	"upload_student_log_evidence_attachment_service": "student_log.evidence_attachment",
	"upload_supporting_material_service": "supporting_material.file",
	"upload_task_submission_artifact_service": "task.submission",
}

ALLOWED_ED_INTERNAL_DRIVE_IMPORTS: dict[str, set[str]] = {
	"ifitwala_ed/admission/doctype/student_applicant/student_applicant.py": {
		"ifitwala_drive.services.storage.base",
	},
	"ifitwala_ed/utilities/image_utils.py": {
		"ifitwala_drive.services.storage.base",
	},
}

ALLOWED_DRIVE_ED_IMPORTS: dict[str, set[str]] = {
	"ifitwala_drive/ifitwala_drive/doctype/drive_upload_session/drive_upload_session.py": {
		"ifitwala_ed.utilities.governed_file_contract",
	},
	"ifitwala_drive/services/governance_contract.py": {
		"ifitwala_ed.utilities.governed_file_contract",
	},
	"ifitwala_drive/services/integration/ifitwala_ed_media.py": {
		"ifitwala_ed.utilities.organization_media",
	},
	"ifitwala_drive/services/uploads/validation.py": {
		"ifitwala_ed.utilities.governed_file_contract",
	},
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


def _drive_repo_root() -> Path:
	return Path(__file__).resolve().parents[2]


def _is_test_module_path(path: Path) -> bool:
	return path.name.startswith("test_") or path.name.endswith("_test.py")


def _iter_imported_modules(path: Path) -> list[tuple[int, str]]:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	imports: list[tuple[int, str]] = []

	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			imports.extend((node.lineno, alias.name) for alias in node.names)
			continue

		if isinstance(node, ast.ImportFrom) and node.module:
			imports.append((node.lineno, node.module))
			continue

		if isinstance(node, ast.Call) and node.args:
			func = node.func
			is_import_module = (
				isinstance(func, ast.Name)
				and func.id == "import_module"
				or isinstance(func, ast.Attribute)
				and func.attr == "import_module"
			)
			if is_import_module and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
				imports.append((node.lineno, node.args[0].value))

	return imports


def _is_same_or_child_module(module_name: str, parent_module: str) -> bool:
	return module_name == parent_module or module_name.startswith(f"{parent_module}.")


def _wrapper_workflows_from_source() -> dict[str, str]:
	wrappers: dict[str, str] = {}
	for path in sorted(
		(_drive_repo_root() / "ifitwala_drive" / "services" / "integration").glob("ifitwala_ed_*.py")
	):
		tree = ast.parse(path.read_text())
		for node in tree.body:
			if not isinstance(node, ast.FunctionDef):
				continue
			if not node.name.startswith("upload_") or not node.name.endswith("_service"):
				continue
			for child in ast.walk(node):
				if not isinstance(child, ast.Assign):
					continue
				if not any(
					isinstance(target, ast.Name) and target.id == "workflow_id" for target in child.targets
				):
					continue
				if isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
					wrappers[node.name] = child.value.value
	return wrappers


def _without_allowed_internal_derivative_doc_section(path: Path, text: str) -> str:
	if path.name not in {
		"08_cross_portal_preview_contract.md",
		"21_cross_portal_governed_attachment_preview_contract.md",
	}:
		return text
	start_marker = "## Internal Architecture: Data Model Direction"
	end_marker = "Recommended statuses:"
	start = text.find(start_marker)
	end = text.find(end_marker, start)
	if start == -1 or end == -1:
		return text
	return text[:start] + text[end:]


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


def test_workflow_backed_slot_validation_is_shape_based_not_registry_based():
	_install_fake_frappe()
	validation = importlib.import_module("ifitwala_drive.services.uploads.validation")
	payload = {
		**_contract(
			owner_doctype="Task Submission",
			owner_name="TSUB-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="assessment",
			purpose="assessment_submission",
			retention_policy="until_school_exit_plus_6m",
			slot="future_workflow_slot__row_001",
		),
		"workflow_id": "future.workflow",
		"contract_version": "1",
		"filename_original": "future.pdf",
	}

	validation.validate_create_session_payload(payload)


def test_path_shaped_workflow_slot_is_rejected():
	_install_fake_frappe()
	validation = importlib.import_module("ifitwala_drive.services.uploads.validation")
	payload = {
		**_contract(
			owner_doctype="Task Submission",
			owner_name="TSUB-0001",
			primary_subject_type="Student",
			primary_subject_id="STU-0001",
			data_class="assessment",
			purpose="assessment_submission",
			retention_policy="until_school_exit_plus_6m",
			slot="../private/student/passport",
		),
		"workflow_id": "task.submission",
		"contract_version": "1",
		"filename_original": "unsafe.pdf",
	}

	with pytest.raises(FakeFrappeError, match="Slot must be a workflow-resolved key"):
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

	assert len(FakeDoc._inserted_docs) == 1
	session_doc = FakeDoc._inserted_docs[0]
	stored_contract = json.loads(session_doc.upload_contract_json)
	workflow = stored_contract["workflow"]
	assert workflow["workflow_id"] == workflow_id
	assert workflow["contract_version"] == "1"
	assert workflow["workflow_payload"] == {"sample_name": sample_name}
	assert workflow["workflow_result"] == {}
	for fieldname, expected_value in _contract.items():
		session_field = {
			"primary_subject_type": "intended_primary_subject_type",
			"primary_subject_id": "intended_primary_subject_id",
			"data_class": "intended_data_class",
			"purpose": "intended_purpose",
			"retention_policy": "intended_retention_policy",
			"slot": "intended_slot",
		}.get(fieldname, fieldname)
		assert getattr(session_doc, session_field) == expected_value


def test_upload_sessions_expose_one_public_create_boundary():
	_install_fake_frappe()
	_install_fake_storage()
	_install_fake_logging()
	_install_fake_bridge()

	sessions = importlib.import_module("ifitwala_drive.services.uploads.sessions")

	assert callable(getattr(sessions, "create_upload_session_service", None))
	assert not hasattr(sessions, "create_resolved_upload_session_service")


def test_ed_runtime_code_uses_drive_public_api_boundary():
	ed_repo_root = _find_ed_repo_root()
	failures: list[str] = []

	for path in sorted((ed_repo_root / "ifitwala_ed").rglob("*.py")):
		if _is_test_module_path(path):
			continue

		relative_path = path.relative_to(ed_repo_root).as_posix()
		allowed_modules = ALLOWED_ED_INTERNAL_DRIVE_IMPORTS.get(relative_path, set())
		for line_number, module_name in _iter_imported_modules(path):
			if not _is_same_or_child_module(module_name, "ifitwala_drive"):
				continue

			if _is_same_or_child_module(module_name, "ifitwala_drive.api"):
				continue

			if any(_is_same_or_child_module(module_name, allowed) for allowed in allowed_modules):
				continue

			failures.append(f"{relative_path}:{line_number} imports {module_name}")

	assert failures == []


def test_drive_runtime_code_uses_approved_ed_boundary_modules():
	drive_repo_root = _drive_repo_root()
	failures: list[str] = []

	for path in sorted((drive_repo_root / "ifitwala_drive").rglob("*.py")):
		if "tests" in path.parts or _is_test_module_path(path):
			continue

		relative_path = path.relative_to(drive_repo_root).as_posix()
		allowed_modules = ALLOWED_DRIVE_ED_IMPORTS.get(relative_path, set())
		for line_number, module_name in _iter_imported_modules(path):
			if not _is_same_or_child_module(module_name, "ifitwala_ed"):
				continue

			if any(_is_same_or_child_module(module_name, allowed) for allowed in allowed_modules):
				continue

			failures.append(f"{relative_path}:{line_number} imports {module_name}")

	assert failures == []


def test_drive_wrapper_workflow_ids_are_valid_ed_specs():
	_install_fake_frappe()
	_ensure_ed_repo_on_path()
	workflow_specs = importlib.import_module("ifitwala_ed.integrations.drive.workflow_specs")
	known_workflows = {spec.workflow_id for spec in workflow_specs.iter_upload_specs()}
	wrapper_workflows = _wrapper_workflows_from_source()

	assert wrapper_workflows == EXPECTED_WRAPPER_WORKFLOWS
	assert set(wrapper_workflows.values()) <= known_workflows


def test_drive_docs_keep_derivative_role_names_inside_internal_architecture_sections():
	docs_root = _drive_repo_root() / "ifitwala_drive" / "docs"
	forbidden_snippets = ("`thumb`", "`card`", "`viewer_preview`", "`pdf_card`", "`derivative_role`")
	failures: list[str] = []

	for path in sorted(docs_root.rglob("*.md")):
		text = _without_allowed_internal_derivative_doc_section(path, path.read_text())
		for snippet in forbidden_snippets:
			if snippet in text:
				failures.append(f"{path.relative_to(_drive_repo_root())} contains {snippet}")

	assert failures == []


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
