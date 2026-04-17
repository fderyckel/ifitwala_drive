from __future__ import annotations

import frappe

from ifitwala_drive.services.concurrency import drive_lock, is_duplicate_entry_error
from ifitwala_drive.services.folders.key_builder import build_folder_system_key, slugify_folder_title


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


def _build_system_key(
	*,
	title: str,
	parent_drive_folder: str | None,
	owner_doctype: str,
	owner_name: str,
	organization: str,
	school: str | None,
	folder_kind: str,
) -> str:
	return build_folder_system_key(
		title=title,
		parent_drive_folder=parent_drive_folder,
		owner_doctype=owner_doctype,
		owner_name=owner_name,
		organization=organization,
		school=school,
		folder_kind=folder_kind,
	)


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
	system_key = _build_system_key(
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
			slugify_folder_title(title),
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
				"slug": slugify_folder_title(title),
				"status": "active",
				"is_system_managed": 1,
				"system_key": system_key,
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
		try:
			doc.insert(ignore_permissions=True)
		except Exception as exc:
			if not is_duplicate_entry_error(exc):
				raise

			existing = frappe.db.get_value(
				"Drive Folder",
				{"system_key": system_key},
				"name",
			)
			if not existing:
				raise
			return existing
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


def _ensure_employee_root(*, employee: str, organization: str, school: str | None) -> str:
	employees_root = _ensure_folder(
		title="Employees",
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Employee",
	)
	return _ensure_folder(
		title=employee,
		parent_drive_folder=employees_root,
		owner_doctype="Employee",
		owner_name=employee,
		organization=organization,
		school=school,
		folder_kind="staff_documents",
		context_doctype="Employee",
		context_name=employee,
	)


def resolve_employee_image_folder(*, employee: str, organization: str, school: str | None) -> str:
	employee_root = _ensure_employee_root(employee=employee, organization=organization, school=school)
	profile_root = _ensure_folder(
		title="Profile",
		parent_drive_folder=employee_root,
		owner_doctype="Employee",
		owner_name=employee,
		organization=organization,
		school=school,
		folder_kind="staff_documents",
		context_doctype="Employee",
		context_name=employee,
	)
	return _ensure_folder(
		title="Employee Image",
		parent_drive_folder=profile_root,
		owner_doctype="Employee",
		owner_name=employee,
		organization=organization,
		school=school,
		folder_kind="staff_documents",
		context_doctype="Employee",
		context_name=employee,
	)


def _ensure_guardian_root(*, guardian: str, organization: str) -> str:
	guardians_root = _ensure_folder(
		title="Guardians",
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Guardian",
	)
	return _ensure_folder(
		title=guardian,
		parent_drive_folder=guardians_root,
		owner_doctype="Guardian",
		owner_name=guardian,
		organization=organization,
		school=None,
		folder_kind="guardian_workspace",
		context_doctype="Guardian",
		context_name=guardian,
	)


def resolve_guardian_image_folder(*, guardian: str, organization: str) -> str:
	guardian_root = _ensure_guardian_root(guardian=guardian, organization=organization)
	profile_root = _ensure_folder(
		title="Profile",
		parent_drive_folder=guardian_root,
		owner_doctype="Guardian",
		owner_name=guardian,
		organization=organization,
		school=None,
		folder_kind="guardian_workspace",
		context_doctype="Guardian",
		context_name=guardian,
	)
	return _ensure_folder(
		title="Guardian Image",
		parent_drive_folder=profile_root,
		owner_doctype="Guardian",
		owner_name=guardian,
		organization=organization,
		school=None,
		folder_kind="guardian_workspace",
		context_doctype="Guardian",
		context_name=guardian,
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


def _ensure_courses_root(*, organization: str) -> str:
	return _ensure_folder(
		title="Courses",
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Organization",
		context_name=organization,
	)


def _ensure_course_root(*, course: str, organization: str, school: str) -> str:
	courses_root = _ensure_courses_root(organization=organization)
	school_root = _ensure_folder(
		title=school,
		parent_drive_folder=courses_root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="School",
		context_name=school,
	)
	return _ensure_folder(
		title=course,
		parent_drive_folder=school_root,
		owner_doctype="Course",
		owner_name=course,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="Course",
		context_name=course,
	)


def _ensure_organization_communications_root(*, organization: str) -> str:
	organization_root = _ensure_folder(
		title=organization,
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Organization",
		context_name=organization,
	)
	return _ensure_folder(
		title="Communications",
		parent_drive_folder=organization_root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Organization",
		context_name=organization,
	)


def _ensure_school_communications_root(*, organization: str, school: str) -> str:
	organization_root = _ensure_folder(
		title=organization,
		parent_drive_folder=None,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Organization",
		context_name=organization,
	)
	schools_root = _ensure_folder(
		title="Schools",
		parent_drive_folder=organization_root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Organization",
		context_name=organization,
	)
	school_root = _ensure_folder(
		title=school,
		parent_drive_folder=schools_root,
		owner_doctype="Organization",
		owner_name=organization,
		organization=organization,
		school=school,
		folder_kind="system_bound",
		context_doctype="School",
		context_name=school,
	)
	return _ensure_folder(
		title="Communications",
		parent_drive_folder=school_root,
		owner_doctype="School",
		owner_name=school,
		organization=organization,
		school=school,
		folder_kind="system_bound",
		context_doctype="School",
		context_name=school,
	)


def resolve_supporting_material_folder(
	*,
	material: str,
	course: str,
	organization: str,
	school: str,
) -> str:
	course_root = _ensure_course_root(
		course=course,
		organization=organization,
		school=school,
	)
	materials_root = _ensure_folder(
		title="Materials",
		parent_drive_folder=course_root,
		owner_doctype="Course",
		owner_name=course,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="Course",
		context_name=course,
	)
	return _ensure_folder(
		title=material,
		parent_drive_folder=materials_root,
		owner_doctype="Supporting Material",
		owner_name=material,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="Supporting Material",
		context_name=material,
	)


def resolve_task_resource_folder(
	*,
	task: str,
	course: str,
	organization: str,
	school: str,
) -> str:
	course_root = _ensure_course_root(
		course=course,
		organization=organization,
		school=school,
	)
	tasks_root = _ensure_folder(
		title="Tasks",
		parent_drive_folder=course_root,
		owner_doctype="Course",
		owner_name=course,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="Course",
		context_name=course,
	)
	task_root = _ensure_folder(
		title=task,
		parent_drive_folder=tasks_root,
		owner_doctype="Task",
		owner_name=task,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="Task",
		context_name=task,
	)
	return _ensure_folder(
		title="Resources",
		parent_drive_folder=task_root,
		owner_doctype="Task",
		owner_name=task,
		organization=organization,
		school=school,
		folder_kind="course_shared",
		context_doctype="Task",
		context_name=task,
	)


def resolve_org_communication_attachment_folder(
	*,
	org_communication: str,
	course: str | None,
	student_group: str | None,
	organization: str,
	school: str | None,
) -> str:
	if course and student_group and school:
		course_root = _ensure_course_root(
			course=course,
			organization=organization,
			school=school,
		)
		communications_root = _ensure_folder(
			title="Communications",
			parent_drive_folder=course_root,
			owner_doctype="Course",
			owner_name=course,
			organization=organization,
			school=school,
			folder_kind="course_shared",
			context_doctype="Course",
			context_name=course,
		)
		student_group_root = _ensure_folder(
			title=student_group,
			parent_drive_folder=communications_root,
			owner_doctype="Student Group",
			owner_name=student_group,
			organization=organization,
			school=school,
			folder_kind="course_shared",
			context_doctype="Student Group",
			context_name=student_group,
		)
		org_communication_root = _ensure_folder(
			title=org_communication,
			parent_drive_folder=student_group_root,
			owner_doctype="Org Communication",
			owner_name=org_communication,
			organization=organization,
			school=school,
			folder_kind="course_shared",
			context_doctype="Org Communication",
			context_name=org_communication,
		)
		return _ensure_folder(
			title="Attachments",
			parent_drive_folder=org_communication_root,
			owner_doctype="Org Communication",
			owner_name=org_communication,
			organization=organization,
			school=school,
			folder_kind="course_shared",
			context_doctype="Org Communication",
			context_name=org_communication,
		)

	if school:
		communications_root = _ensure_school_communications_root(
			organization=organization,
			school=school,
		)
		org_communication_root = _ensure_folder(
			title=org_communication,
			parent_drive_folder=communications_root,
			owner_doctype="Org Communication",
			owner_name=org_communication,
			organization=organization,
			school=school,
			folder_kind="system_bound",
			context_doctype="Org Communication",
			context_name=org_communication,
		)
		return _ensure_folder(
			title="Attachments",
			parent_drive_folder=org_communication_root,
			owner_doctype="Org Communication",
			owner_name=org_communication,
			organization=organization,
			school=school,
			folder_kind="system_bound",
			context_doctype="Org Communication",
			context_name=org_communication,
		)

	communications_root = _ensure_organization_communications_root(organization=organization)
	org_communication_root = _ensure_folder(
		title=org_communication,
		parent_drive_folder=communications_root,
		owner_doctype="Org Communication",
		owner_name=org_communication,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Org Communication",
		context_name=org_communication,
	)
	return _ensure_folder(
		title="Attachments",
		parent_drive_folder=org_communication_root,
		owner_doctype="Org Communication",
		owner_name=org_communication,
		organization=organization,
		school=None,
		folder_kind="system_bound",
		context_doctype="Org Communication",
		context_name=org_communication,
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
