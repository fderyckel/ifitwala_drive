from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import ClassVar


class FakeDoc:
	_insert_counters: ClassVar[dict[str, int]] = {}

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

	def insert(self, ignore_permissions=False):
		doctype = getattr(self, "doctype", "DocType")
		prefix_map = {
			"Drive Folder": "DRF",
		}
		prefix = prefix_map.get(doctype, "DOC")
		next_value = self._insert_counters.get(prefix, 0) + 1
		self._insert_counters[prefix] = next_value
		if not getattr(self, "name", None):
			self.name = f"{prefix}-{next_value:04d}"
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
		if (
			any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes)
			or module_name.startswith("ifitwala_drive.services.folders")
			or module_name == "ifitwala_drive.services.integration._ed_delegate"
			or module_name.startswith("ifitwala_drive.services.integration.ifitwala_ed_")
			or module_name == "ifitwala_ed"
			or module_name.startswith("ifitwala_ed.")
		):
			sys.modules.pop(module_name, None)
	FakeDoc._insert_counters = {}


def _ensure_ed_repo_on_path() -> None:
	ed_repo_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed"
	if ed_repo_root.exists():
		ed_repo_root_text = str(ed_repo_root)
		if ed_repo_root_text not in sys.path:
			sys.path.insert(0, ed_repo_root_text)
		return

	if "ifitwala_ed" in sys.modules:
		return

	_install_fake_ifitwala_ed()


