from __future__ import annotations

import importlib
import sys
import types


class FakeDoc:
	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)
		self.saved = 0

	def check_permission(self, permission_type=None):
		return None

	def append(self, fieldname, row):
		rows = getattr(self, fieldname, None)
		if rows is None:
			rows = []
			setattr(self, fieldname, rows)
		child = types.SimpleNamespace(**row)
		rows.append(child)
		return child

	def save(self, ignore_permissions=False):
		self.saved += 1
		return self


def _normalize_key_part(value):
	if isinstance(value, dict):
		return tuple(sorted((key, _normalize_key_part(item)) for key, item in value.items()))
	if isinstance(value, list):
		return tuple(_normalize_key_part(item) for item in value)
	if isinstance(value, tuple):
		return tuple(_normalize_key_part(item) for item in value)
	return value


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


def _install_fake_frappe(*, exists_map=None, value_map=None, docs_map=None):
	exists_map = exists_map or {}
	value_map = value_map or {}
	docs_map = docs_map or {}
	db_set_calls = []

	class FakeDB:
		def exists(self, doctype, name=None):
			key = (doctype, _normalize_key_part(name))
			if key in exists_map:
				return exists_map[key]
			if isinstance(name, dict):
				return exists_map.get((doctype, _normalize_key_part(name)), False)
			return (doctype, name) in docs_map

		def get_value(self, doctype, name, fieldname=None, as_dict=False):
			key = (
				doctype,
				_normalize_key_part(name),
				_normalize_key_part(fieldname),
				as_dict,
			)
			if key in value_map:
				return value_map[key]
			key = (
				doctype,
				_normalize_key_part(name),
				_normalize_key_part(fieldname),
			)
			if key in value_map:
				return value_map[key]
			doc = docs_map.get((doctype, name))
			if doc is None:
				return None
			if isinstance(fieldname, (list, tuple)):
				if as_dict:
					return {field: getattr(doc, field, None) for field in fieldname}
				return [getattr(doc, field, None) for field in fieldname]
			return getattr(doc, fieldname, None)

		def set_value(self, doctype, name, values, fieldname=None, update_modified=False):
			db_set_calls.append((doctype, name, values, fieldname))
			return None

	def _throw(message, exc=None):
		raise RuntimeError(message)

	def _get_doc(doctype, name=None):
		if isinstance(doctype, dict):
			return FakeDoc(doctype)
		return docs_map[(doctype, name)]

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.db = FakeDB()
	frappe.get_doc = _get_doc
	frappe.session = types.SimpleNamespace(user="tester@example.com")
	frappe.generate_hash = lambda length=10: "x" * length
	frappe.scrub = lambda value: str(value or "").strip().lower().replace(" ", "_")
	frappe.as_json = lambda value, indent=None: str(value)
	frappe.logger = lambda: types.SimpleNamespace(info=lambda *a, **k: None)
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.local = types.SimpleNamespace(request_ip="127.0.0.1")
	frappe.bold = lambda value: str(value)

	sys.modules["frappe"] = frappe
	return db_set_calls


