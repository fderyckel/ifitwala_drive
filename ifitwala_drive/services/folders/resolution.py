from __future__ import annotations

import re

import frappe
from ifitwala_drive.services.concurrency import drive_lock


def _slugify(value: str | None) -> str:
	value = (value or "").strip().lower()
	value = re.sub(r"[^a-z0-9]+", "-", value)
	value = re.sub(r"-{2,}", "-", value).strip("-")
	return value or "folder"


def _folder_lookup_filters(
	*,
	title: str,
	parent_drive_folder: str | None,
	owner_doctype: str,
	owner_name: str,
	organization: str,
	school: str | None,
	folder_kind: str,
) -> dict[str, object]:
	filters: dict[str, object] = {
		"title": title,
		"owner_doctype": owner_doctype,
		"owner_name": owner_name,
		"organization": organization,
		"folder_kind": folder_kind,
	}
	if parent_drive_folder:
		filters["parent_drive_folder"] = parent_drive_folder
	if school:
		filters["school"] = school
	return filters


def _ensure_folder(
	*,
	title: str,
	parent_drive_folder: str | None,
	owner_doctype: str,
	owner_name: str,
	organization: str,
	school: str | None,
	folder_kind: str,
	context_doctype: str | None = None,
	context_name: str | None = None,
	is_private: int = 1,
) -> str:
	filters = _folder_lookup_filters(
		title=title,
		parent_drive_folder=parent_drive_folder,
		owner_doctype=owner_doctype,
		owner_name=owner_name,
		organization=organization,
		school=school,
		folder_kind=folder_kind,
	)
	lock_key = "|".join(
		[
			"folder",
			organization,
			owner_doctype,
			owner_name,
			parent_drive_folder or "root",
			folder_kind,
			_slugify(title),
			school or "no-school",
		]
	)
	with drive_lock(lock_key, timeout=20):
		existing = frappe.db.get_value("Drive Folder", filters, "name")
		if existing:
			return existing

		doc = frappe.get_doc(
			{
				"doctype": "Drive Folder",
				"title": title,
				"slug": _slugify(title),
				"status": "active",
				"is_system_managed": 1,
				"parent_drive_folder": parent_drive_folder,
				"owner_doctype": owner_doctype,
				"owner_name": owner_name,
				"organization": organization,
				"school": school,
				"folder_kind": folder_kind,
				"context_doctype": context_doctype,
				"context_name": context_name,
				"is_private": is_private,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name


def _ensure_admissions_applicant_root(*, student_applicant: str, organization: str, school: str) -> str:
	admissions_root = _ensure_folder(
		title="Admissions",
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Student Applicant",
	)
	applicant_root = _ensure_folder(
		title="Applicant",
		parent_drive_folder=admissions_root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=school,
		folder_kind="system_bound",
		context_doctype="Student Applicant",
	)
	return _ensure_folder(
		title=student_applicant,
		parent_drive_folder=applicant_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def _ensure_documents_branch(*, student_applicant: str, organization: str, school: str) -> str:
	applicant_root = _ensure_admissions_applicant_root(
		student_applicant=student_applicant,
		organization=organization,
		school=school,
	)
	return _ensure_folder(
		title="Documents",
		parent_drive_folder=applicant_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def _ensure_profile_branch(*, student_applicant: str, organization: str, school: str) -> str:
	applicant_root = _ensure_admissions_applicant_root(
		student_applicant=student_applicant,
		organization=organization,
		school=school,
	)
	return _ensure_folder(
		title="Profile",
		parent_drive_folder=applicant_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def _classify_applicant_document_group(*, slot: str, document_type_code: str | None) -> str:
	code = (document_type_code or "").strip().lower()
	slot = (slot or "").strip().lower()
	if slot.startswith("identity_") or code in {"passport", "id", "identity", "visa"}:
		return "Identity"
	if "transcript" in code or "transcript" in slot:
		return "Academic"
	return "Documents"


def resolve_applicant_document_folder(
	*,
	student_applicant: str,
	organization: str,
	school: str,
	slot: str,
	document_type_code: str | None = None,
) -> str:
	documents_root = _ensure_documents_branch(
		student_applicant=student_applicant,
		organization=organization,
		school=school,
	)
	group_title = _classify_applicant_document_group(slot=slot, document_type_code=document_type_code)
	if group_title == "Documents":
		return documents_root
	return _ensure_folder(
		title=group_title,
		parent_drive_folder=documents_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def resolve_applicant_health_folder(*, student_applicant: str, organization: str, school: str) -> str:
	documents_root = _ensure_documents_branch(
		student_applicant=student_applicant,
		organization=organization,
		school=school,
	)
	return _ensure_folder(
		title="Health",
		parent_drive_folder=documents_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def resolve_applicant_profile_image_folder(*, student_applicant: str, organization: str, school: str) -> str:
	profile_root = _ensure_profile_branch(
		student_applicant=student_applicant,
		organization=organization,
		school=school,
	)
	return _ensure_folder(
		title="Applicant Image",
		parent_drive_folder=profile_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def resolve_applicant_guardian_image_folder(*, student_applicant: str, organization: str, school: str) -> str:
	profile_root = _ensure_profile_branch(
		student_applicant=student_applicant,
		organization=organization,
		school=school,
	)
	return _ensure_folder(
		title="Guardian Images",
		parent_drive_folder=profile_root,
		owner_doctype="Student Applicant",
		owner_name=student_applicant,
		organization=organization,
		school=school,
		folder_kind="applicant_documents",
		context_doctype="Student Applicant",
		context_name=student_applicant,
	)


def _ensure_student_root(*, student: str, organization: str, school: str) -> str:
	student_root = _ensure_folder(
		title="Student",
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Student",
	)
	return _ensure_folder(
		title=student,
		parent_drive_folder=student_root,
		owner_doctype="Student",
		owner_name=student,
		organization=organization,
		school=school,
		folder_kind="student_workspace",
		context_doctype="Student",
		context_name=student,
	)


def resolve_student_image_folder(*, student: str, organization: str, school: str) -> str:
	student_root = _ensure_student_root(student=student, organization=organization, school=school)
	profile_root = _ensure_folder(
		title="Profile",
		parent_drive_folder=student_root,
		owner_doctype="Student",
		owner_name=student,
		organization=organization,
		school=school,
		folder_kind="student_workspace",
		context_doctype="Student",
		context_name=student,
	)
	return _ensure_folder(
		title="Student Image",
		parent_drive_folder=profile_root,
		owner_doctype="Student",
		owner_name=student,
		organization=organization,
		school=school,
		folder_kind="student_workspace",
		context_doctype="Student",
		context_name=student,
	)


def resolve_task_submission_folder(
	*,
	student: str,
	task_name: str,
	organization: str,
	school: str,
) -> str:
	student_root = _ensure_student_root(student=student, organization=organization, school=school)
	tasks_root = _ensure_folder(
		title="Tasks",
		parent_drive_folder=student_root,
		owner_doctype="Student",
		owner_name=student,
		organization=organization,
		school=school,
		folder_kind="student_workspace",
		context_doctype="Student",
		context_name=student,
	)
	task_root = _ensure_folder(
		title=task_name,
		parent_drive_folder=tasks_root,
		owner_doctype="Student",
		owner_name=student,
		organization=organization,
		school=school,
		folder_kind="student_workspace",
		context_doctype="Student",
		context_name=student,
	)
	return _ensure_folder(
		title="Submissions",
		parent_drive_folder=task_root,
		owner_doctype="Student",
		owner_name=student,
		organization=organization,
		school=school,
		folder_kind="student_workspace",
		context_doctype="Student",
		context_name=student,
	)


def _ensure_organization_media_root(*, organization: str) -> str:
	return _ensure_folder(
		title="Organization Media",
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Organization",
		context_name=organization,
		is_private=0,
	)


def _organization_media_leaf_for_slot(slot: str) -> str:
	slot = (slot or "").strip().lower()
	if slot.startswith("organization_logo__") or slot.startswith("school_logo__"):
		return "Logos"
	if slot.startswith("school_gallery_image__"):
		return "Campus Media"
	return "Public Media"


def resolve_organization_media_folder(*, organization: str, school: str | None, slot: str) -> str:
	root = _ensure_organization_media_root(organization=organization)
	if school:
		schools_root = _ensure_folder(
			title="Schools",
			parent_drive_folder=root,
			owner_doctype="Organization",
			owner_name=organization,
			organization=organization,
			school=None,
			folder_kind="organization_media",
			context_doctype="Organization",
			context_name=organization,
			is_private=0,
		)
		school_root = _ensure_folder(
			title=school,
			parent_drive_folder=schools_root,
			owner_doctype="Organization",
			owner_name=organization,
			organization=organization,
			school=school,
			folder_kind="organization_media",
			context_doctype="School",
			context_name=school,
			is_private=0,
		)
		return _ensure_folder(
			title=_organization_media_leaf_for_slot(slot),
			parent_drive_folder=school_root,
			owner_doctype="Organization",
			owner_name=organization,
			organization=organization,
			school=school,
			folder_kind="organization_media",
			context_doctype="School",
			context_name=school,
			is_private=0,
		)

	organization_root = _ensure_folder(
		title="Organization",
		parent_drive_folder=root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="organization_media",
		context_doctype="Organization",
		context_name=organization,
		is_private=0,
	)
	return _ensure_folder(
		title=_organization_media_leaf_for_slot(slot),
		parent_drive_folder=organization_root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="organization_media",
		context_doctype="Organization",
		context_name=organization,
		is_private=0,
	)