def _install_fake_ifitwala_ed():
	import frappe

	ed_package_root = Path(__file__).resolve().parents[2].parent / "ifitwala_ed" / "ifitwala_ed"
	utilities_package_root = ed_package_root / "utilities"
	integrations_package_root = ed_package_root / "integrations"
	drive_integrations_package_root = integrations_package_root / "drive"
	admission_package_root = ed_package_root / "admission"
	api_package_root = ed_package_root / "api"

	profile_image_slot = "profile_image"
	guardian_profile_image_slot_prefix = "guardian_profile_image__"
	health_vaccination_slot_prefix = "health_vaccination_proof_"

	def _get_org_from_school(school: str) -> str:
		organization = frappe.db.get_value("School", school, "organization")
		if not organization:
			frappe.throw("Organization is required for file classification.")
		return organization

	def _build_employee_image_contract(employee_doc) -> dict[str, object]:
		return {
			"owner_doctype": "Employee",
			"owner_name": employee_doc.name,
			"attached_doctype": "Employee",
			"attached_name": employee_doc.name,
			"organization": getattr(employee_doc, "organization", None),
			"school": getattr(employee_doc, "school", None),
			"primary_subject_type": "Employee",
			"primary_subject_id": employee_doc.name,
			"data_class": "identity_image",
			"purpose": "employee_profile_display",
			"retention_policy": "employment_duration_plus_grace",
			"slot": profile_image_slot,
		}

	def _build_student_image_contract(student_doc) -> dict[str, object]:
		school = getattr(student_doc, "anchor_school", None)
		return {
			"owner_doctype": "Student",
			"owner_name": student_doc.name,
			"attached_doctype": "Student",
			"attached_name": student_doc.name,
			"organization": _get_org_from_school(school),
			"school": school,
			"primary_subject_type": "Student",
			"primary_subject_id": student_doc.name,
			"data_class": "identity_image",
			"purpose": "student_profile_display",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": profile_image_slot,
		}

	def _build_guardian_image_contract(guardian_doc) -> dict[str, object]:
		return {
			"owner_doctype": "Guardian",
			"owner_name": guardian_doc.name,
			"attached_doctype": "Guardian",
			"attached_name": guardian_doc.name,
			"organization": getattr(guardian_doc, "organization", None),
			"school": None,
			"primary_subject_type": "Guardian",
			"primary_subject_id": guardian_doc.name,
			"data_class": "identity_image",
			"purpose": "guardian_profile_display",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": profile_image_slot,
		}

	def _build_organization_media_contract(
		*,
		organization: str,
		slot: str,
		school: str | None = None,
		upload_source: str,
	) -> dict[str, object]:
		from ifitwala_ed.utilities.organization_media import build_organization_media_classification

		classification = build_organization_media_classification(
			organization=organization,
			school=school,
			slot=slot,
			upload_source=upload_source,
		)
		return {
			"owner_doctype": "Organization",
			"owner_name": organization,
			"attached_doctype": "Organization",
			"attached_name": organization,
			"organization": organization,
			"school": school,
			"primary_subject_type": classification["primary_subject_type"],
			"primary_subject_id": classification["primary_subject_id"],
			"data_class": classification["data_class"],
			"purpose": classification["purpose"],
			"retention_policy": classification["retention_policy"],
			"slot": classification["slot"],
		}

	def _build_health_vaccination_slot(
		*,
		vaccine_name: str | None,
		date_value: str | None,
		row_index: int | None = None,
	) -> str:
		base = "_".join(
			part for part in [(vaccine_name or "").strip(), (date_value or "").strip()] if part
		).strip()
		if not base:
			base = f"row_{int(row_index or 0) + 1}"
		return f"{health_vaccination_slot_prefix}{frappe.scrub(base)[:80]}"

	def _get_student_applicant_scope(student_applicant: str) -> dict[str, object]:
		applicant_row = (
			frappe.db.get_value(
				"Student Applicant",
				student_applicant,
				["organization", "school"],
				as_dict=True,
			)
			or {}
		)
		if not applicant_row.get("organization") or not applicant_row.get("school"):
			frappe.throw("Student Applicant must have organization and school.")
		return applicant_row

	def _get_applicant_document_context(payload: dict[str, object]) -> dict[str, object]:
		admission_api = importlib.import_module("ifitwala_ed.admission.admissions_portal")
		get_applicant_document_slot_spec = importlib.import_module(
			"ifitwala_ed.admission.admission_utils"
		).get_applicant_document_slot_spec

		doc = admission_api._resolve_applicant_document(
			applicant_document=payload.get("applicant_document"),
			student_applicant=payload.get("student_applicant"),
			document_type=payload.get("document_type"),
		)
		item_doc = admission_api._resolve_applicant_document_item(
			applicant_document=doc,
			applicant_document_item=payload.get("applicant_document_item"),
			item_key=payload.get("item_key"),
			item_label=payload.get("item_label"),
			fallback_label=payload.get("filename_original"),
		)
		document_type_code = (
			frappe.db.get_value("Applicant Document Type", doc.document_type, "code") or doc.document_type
		)
		slot_spec = get_applicant_document_slot_spec(
			document_type=doc.document_type,
			doc_type_code=document_type_code,
		)
		applicant_row = _get_student_applicant_scope(doc.student_applicant)
		return {
			"owner_doctype": "Student Applicant",
			"owner_name": doc.student_applicant,
			"attached_doctype": "Applicant Document Item",
			"attached_name": item_doc.name,
			"organization": applicant_row["organization"],
			"school": applicant_row["school"],
			"primary_subject_type": "Student Applicant",
			"primary_subject_id": doc.student_applicant,
			"data_class": slot_spec["data_class"],
			"purpose": slot_spec["purpose"],
			"retention_policy": slot_spec["retention_policy"],
			"slot": f"{slot_spec['slot']}_{frappe.scrub(item_doc.item_key)[:80]}",
			"applicant_document": doc.name,
			"applicant_document_item": item_doc.name,
			"item_key": item_doc.item_key,
			"item_label": item_doc.item_label,
			"document_type": doc.document_type,
			"document_type_code": document_type_code,
		}

	def _get_applicant_health_vaccination_context(payload: dict[str, object]) -> dict[str, object]:
		health_row = (
			frappe.db.get_value(
				"Applicant Health Profile",
				payload.get("applicant_health_profile"),
				["name", "student_applicant"],
				as_dict=True,
			)
			or {}
		)
		applicant_row = _get_student_applicant_scope(str(payload.get("student_applicant") or ""))
		return {
			"owner_doctype": "Student Applicant",
			"owner_name": payload.get("student_applicant"),
			"attached_doctype": "Applicant Health Profile",
			"attached_name": health_row["name"],
			"organization": applicant_row["organization"],
			"school": applicant_row["school"],
			"primary_subject_type": "Student Applicant",
			"primary_subject_id": payload.get("student_applicant"),
			"data_class": "safeguarding",
			"purpose": "medical_record",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": _build_health_vaccination_slot(
				vaccine_name=str(payload.get("vaccine_name") or ""),
				date_value=str(payload.get("date") or ""),
				row_index=payload.get("row_index"),
			),
		}

	def _get_applicant_profile_image_context(payload: dict[str, object]) -> dict[str, object]:
		applicant_row = _get_student_applicant_scope(str(payload.get("student_applicant") or ""))
		return {
			"owner_doctype": "Student Applicant",
			"owner_name": payload.get("student_applicant"),
			"attached_doctype": "Student Applicant",
			"attached_name": payload.get("student_applicant"),
			"organization": applicant_row["organization"],
			"school": applicant_row["school"],
			"primary_subject_type": "Student Applicant",
			"primary_subject_id": payload.get("student_applicant"),
			"data_class": "identity_image",
			"purpose": "applicant_profile_display",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": profile_image_slot,
		}

	def _get_applicant_guardian_image_context(payload: dict[str, object]) -> dict[str, object]:
		guardian_row_name = str(payload.get("guardian_row_name") or "")
		applicant_row = _get_student_applicant_scope(str(payload.get("student_applicant") or ""))
		return {
			"owner_doctype": "Student Applicant",
			"owner_name": payload.get("student_applicant"),
			"attached_doctype": "Student Applicant Guardian",
			"attached_name": guardian_row_name,
			"organization": applicant_row["organization"],
			"school": applicant_row["school"],
			"primary_subject_type": "Student Applicant",
			"primary_subject_id": payload.get("student_applicant"),
			"data_class": "identity_image",
			"purpose": "applicant_profile_display",
			"retention_policy": "until_school_exit_plus_6m",
			"slot": f"{guardian_profile_image_slot_prefix}{frappe.scrub(guardian_row_name)[:80]}",
		}

	def _get_admissions_attached_field_override(upload_session_doc) -> str | None:
		if (
			getattr(upload_session_doc, "owner_doctype", None) == "Student Applicant"
			and getattr(upload_session_doc, "attached_doctype", None) == "Applicant Health Profile"
			and str(getattr(upload_session_doc, "intended_slot", "") or "").startswith(
				health_vaccination_slot_prefix
			)
		):
			return "vaccinations"
		if (
			getattr(upload_session_doc, "owner_doctype", None) == "Student Applicant"
			and getattr(upload_session_doc, "attached_doctype", None) == "Student Applicant"
			and getattr(upload_session_doc, "intended_slot", None) == profile_image_slot
		):
			return "applicant_image"
		if (
			getattr(upload_session_doc, "owner_doctype", None) == "Student Applicant"
			and getattr(upload_session_doc, "attached_doctype", None) == "Student Applicant Guardian"
			and str(getattr(upload_session_doc, "intended_slot", "") or "").startswith(
				guardian_profile_image_slot_prefix
			)
		):
			return "guardian_image"
		return None

	def _get_drive_file_for_file(file_name: str):
		rows = frappe.get_all(
			"Drive File",
			fields=["name"],
			filters={"file": file_name},
			limit=1,
		)
		if not rows:
			frappe.throw(f"Drive File not found for File {file_name}")
		first_row = rows[0]
		drive_file_name = first_row["name"] if isinstance(first_row, dict) else first_row
		return frappe.get_doc("Drive File", drive_file_name)

	def _run_media_post_finalize(upload_session_doc, created_file) -> dict[str, object]:
		file_url = getattr(created_file, "file_url", None)
		if upload_session_doc.owner_doctype == "Employee":
			frappe.db.set_value(
				"Employee",
				upload_session_doc.owner_name,
				"employee_image",
				file_url,
				update_modified=False,
			)
			return {"file_url": file_url}
		if upload_session_doc.owner_doctype == "Student":
			frappe.db.set_value(
				"Student",
				upload_session_doc.owner_name,
				"student_image",
				file_url,
				update_modified=False,
			)
			invalidate_cache = getattr(
				importlib.import_module("ifitwala_ed.api.portal"),
				"invalidate_student_portal_identity_cache",
				None,
			)
			if callable(invalidate_cache):
				invalidate_cache(student=upload_session_doc.owner_name)
			return {"file_url": file_url}
		if upload_session_doc.owner_doctype == "Guardian":
			frappe.db.set_value(
				"Guardian",
				upload_session_doc.owner_name,
				{
					"guardian_image": file_url,
					"organization": upload_session_doc.organization,
				},
				update_modified=False,
			)
			return {"file_url": file_url}
		return {"file_url": file_url}

	def _run_admissions_post_finalize(upload_session_doc, created_file) -> dict[str, object]:
		drive_file_doc = _get_drive_file_for_file(created_file.name)
		response = {
			"drive_file_id": drive_file_doc.name,
			"canonical_ref": getattr(drive_file_doc, "canonical_ref", None),
		}
		file_url = getattr(created_file, "file_url", None)
		if file_url:
			response["file_url"] = file_url

		attached_doctype = getattr(upload_session_doc, "attached_doctype", None)
		intended_slot = str(getattr(upload_session_doc, "intended_slot", "") or "")
		if attached_doctype == "Applicant Document Item":
			frappe.db.set_value(
				"Applicant Document Item",
				upload_session_doc.attached_name,
				"review_status",
				None,
				update_modified=False,
			)
			response["applicant_document_item"] = upload_session_doc.attached_name
			return response
		if attached_doctype == "Student Applicant" and intended_slot == profile_image_slot:
			frappe.db.set_value(
				"Student Applicant",
				upload_session_doc.owner_name,
				"applicant_image",
				file_url,
				update_modified=False,
			)
			return response
		if attached_doctype == "Student Applicant Guardian" and intended_slot.startswith(
			guardian_profile_image_slot_prefix
		):
			frappe.db.set_value(
				"Student Applicant Guardian",
				upload_session_doc.attached_name,
				"guardian_image",
				file_url,
				update_modified=False,
			)
			response["guardian_row_name"] = upload_session_doc.attached_name
			return response
		if attached_doctype == "Applicant Health Profile" and intended_slot.startswith(
			health_vaccination_slot_prefix
		):
			response["applicant_health_profile"] = upload_session_doc.attached_name
			return response
		return response

	def _resolve_upload_session_context(
		workflow_id: str, workflow_payload: dict[str, object]
	) -> dict[str, object]:
		if workflow_id == "media.employee_profile_image":
			context = _build_employee_image_contract(
				frappe.get_doc("Employee", workflow_payload.get("employee"))
			)
			is_private = 1
		elif workflow_id == "media.student_profile_image":
			context = _build_student_image_contract(
				frappe.get_doc("Student", workflow_payload.get("student"))
			)
			is_private = 1
		elif workflow_id == "media.guardian_profile_image":
			context = _build_guardian_image_contract(
				frappe.get_doc("Guardian", workflow_payload.get("guardian"))
			)
			is_private = 1
		elif workflow_id == "organization_media.organization_logo":
			from ifitwala_ed.utilities.organization_media import build_organization_logo_slot

			context = _build_organization_media_contract(
				organization=str(workflow_payload.get("organization") or ""),
				slot=build_organization_logo_slot(str(workflow_payload.get("organization") or "")),
				school=None,
				upload_source=str(workflow_payload.get("upload_source") or "Desk"),
			)
			is_private = 0
		elif workflow_id == "admissions.applicant_document":
			context = _get_applicant_document_context(workflow_payload)
			is_private = 1
		elif workflow_id == "admissions.applicant_profile_image":
			context = _get_applicant_profile_image_context(workflow_payload)
			is_private = 1
		elif workflow_id == "admissions.applicant_guardian_image":
			context = _get_applicant_guardian_image_context(workflow_payload)
			is_private = 1
		elif workflow_id == "admissions.applicant_health_vaccination":
			context = _get_applicant_health_vaccination_context(workflow_payload)
			is_private = 1
		else:
			raise RuntimeError(f"unexpected workflow_id: {workflow_id}")

		return {
			**context,
			"workflow_id": workflow_id,
			"contract_version": "1",
			"is_private": is_private,
		}

	organization_media = sys.modules.get("ifitwala_ed.utilities.organization_media")
	if organization_media is None:
		organization_media = types.ModuleType("ifitwala_ed.utilities.organization_media")
		organization_media.build_organization_logo_slot = lambda organization: (
			f"organization_logo__{frappe.scrub(organization)[:80]}"
		)
		organization_media.build_organization_media_classification = lambda **kwargs: {
			"primary_subject_type": "Organization",
			"primary_subject_id": kwargs["organization"],
			"data_class": "operational",
			"purpose": "organization_public_media",
			"retention_policy": "immediate_on_request",
			"slot": kwargs["slot"],
		}

	api_portal = sys.modules.get("ifitwala_ed.api.portal")
	if api_portal is None:
		api_portal = types.ModuleType("ifitwala_ed.api.portal")
		api_portal.invalidate_student_portal_identity_cache = lambda **kwargs: None

	admissions_portal = sys.modules.get("ifitwala_ed.admission.admissions_portal")
	if admissions_portal is None:
		admissions_portal = types.ModuleType("ifitwala_ed.admission.admissions_portal")
		admissions_portal._resolve_applicant_document = lambda **kwargs: (_ for _ in ()).throw(
			RuntimeError("Applicant document test delegate is not installed.")
		)
		admissions_portal._resolve_applicant_document_item = lambda **kwargs: (_ for _ in ()).throw(
			RuntimeError("Applicant document test delegate is not installed.")
		)

	admission_utils = sys.modules.get("ifitwala_ed.admission.admission_utils")
	if admission_utils is None:
		admission_utils = types.ModuleType("ifitwala_ed.admission.admission_utils")
		admission_utils.get_applicant_document_slot_spec = lambda **kwargs: {
			"slot": "identity_document",
			"data_class": "legal",
			"purpose": "identification_document",
			"retention_policy": "until_school_exit_plus_6m",
		}

	media = types.ModuleType("ifitwala_ed.integrations.drive.media")
	media.build_employee_image_contract = _build_employee_image_contract
	media.build_student_image_contract = _build_student_image_contract
	media.build_guardian_image_contract = _build_guardian_image_contract
	media.build_organization_media_contract = _build_organization_media_contract
	media.run_media_post_finalize = _run_media_post_finalize

	admissions = types.ModuleType("ifitwala_ed.integrations.drive.admissions")
	admissions.get_applicant_document_context = _get_applicant_document_context
	admissions.get_applicant_health_vaccination_context = _get_applicant_health_vaccination_context
	admissions.get_applicant_profile_image_context = _get_applicant_profile_image_context
	admissions.get_applicant_guardian_image_context = _get_applicant_guardian_image_context
	admissions.get_admissions_attached_field_override = _get_admissions_attached_field_override
	admissions.run_admissions_post_finalize = _run_admissions_post_finalize

	bridge = types.ModuleType("ifitwala_ed.integrations.drive.bridge")
	bridge.resolve_upload_session_context = _resolve_upload_session_context

	utilities = sys.modules.get("ifitwala_ed.utilities") or types.ModuleType("ifitwala_ed.utilities")
	utilities.__path__ = [str(utilities_package_root)]
	utilities.organization_media = organization_media

	admission = sys.modules.get("ifitwala_ed.admission") or types.ModuleType("ifitwala_ed.admission")
	admission.__path__ = [str(admission_package_root)]
	admission.admissions_portal = admissions_portal
	admission.admission_utils = admission_utils

	api = sys.modules.get("ifitwala_ed.api") or types.ModuleType("ifitwala_ed.api")
	api.__path__ = [str(api_package_root)]
	api.portal = api_portal

	integrations = sys.modules.get("ifitwala_ed.integrations") or types.ModuleType("ifitwala_ed.integrations")
	integrations.__path__ = [str(integrations_package_root)]
	drive_integrations = sys.modules.get("ifitwala_ed.integrations.drive") or types.ModuleType(
		"ifitwala_ed.integrations.drive"
	)
	drive_integrations.__path__ = [str(drive_integrations_package_root)]
	drive_integrations.bridge = bridge
	drive_integrations.media = media
	drive_integrations.admissions = admissions
	integrations.drive = drive_integrations

	ifitwala_ed = sys.modules.get("ifitwala_ed") or types.ModuleType("ifitwala_ed")
	ifitwala_ed.__path__ = [str(ed_package_root)]
	ifitwala_ed.utilities = utilities
	ifitwala_ed.admission = admission
	ifitwala_ed.api = api
	ifitwala_ed.integrations = integrations

	sys.modules["ifitwala_ed"] = ifitwala_ed
	sys.modules["ifitwala_ed.utilities"] = utilities
	sys.modules["ifitwala_ed.utilities.organization_media"] = organization_media
	sys.modules["ifitwala_ed.admission"] = admission
	sys.modules["ifitwala_ed.admission.admissions_portal"] = admissions_portal
	sys.modules["ifitwala_ed.admission.admission_utils"] = admission_utils
	sys.modules["ifitwala_ed.api"] = api
	sys.modules["ifitwala_ed.api.portal"] = api_portal
	sys.modules["ifitwala_ed.integrations"] = integrations
	sys.modules["ifitwala_ed.integrations.drive"] = drive_integrations
	sys.modules["ifitwala_ed.integrations.drive.bridge"] = bridge
	sys.modules["ifitwala_ed.integrations.drive.media"] = media
	sys.modules["ifitwala_ed.integrations.drive.admissions"] = admissions


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
			if isinstance(name, dict):
				return None
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
	frappe.get_all = lambda doctype, fields=None, filters=None, order_by=None, limit=None, pluck=None: [
		candidate_name
		if pluck == "name"
		else (
			getattr(doc, pluck, None)
			if pluck
			else {field: getattr(doc, field, None) for field in (fields or [])}
		)
		for (candidate_doctype, candidate_name), doc in docs_map.items()
		if candidate_doctype == doctype
		and (
			not filters
			or all(
				(
					getattr(doc, fieldname, None) in value[1]
					if isinstance(value, list) and len(value) == 2 and value[0] == "in"
					else getattr(doc, fieldname, None) != value[1]
					if isinstance(value, list) and len(value) == 2 and value[0] == "!="
					else getattr(doc, fieldname, None) == value
				)
				for fieldname, value in filters.items()
			)
		)
	][: limit or None]

	sys.modules["frappe"] = frappe
	frappe_utils = types.ModuleType("frappe.utils")
	frappe_utils.now_datetime = lambda: None
	sys.modules["frappe.utils"] = frappe_utils
	return db_set_calls