def _install_fake_sessions(recorder):
	module = types.ModuleType("ifitwala_drive.services.uploads.sessions")

	def create_upload_session_service(payload):
		recorder["payload"] = payload
		return {"upload_session_id": "DUS-0001", "status": "created"}

	module.create_upload_session_service = create_upload_session_service
	sys.modules["ifitwala_drive.services.uploads.sessions"] = module


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def test_upload_student_image_uses_authoritative_contract():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_drive.services.uploads.sessions",
	)
	student = FakeDoc({"name": "STU-0001", "anchor_school": "SCH-0001"})
	_install_fake_frappe(
		exists_map={("Student", "STU-0001"): True},
		value_map={("School", "SCH-0001", "organization"): "ORG-0001"},
		docs_map={("Student", "STU-0001"): student},
	)
	recorder = {}
	_install_fake_sessions(recorder)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")

	response = module.upload_student_image_service(
		{
			"student": "STU-0001",
			"filename_original": "student.jpg",
			"mime_type_hint": "image/jpeg",
			"expected_size_bytes": 123,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert recorder["payload"]["owner_doctype"] == "Student"
	assert recorder["payload"]["primary_subject_id"] == "STU-0001"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["slot"] == "profile_image"
	assert recorder["payload"]["is_private"] == 0


def test_upload_organization_logo_keeps_organization_as_owner():
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_drive.services.uploads.sessions",
	)
	org = FakeDoc({"name": "ORG-0001"})
	_install_fake_frappe(
		exists_map={("Organization", "ORG-0001"): True},
		docs_map={("Organization", "ORG-0001"): org},
	)
	recorder = {}
	_install_fake_sessions(recorder)

	organization_media = types.ModuleType("ifitwala_ed.utilities.organization_media")
	organization_media.build_organization_logo_slot = lambda organization: (
		f"organization_logo__{organization.lower()}"
	)
	organization_media.build_organization_media_classification = lambda **kwargs: {
		"primary_subject_type": "Organization",
		"primary_subject_id": kwargs["organization"],
		"data_class": "operational",
		"purpose": "organization_public_media",
		"retention_policy": "immediate_on_request",
		"slot": kwargs["slot"],
	}
	sys.modules["ifitwala_ed.utilities.organization_media"] = organization_media

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")
	module.upload_organization_logo_service(
		{
			"organization": "ORG-0001",
			"filename_original": "logo.png",
		}
	)

	assert recorder["payload"]["owner_doctype"] == "Organization"
	assert recorder["payload"]["owner_name"] == "ORG-0001"
	assert recorder["payload"]["attached_doctype"] == "Organization"
	assert recorder["payload"]["slot"] == "organization_logo__org-0001"


def test_upload_applicant_document_builds_item_scoped_session():
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_admissions",
		"ifitwala_drive.services.uploads.sessions",
	)
	_install_fake_frappe(
		value_map={
			("Applicant Document Type", "Passport", "code"): "passport",
			(
				"Student Applicant",
				"APP-0001",
				("organization", "school"),
				True,
			): {"organization": "ORG-0001", "school": "SCH-0001"},
		}
	)
	recorder = {}
	_install_fake_sessions(recorder)

	admissions_portal = types.ModuleType("ifitwala_ed.admission.admissions_portal")
	admissions_portal._resolve_applicant_document = lambda **kwargs: types.SimpleNamespace(
		name="ADOC-0001",
		student_applicant="APP-0001",
		document_type="Passport",
	)
	admissions_portal._resolve_applicant_document_item = lambda **kwargs: types.SimpleNamespace(
		name="ADI-0001",
		item_key="passport_copy",
		item_label="Passport Copy",
	)
	sys.modules["ifitwala_ed.admission.admissions_portal"] = admissions_portal
	admission_pkg = types.ModuleType("ifitwala_ed.admission")
	admission_pkg.admissions_portal = admissions_portal
	sys.modules["ifitwala_ed.admission"] = admission_pkg

	admission_utils = types.ModuleType("ifitwala_ed.admission.admission_utils")
	admission_utils.get_applicant_document_slot_spec = lambda **kwargs: {
		"slot": "identity_passport",
		"data_class": "legal",
		"purpose": "identification_document",
		"retention_policy": "until_school_exit_plus_6m",
	}
	sys.modules["ifitwala_ed.admission.admission_utils"] = admission_utils
	admission_pkg.admission_utils = admission_utils

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")
	response = module.upload_applicant_document_service(
		{
			"student_applicant": "APP-0001",
			"document_type": "Passport",
			"filename_original": "passport.pdf",
		}
	)

	assert response["applicant_document_item"] == "ADI-0001"
	assert recorder["payload"]["attached_doctype"] == "Applicant Document Item"
	assert recorder["payload"]["attached_name"] == "ADI-0001"
	assert recorder["payload"]["slot"] == "identity_passport_passport_copy"


def test_upload_applicant_health_vaccination_proof_builds_profile_scoped_session():
	_purge_modules(
		"frappe",
		"ifitwala_ed",
		"ifitwala_drive.services.integration.ifitwala_ed_admissions",
		"ifitwala_drive.services.uploads.sessions",
	)
	_install_fake_frappe(
		value_map={
			(
				"Applicant Health Profile",
				"AHP-0001",
				("name", "student_applicant"),
				True,
			): {
				"name": "AHP-0001",
				"student_applicant": "APP-0001",
			},
			(
				"Student Applicant",
				"APP-0001",
				("organization", "school"),
				True,
			): {"organization": "ORG-0001", "school": "SCH-0001"},
		},
	)
	recorder = {}
	_install_fake_sessions(recorder)

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")
	response = module.upload_applicant_health_vaccination_proof_service(
		{
			"student_applicant": "APP-0001",
			"applicant_health_profile": "AHP-0001",
			"vaccine_name": "MMR",
			"date": "2020-03-04",
			"row_index": 0,
			"filename_original": "mmr-proof.png",
		}
	)

	assert response["applicant_health_profile"] == "AHP-0001"
	assert recorder["payload"]["owner_doctype"] == "Student Applicant"
	assert recorder["payload"]["owner_name"] == "APP-0001"
	assert recorder["payload"]["attached_doctype"] == "Applicant Health Profile"
	assert recorder["payload"]["attached_name"] == "AHP-0001"
	assert recorder["payload"]["slot"] == "health_vaccination_proof_mmr_2020-03-04"
	assert recorder["payload"]["is_private"] == 1