def _install_fake_sessions(recorder):
	module = types.ModuleType("ifitwala_drive.services.uploads.sessions")

	def create_upload_session_service(payload):
		recorder["payload"] = payload
		return {
			"upload_session_id": "DUS-0001",
			"status": "created",
			"workflow_result": payload.get("workflow_result") or {},
		}

	module.create_upload_session_service = create_upload_session_service
	sys.modules["ifitwala_drive.services.uploads.sessions"] = module


def _load_module(module_name: str):
	_ensure_ed_repo_on_path()
	return importlib.import_module(module_name)


def test_media_api_exports_expected_wrappers_and_delegates():
	_purge_modules(
		"frappe",
		"ifitwala_drive.api.media",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
	)
	_install_fake_frappe()
	recorder = []

	def _service(name):
		def _inner(payload):
			recorder.append((name, payload))
			return {"status": "ok", "wrapper": name}

		return _inner

	integration_module = types.ModuleType("ifitwala_drive.services.integration.ifitwala_ed_media")
	for method_name in (
		"issue_employee_image_download_grant",
		"issue_employee_image_preview_grant",
		"request_employee_image_preview_derivatives",
		"issue_guardian_image_download_grant",
		"issue_guardian_image_preview_grant",
		"request_guardian_image_preview_derivatives",
		"issue_public_employee_image_preview_grant",
		"issue_public_website_media_download_grant",
		"issue_public_website_media_preview_grant",
		"issue_student_image_download_grant",
		"issue_student_image_preview_grant",
		"request_student_image_preview_derivatives",
		"upload_employee_image",
		"upload_guardian_image",
		"upload_student_image",
		"upload_organization_logo",
		"upload_school_logo",
		"upload_school_gallery_image",
		"upload_organization_media_asset",
	):
		setattr(integration_module, f"{method_name}_service", _service(method_name))
	sys.modules["ifitwala_drive.services.integration.ifitwala_ed_media"] = integration_module

	module = _load_module("ifitwala_drive.api.media")
	assert (
		module.issue_employee_image_download_grant(
			employee="EMP-0001",
			file_id="FILE-EMP-1",
		)["wrapper"]
		== "issue_employee_image_download_grant"
	)
	assert (
		module.issue_employee_image_preview_grant(
			employee="EMP-0001",
			file_id="FILE-EMP-1",
			derivative_role="thumb",
		)["wrapper"]
		== "issue_employee_image_preview_grant"
	)
	assert (
		module.request_employee_image_preview_derivatives(
			employee="EMP-0001",
			file_id="FILE-EMP-1",
			derivative_roles=["thumb", "card"],
		)["wrapper"]
		== "request_employee_image_preview_derivatives"
	)
	assert (
		module.issue_guardian_image_download_grant(
			guardian="GRD-0001",
			file_id="FILE-GRD-1",
		)["wrapper"]
		== "issue_guardian_image_download_grant"
	)
	assert (
		module.issue_guardian_image_preview_grant(
			guardian="GRD-0001",
			file_id="FILE-GRD-1",
			derivative_role="thumb",
		)["wrapper"]
		== "issue_guardian_image_preview_grant"
	)
	assert (
		module.request_guardian_image_preview_derivatives(
			guardian="GRD-0001",
			file_id="FILE-GRD-1",
			derivative_roles=["thumb", "card"],
		)["wrapper"]
		== "request_guardian_image_preview_derivatives"
	)
	assert (
		module.issue_public_employee_image_preview_grant(
			employee="EMP-0001",
			file_id="FILE-EMP-1",
			derivative_role="card",
		)["wrapper"]
		== "issue_public_employee_image_preview_grant"
	)
	assert (
		module.issue_public_website_media_download_grant(
			file_id="FILE-PUBLIC-1",
		)["wrapper"]
		== "issue_public_website_media_download_grant"
	)
	assert (
		module.issue_public_website_media_preview_grant(
			file_id="FILE-PUBLIC-1",
			derivative_role="viewer_preview",
		)["wrapper"]
		== "issue_public_website_media_preview_grant"
	)
	assert (
		module.issue_student_image_download_grant(
			student="STU-0001",
			file_id="FILE-STU-1",
		)["wrapper"]
		== "issue_student_image_download_grant"
	)
	assert (
		module.issue_student_image_preview_grant(
			student="STU-0001",
			file_id="FILE-STU-1",
			derivative_role="thumb",
		)["wrapper"]
		== "issue_student_image_preview_grant"
	)
	assert (
		module.request_student_image_preview_derivatives(
			student="STU-0001",
			file_id="FILE-STU-1",
			derivative_roles=["thumb", "card", "viewer_preview"],
		)["wrapper"]
		== "request_student_image_preview_derivatives"
	)
	assert (
		module.upload_employee_image(
			employee="EMP-0001",
			filename_original="employee.jpg",
			expected_size_bytes=100,
			idempotency_key="retry-employee-001",
		)["wrapper"]
		== "upload_employee_image"
	)
	assert (
		module.upload_guardian_image(
			guardian="GRD-0001",
			filename_original="guardian.jpg",
		)["wrapper"]
		== "upload_guardian_image"
	)
	assert (
		module.upload_student_image(
			student="STU-0001",
			filename_original="student.jpg",
		)["wrapper"]
		== "upload_student_image"
	)
	assert (
		module.upload_organization_logo(
			organization="ORG-0001",
			filename_original="logo.png",
		)["wrapper"]
		== "upload_organization_logo"
	)
	assert (
		module.upload_school_logo(
			school="SCH-0001",
			filename_original="logo.png",
		)["wrapper"]
		== "upload_school_logo"
	)
	assert (
		module.upload_school_gallery_image(
			school="SCH-0001",
			filename_original="gallery.jpg",
			row_name="ROW-0001",
			caption="Hero",
		)["wrapper"]
		== "upload_school_gallery_image"
	)
	assert (
		module.upload_organization_media_asset(
			filename_original="asset.jpg",
			organization="ORG-0001",
			scope="organization",
			media_key="homepage_hero",
		)["wrapper"]
		== "upload_organization_media_asset"
	)

	assert recorder == [
		(
			"issue_employee_image_download_grant",
			{
				"employee": "EMP-0001",
				"file_id": "FILE-EMP-1",
			},
		),
		(
			"issue_employee_image_preview_grant",
			{
				"employee": "EMP-0001",
				"file_id": "FILE-EMP-1",
				"derivative_role": "thumb",
			},
		),
		(
			"request_employee_image_preview_derivatives",
			{
				"employee": "EMP-0001",
				"file_id": "FILE-EMP-1",
				"derivative_roles": ["thumb", "card"],
			},
		),
		(
			"issue_guardian_image_download_grant",
			{
				"guardian": "GRD-0001",
				"file_id": "FILE-GRD-1",
			},
		),
		(
			"issue_guardian_image_preview_grant",
			{
				"guardian": "GRD-0001",
				"file_id": "FILE-GRD-1",
				"derivative_role": "thumb",
			},
		),
		(
			"request_guardian_image_preview_derivatives",
			{
				"guardian": "GRD-0001",
				"file_id": "FILE-GRD-1",
				"derivative_roles": ["thumb", "card"],
			},
		),
		(
			"issue_public_employee_image_preview_grant",
			{
				"employee": "EMP-0001",
				"file_id": "FILE-EMP-1",
				"derivative_role": "card",
			},
		),
		(
			"issue_public_website_media_download_grant",
			{
				"file_id": "FILE-PUBLIC-1",
			},
		),
		(
			"issue_public_website_media_preview_grant",
			{
				"file_id": "FILE-PUBLIC-1",
				"derivative_role": "viewer_preview",
			},
		),
		(
			"issue_student_image_download_grant",
			{
				"student": "STU-0001",
				"file_id": "FILE-STU-1",
			},
		),
		(
			"issue_student_image_preview_grant",
			{
				"student": "STU-0001",
				"file_id": "FILE-STU-1",
				"derivative_role": "thumb",
			},
		),
		(
			"request_student_image_preview_derivatives",
			{
				"student": "STU-0001",
				"file_id": "FILE-STU-1",
				"derivative_roles": ["thumb", "card", "viewer_preview"],
			},
		),
		(
			"upload_employee_image",
			{
				"employee": "EMP-0001",
				"filename_original": "employee.jpg",
				"expected_size_bytes": 100,
				"idempotency_key": "retry-employee-001",
			},
		),
		(
			"upload_guardian_image",
			{
				"guardian": "GRD-0001",
				"filename_original": "guardian.jpg",
			},
		),
		(
			"upload_student_image",
			{
				"student": "STU-0001",
				"filename_original": "student.jpg",
			},
		),
		(
			"upload_organization_logo",
			{
				"organization": "ORG-0001",
				"filename_original": "logo.png",
			},
		),
		(
			"upload_school_logo",
			{
				"school": "SCH-0001",
				"filename_original": "logo.png",
			},
		),
		(
			"upload_school_gallery_image",
			{
				"school": "SCH-0001",
				"filename_original": "gallery.jpg",
				"row_name": "ROW-0001",
				"caption": "Hero",
			},
		),
		(
			"upload_organization_media_asset",
			{
				"filename_original": "asset.jpg",
				"organization": "ORG-0001",
				"scope": "organization",
				"media_key": "homepage_hero",
			},
		),
	]


def test_public_website_media_grant_services_use_delegate_scoped_access():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_ed.integrations.drive.media",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-PUBLIC-1",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"purpose": "organization_public_media",
			"status": "active",
			"preview_status": "ready",
		}
	)
	_install_fake_frappe(
		exists_map={
			("Drive File", "DF-PUBLIC-1"): True,
		},
		docs_map={("Drive File", "DF-PUBLIC-1"): drive_file},
	)
	_ensure_ed_repo_on_path()
	importlib.import_module("ifitwala_ed")
	importlib.import_module("ifitwala_ed.integrations")
	importlib.import_module("ifitwala_ed.integrations.drive")
	delegate_calls = []
	delegate = types.ModuleType("ifitwala_ed.integrations.drive.media")
	delegate.assert_public_website_media_read_access = lambda *, file_name: (
		delegate_calls.append(file_name)
		or {
			"file_id": "FILE-PUBLIC-1",
			"drive_file_id": "DF-PUBLIC-1",
			"organization": "ORG-0001",
		}
	)
	sys.modules["ifitwala_ed.integrations.drive.media"] = delegate

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")
	access_module = importlib.import_module("ifitwala_drive.services.files.access")
	preview_docs = []
	download_docs = []
	grant_calls = []

	def _fake_issue_preview_grant_for_doc(*, doc, payload=None):
		if str((payload or {}).get("derivative_role") or "").strip():
			download_docs.append(doc.name)
		else:
			preview_docs.append(doc.name)
		grant_calls.append(
			{
				"doc": doc.name,
				"grant_kind": "preview",
				"payload": payload,
			}
		)
		return {"url": f"https://preview.example.com/{doc.name}"}

	module._assert_can_issue_download = lambda doc: download_docs.append(doc.name)
	module._issue_preview_grant_for_doc = _fake_issue_preview_grant_for_doc
	module._issue_grant = lambda *, doc, grant_kind, payload=None: (
		grant_calls.append(
			{
				"doc": doc.name,
				"grant_kind": grant_kind,
				"payload": payload,
			}
		)
		or {"url": f"https://{grant_kind}.example.com/{doc.name}"}
	)
	access_module._assert_can_issue_preview = lambda doc: None
	access_module._issue_grant = module._issue_grant
	access_module.now_datetime = lambda: datetime(2026, 1, 1, 0, 0, 0)

	preview_response = module.issue_public_website_media_preview_grant_service(
		{
			"file_id": "FILE-PUBLIC-1",
			"derivative_role": "viewer_preview",
		}
	)
	download_response = module.issue_public_website_media_download_grant_service(
		{
			"file_id": "FILE-PUBLIC-1",
		}
	)

	assert delegate_calls == ["FILE-PUBLIC-1", "FILE-PUBLIC-1"]
	assert preview_docs == []
	assert download_docs == ["DF-PUBLIC-1", "DF-PUBLIC-1"]
	assert preview_response == {"url": "https://preview.example.com/DF-PUBLIC-1"}
	assert download_response == {"url": "https://download.example.com/DF-PUBLIC-1"}
	assert grant_calls == [
		{
			"doc": "DF-PUBLIC-1",
			"grant_kind": "preview",
			"payload": {
				"file_id": "FILE-PUBLIC-1",
				"derivative_role": "viewer_preview",
			},
		},
		{
			"doc": "DF-PUBLIC-1",
			"grant_kind": "download",
			"payload": None,
		},
	]