def test_get_admissions_attached_field_override_returns_vaccinations_for_health_uploads():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	_install_fake_frappe()
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	fieldname = module.get_admissions_attached_field_override(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			attached_doctype="Applicant Health Profile",
			intended_slot="health_vaccination_proof_mmr_2020-03-04",
		)
	)

	assert fieldname == "vaccinations"


def test_run_media_post_finalize_updates_student_image():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_media")
	student = FakeDoc({"name": "STU-0001", "anchor_school": "SCH-0001", "student_image": None})
	db_set_calls = _install_fake_frappe(docs_map={("Student", "STU-0001"): student})
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")

	class CreatedFile:
		name = "FILE-0001"
		file_url = "/private/files/student.jpg"

	response = module.run_media_post_finalize(
		types.SimpleNamespace(owner_doctype="Student", owner_name="STU-0001", intended_slot="profile_image"),
		CreatedFile(),
	)

	assert response["file_url"] == "/private/files/student.jpg"
	assert db_set_calls[0][0] == "Student"
	assert db_set_calls[0][2] == "student_image"


def test_run_admissions_post_finalize_resets_review_state():
	_purge_modules("frappe", "ifitwala_ed", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	db_set_calls = _install_fake_frappe(
		value_map={
			(
				"Applicant Document Item",
				"ADI-0001",
				("applicant_document", "item_key", "item_label"),
				True,
			): {
				"applicant_document": "ADOC-0001",
				"item_key": "passport_copy",
				"item_label": "Passport Copy",
			},
			("Applicant Document", "ADOC-0001", "document_type"): "Passport",
			("Applicant Document Type", "Passport", "code"): "passport",
			("File Classification", (("file", "FILE-0001"),), "name"): "FC-0001",
		}
	)

	admissions_portal = types.ModuleType("ifitwala_ed.admission.admissions_portal")
	admissions_portal._append_document_upload_timeline = lambda **kwargs: None
	sys.modules["ifitwala_ed.admission.admissions_portal"] = admissions_portal
	admission_pkg = types.ModuleType("ifitwala_ed.admission")
	admission_pkg.admissions_portal = admissions_portal
	sys.modules["ifitwala_ed.admission"] = admission_pkg

	review_workflow = types.ModuleType("ifitwala_ed.admission.applicant_review_workflow")
	review_workflow.materialize_document_item_review_assignments = lambda **kwargs: None
	sys.modules["ifitwala_ed.admission.applicant_review_workflow"] = review_workflow
	admission_pkg.applicant_review_workflow = review_workflow

	applicant_document = types.ModuleType(
		"ifitwala_ed.admission.doctype.applicant_document.applicant_document"
	)
	applicant_document.sync_applicant_document_review_from_items = lambda applicant_document=None: None
	sys.modules["ifitwala_ed.admission.doctype.applicant_document.applicant_document"] = applicant_document

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	class CreatedFile:
		name = "FILE-0001"
		file_url = "/private/files/passport.pdf"

	response = module.run_admissions_post_finalize(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Applicant Document Item",
			attached_name="ADI-0001",
			upload_source="SPA",
		),
		CreatedFile(),
	)

	assert response["classification"] == "FC-0001"
	assert response["applicant_document_item"] == "ADI-0001"
	assert db_set_calls[0][0] == "Applicant Document Item"


def test_run_admissions_post_finalize_returns_health_upload_metadata():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	_install_fake_frappe(
		value_map={
			("File Classification", (("file", "FILE-0001"),), "name"): "FC-0002",
		}
	)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	class CreatedFile:
		name = "FILE-0001"
		file_url = "/private/files/mmr-proof.png"

	response = module.run_admissions_post_finalize(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Applicant Health Profile",
			attached_name="AHP-0001",
			intended_slot="health_vaccination_proof_mmr_2020-03-04",
		),
		CreatedFile(),
	)

	assert response["classification"] == "FC-0002"
	assert response["file_url"] == "/private/files/mmr-proof.png"
	assert response["applicant_health_profile"] == "AHP-0001"