def test_public_employee_image_preview_grant_service_uses_delegate_scoped_access():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_ed.integrations.drive.media",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-EMP-1",
			"owner_doctype": "Employee",
			"owner_name": "EMP-0001",
			"purpose": "employee_profile_display",
			"slot": "profile_image",
			"status": "active",
			"preview_status": "ready",
		}
	)
	_install_fake_frappe(
		exists_map={
			("Drive File", "DF-EMP-1"): True,
		},
		docs_map={("Drive File", "DF-EMP-1"): drive_file},
	)
	_ensure_ed_repo_on_path()
	importlib.import_module("ifitwala_ed")
	importlib.import_module("ifitwala_ed.integrations")
	importlib.import_module("ifitwala_ed.integrations.drive")
	delegate_calls = []
	delegate = types.ModuleType("ifitwala_ed.integrations.drive.media")
	delegate.assert_public_employee_image_read_access = lambda employee, *, file_name: (
		delegate_calls.append((employee, file_name))
		or {
			"employee": "EMP-0001",
			"file_id": "FILE-EMP-1",
			"drive_file_id": "DF-EMP-1",
		}
	)
	sys.modules["ifitwala_ed.integrations.drive.media"] = delegate

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")
	preview_calls = []

	module._issue_preview_grant_for_doc = lambda *, doc, payload=None: (
		preview_calls.append({"doc": doc.name, "payload": payload})
		or {"url": f"https://preview.example.com/{doc.name}"}
	)

	response = module.issue_public_employee_image_preview_grant_service(
		{
			"employee": "EMP-0001",
			"file_id": "FILE-EMP-1",
			"derivative_role": "card",
		}
	)

	assert delegate_calls == [("EMP-0001", "FILE-EMP-1")]
	assert response == {"url": "https://preview.example.com/DF-EMP-1"}
	assert preview_calls == [
		{
			"doc": "DF-EMP-1",
			"payload": {
				"employee": "EMP-0001",
				"file_id": "FILE-EMP-1",
				"derivative_role": "card",
			},
		}
	]


def test_student_preview_derivative_request_service_uses_delegate_scoped_access():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_ed.integrations.drive.media",
	)
	drive_file = FakeDoc(
		{
			"name": "DF-STU-1",
			"owner_doctype": "Student",
			"owner_name": "STU-0001",
			"slot": "profile_image",
			"status": "active",
			"preview_status": "pending",
		}
	)
	_install_fake_frappe(
		exists_map={
			("Drive File", "DF-STU-1"): True,
		},
		docs_map={("Drive File", "DF-STU-1"): drive_file},
	)
	_ensure_ed_repo_on_path()
	importlib.import_module("ifitwala_ed")
	importlib.import_module("ifitwala_ed.integrations")
	importlib.import_module("ifitwala_ed.integrations.drive")
	delegate_calls = []
	delegate = types.ModuleType("ifitwala_ed.integrations.drive.media")
	delegate.assert_student_image_read_access = lambda student, *, file_name: (
		delegate_calls.append((student, file_name))
		or {
			"student": "STU-0001",
			"file_id": "FILE-STU-1",
			"drive_file_id": "DF-STU-1",
		}
	)
	sys.modules["ifitwala_ed.integrations.drive.media"] = delegate

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")
	request_calls = []
	module.request_preview_derivatives_for_doc = lambda *, doc, payload=None: (
		request_calls.append({"doc": doc.name, "payload": payload})
		or {"drive_file_id": doc.name, "preview_status": "pending", "requested": True}
	)

	response = module.request_student_image_preview_derivatives_service(
		{
			"student": "STU-0001",
			"file_id": "FILE-STU-1",
			"derivative_roles": ["thumb", "card", "viewer_preview"],
		}
	)

	assert delegate_calls == [("STU-0001", "FILE-STU-1")]
	assert request_calls == [
		{
			"doc": "DF-STU-1",
			"payload": {
				"student": "STU-0001",
				"file_id": "FILE-STU-1",
				"derivative_roles": ["thumb", "card", "viewer_preview"],
			},
		}
	]
	assert response == {
		"drive_file_id": "DF-STU-1",
		"preview_status": "pending",
		"requested": True,
	}


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
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


def test_upload_employee_image_uses_employee_folder_tree():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_drive.services.uploads.sessions",
	)
	employee = FakeDoc({"name": "EMP-0001", "organization": "ORG-0001", "school": "SCH-0001"})
	_install_fake_frappe(
		exists_map={("Employee", "EMP-0001"): True},
		docs_map={("Employee", "EMP-0001"): employee},
	)
	recorder = {}
	_install_fake_sessions(recorder)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")

	response = module.upload_employee_image_service(
		{
			"employee": "EMP-0001",
			"filename_original": "employee.jpg",
			"mime_type_hint": "image/jpeg",
			"expected_size_bytes": 456,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert recorder["payload"]["owner_doctype"] == "Employee"
	assert recorder["payload"]["owner_name"] == "EMP-0001"
	assert recorder["payload"]["attached_doctype"] == "Employee"
	assert recorder["payload"]["attached_name"] == "EMP-0001"
	assert recorder["payload"]["primary_subject_id"] == "EMP-0001"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["school"] == "SCH-0001"
	assert recorder["payload"]["slot"] == "profile_image"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


def test_upload_guardian_image_uses_guardian_org_contract():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_media",
		"ifitwala_drive.services.uploads.sessions",
	)
	guardian = FakeDoc({"name": "GRD-0001", "organization": "ORG-0001"})
	_install_fake_frappe(
		exists_map={("Guardian", "GRD-0001"): True},
		docs_map={("Guardian", "GRD-0001"): guardian},
	)
	recorder = {}
	_install_fake_sessions(recorder)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_media")

	response = module.upload_guardian_image_service(
		{
			"guardian": "GRD-0001",
			"filename_original": "guardian.jpg",
			"mime_type_hint": "image/jpeg",
			"expected_size_bytes": 222,
		}
	)

	assert response["upload_session_id"] == "DUS-0001"
	assert recorder["payload"]["owner_doctype"] == "Guardian"
	assert recorder["payload"]["owner_name"] == "GRD-0001"
	assert recorder["payload"]["attached_doctype"] == "Guardian"
	assert recorder["payload"]["attached_name"] == "GRD-0001"
	assert recorder["payload"]["primary_subject_type"] == "Guardian"
	assert recorder["payload"]["primary_subject_id"] == "GRD-0001"
	assert recorder["payload"]["organization"] == "ORG-0001"
	assert recorder["payload"]["school"] is None
	assert recorder["payload"]["purpose"] == "guardian_profile_display"
	assert recorder["payload"]["slot"] == "profile_image"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


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
	assert recorder["payload"]["folder"].startswith("DRF-")


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

	assert response["workflow_result"]["applicant_document_item"] == "ADI-0001"
	assert recorder["payload"]["attached_doctype"] == "Applicant Document Item"
	assert recorder["payload"]["attached_name"] == "ADI-0001"
	assert recorder["payload"]["slot"] == "identity_passport_passport_copy"
	assert recorder["payload"]["folder"].startswith("DRF-")


def test_upload_applicant_profile_image_builds_applicant_scoped_session():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_admissions",
		"ifitwala_drive.services.uploads.sessions",
	)
	_install_fake_frappe(
		value_map={
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

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")
	response = module.upload_applicant_profile_image_service(
		{
			"student_applicant": "APP-0001",
			"filename_original": "profile.jpg",
		}
	)

	assert response["workflow_result"]["student_applicant"] == "APP-0001"
	assert recorder["payload"]["owner_doctype"] == "Student Applicant"
	assert recorder["payload"]["attached_doctype"] == "Student Applicant"
	assert recorder["payload"]["attached_name"] == "APP-0001"
	assert recorder["payload"]["slot"] == "profile_image"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


def test_upload_applicant_guardian_image_builds_row_scoped_session():
	_purge_modules(
		"frappe",
		"ifitwala_drive.services.integration.ifitwala_ed_admissions",
		"ifitwala_drive.services.uploads.sessions",
	)
	_install_fake_frappe(
		value_map={
			(
				"Student Applicant Guardian",
				(
					("name", "ROW-0001"),
					("parent", "APP-0001"),
					("parenttype", "Student Applicant"),
				),
				("name", "parent"),
				True,
			): {"name": "ROW-0001", "parent": "APP-0001"},
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

	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")
	response = module.upload_applicant_guardian_image_service(
		{
			"student_applicant": "APP-0001",
			"guardian_row_name": "ROW-0001",
			"filename_original": "guardian.jpg",
		}
	)

	assert response["workflow_result"]["guardian_row_name"] == "ROW-0001"
	assert recorder["payload"]["owner_doctype"] == "Student Applicant"
	assert recorder["payload"]["attached_doctype"] == "Student Applicant Guardian"
	assert recorder["payload"]["attached_name"] == "ROW-0001"
	assert recorder["payload"]["slot"] == "guardian_profile_image__row-0001"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


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

	assert response["workflow_result"]["applicant_health_profile"] == "AHP-0001"
	assert recorder["payload"]["owner_doctype"] == "Student Applicant"
	assert recorder["payload"]["owner_name"] == "APP-0001"
	assert recorder["payload"]["attached_doctype"] == "Applicant Health Profile"
	assert recorder["payload"]["attached_name"] == "AHP-0001"
	assert recorder["payload"]["slot"] == "health_vaccination_proof_mmr_2020-03-04"
	assert recorder["payload"]["is_private"] == 1
	assert recorder["payload"]["folder"].startswith("DRF-")


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


def test_get_admissions_attached_field_override_returns_applicant_image_for_profile_uploads():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	_install_fake_frappe()
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	fieldname = module.get_admissions_attached_field_override(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			attached_doctype="Student Applicant",
			intended_slot="profile_image",
		)
	)

	assert fieldname == "applicant_image"


def test_get_admissions_attached_field_override_returns_guardian_image_for_guardian_uploads():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	_install_fake_frappe()
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	fieldname = module.get_admissions_attached_field_override(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			attached_doctype="Student Applicant Guardian",
			intended_slot="guardian_profile_image__row-0001",
		)
	)

	assert fieldname == "guardian_image"


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
		},
		docs_map={
			("Drive File", "DF-0001"): FakeDoc(
				{
					"name": "DF-0001",
					"file": "FILE-0001",
					"status": "active",
					"canonical_ref": "drv:ORG-0001:DF-0001",
				}
			),
		},
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

	assert response["drive_file_id"] == "DF-0001"
	assert response["canonical_ref"] == "drv:ORG-0001:DF-0001"
	assert response["applicant_document_item"] == "ADI-0001"
	assert db_set_calls[0][0] == "Applicant Document Item"


def test_run_admissions_post_finalize_updates_applicant_profile_image():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	db_set_calls = _install_fake_frappe(
		value_map={},
		docs_map={
			("Drive File", "DF-0003"): FakeDoc(
				{
					"name": "DF-0003",
					"file": "FILE-0001",
					"status": "active",
					"canonical_ref": "drv:ORG-0001:DF-0003",
				}
			),
		},
	)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	class CreatedFile:
		name = "FILE-0001"
		file_url = "/private/files/profile.jpg"

	response = module.run_admissions_post_finalize(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Student Applicant",
			attached_name="APP-0001",
			intended_slot="profile_image",
		),
		CreatedFile(),
	)

	assert response["drive_file_id"] == "DF-0003"
	assert response["canonical_ref"] == "drv:ORG-0001:DF-0003"
	assert response["file_url"] == "/private/files/profile.jpg"
	assert db_set_calls[0][0] == "Student Applicant"
	assert db_set_calls[0][2] == "applicant_image"


def test_run_admissions_post_finalize_updates_guardian_image_row():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	db_set_calls = _install_fake_frappe(
		value_map={},
		docs_map={
			("Drive File", "DF-0004"): FakeDoc(
				{
					"name": "DF-0004",
					"file": "FILE-0001",
					"status": "active",
					"canonical_ref": "drv:ORG-0001:DF-0004",
				}
			),
		},
	)
	module = _load_module("ifitwala_drive.services.integration.ifitwala_ed_admissions")

	class CreatedFile:
		name = "FILE-0001"
		file_url = "/private/files/guardian.jpg"

	response = module.run_admissions_post_finalize(
		types.SimpleNamespace(
			owner_doctype="Student Applicant",
			owner_name="APP-0001",
			attached_doctype="Student Applicant Guardian",
			attached_name="ROW-0001",
			intended_slot="guardian_profile_image__row-0001",
		),
		CreatedFile(),
	)

	assert response["drive_file_id"] == "DF-0004"
	assert response["canonical_ref"] == "drv:ORG-0001:DF-0004"
	assert response["guardian_row_name"] == "ROW-0001"
	assert db_set_calls[0][0] == "Student Applicant Guardian"
	assert db_set_calls[0][2] == "guardian_image"


def test_run_admissions_post_finalize_returns_health_upload_metadata():
	_purge_modules("frappe", "ifitwala_drive.services.integration.ifitwala_ed_admissions")
	_install_fake_frappe(
		value_map={},
		docs_map={
			("Drive File", "DF-0002"): FakeDoc(
				{
					"name": "DF-0002",
					"file": "FILE-0001",
					"status": "active",
					"canonical_ref": "drv:ORG-0001:DF-0002",
				}
			),
		},
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

	assert response["drive_file_id"] == "DF-0002"
	assert response["canonical_ref"] == "drv:ORG-0001:DF-0002"
	assert response["file_url"] == "/private/files/mmr-proof.png"
	assert response["applicant_health_profile"] == "AHP-0001"
