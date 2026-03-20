from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	for module_name in list(sys.modules):
		if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
			sys.modules.pop(module_name, None)


class FakeDoc:
	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def check_permission(self, permission_type=None):
		if getattr(self, "permission_error", False):
			raise RuntimeError("Permission denied")
		return None


def _install_fake_frappe(*, exists_map=None, docs_map=None, get_all_handlers=None, session_user="tester@example.com", roles=None):
	exists_map = exists_map or {}
	docs_map = docs_map or {}
	get_all_handlers = get_all_handlers or {}
	roles = roles or []

	class FakeDB:
		def exists(self, doctype, name=None):
			key = (doctype, name)
			if key in exists_map:
				return exists_map[key]
			return (doctype, name) in docs_map

	def _throw(message, exc=None):
		raise RuntimeError(message)

	def _get_doc(doctype, name=None):
		return docs_map[(doctype, name)]

	def _get_all(doctype, filters=None, fields=None, order_by=None, limit_page_length=None, limit_start=None):
		handler = get_all_handlers.get(doctype)
		if not handler:
			return []
		return handler(
			filters=filters or {},
			fields=fields or [],
			order_by=order_by,
			limit_page_length=limit_page_length,
			limit_start=limit_start,
		)

	frappe = types.ModuleType("frappe")
	frappe.throw = _throw
	frappe._ = lambda message: message
	frappe.db = FakeDB()
	frappe.get_doc = _get_doc
	frappe.get_all = _get_all
	frappe.session = types.SimpleNamespace(user=session_user)
	frappe.get_roles = lambda user=None: roles
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn

	sys.modules["frappe"] = frappe
	return frappe


def _load_module(module_name: str):
	return importlib.import_module(module_name)


def test_list_context_files_returns_bound_drive_files():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	task_submission = FakeDoc({"name": "TSUB-0001"})
	student_root = FakeDoc(
		{
			"name": "DRF-STUDENT",
			"title": "Student",
			"path_cache": "student",
			"owner_doctype": "Student",
			"owner_name": "STU-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Student",
			"context_name": "STU-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	task_root = FakeDoc(
		{
			"name": "DRF-TASK",
			"title": "TASK-0001",
			"path_cache": "student/task-0001",
			"parent_drive_folder": "DRF-STUDENT",
			"owner_doctype": "Student",
			"owner_name": "STU-0001",
			"folder_kind": "student_workspace",
			"context_doctype": "Student",
			"context_name": "STU-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	submissions_folder = FakeDoc(
		{
			"name": "DRF-0001",
			"title": "Submissions",
			"path_cache": "student/task-0001/submissions",
			"parent_drive_folder": "DRF-TASK",
			"owner_doctype": "Student",
			"owner_name": "STU-0001",
			"folder_kind": "student_workspace",
			"context_doctype": "Student",
			"context_name": "STU-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0001"): True},
		docs_map={
			("Task Submission", "TSUB-0001"): task_submission,
			("Drive Folder", "DRF-STUDENT"): student_root,
			("Drive Folder", "DRF-TASK"): task_root,
			("Drive Folder", "DRF-0001"): submissions_folder,
		},
		get_all_handlers={
			"Drive Binding": lambda **kwargs: [
				{
					"drive_file": "DF-0001",
					"binding_role": "submission_artifact",
					"slot": "submission",
					"is_primary": 1,
					"modified": "2026-03-18 10:00:00",
				}
			],
			"Drive File": lambda **kwargs: [
				{
					"name": "DF-0001",
					"canonical_ref": "drv:ORG-0001:DF-0001",
					"slot": "submission",
					"display_name": "essay.docx",
					"current_version_no": 1,
					"preview_status": "pending",
					"folder": "DRF-0001",
					"attached_doctype": "Task Submission",
					"attached_name": "TSUB-0001",
				}
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service(
		{
			"doctype": "Task Submission",
			"name": "TSUB-0001",
			"binding_role": "submission_artifact",
		}
	)

	assert response == {
		"context": {"doctype": "Task Submission", "name": "TSUB-0001"},
		"files": [
			{
				"id": "DF-0001",
				"drive_file_id": "DF-0001",
				"canonical_ref": "drv:ORG-0001:DF-0001",
				"slot": "submission",
				"title": "essay.docx",
				"current_version_no": 1,
				"preview_status": "pending",
				"binding_role": "submission_artifact",
				"folder": {
					"id": "DRF-0001",
					"title": "Submissions",
					"path_cache": "student/task-0001/submissions",
					"context_path": "Student / TASK-0001 / Submissions",
					"folder_kind": "student_workspace",
					"parent_folder": "DRF-TASK",
					"breadcrumbs": [
						{
							"id": "DRF-STUDENT",
							"title": "Student",
							"path_cache": "student",
						},
						{
							"id": "DRF-TASK",
							"title": "TASK-0001",
							"path_cache": "student/task-0001",
						},
						{
							"id": "DRF-0001",
							"title": "Submissions",
							"path_cache": "student/task-0001/submissions",
						},
					],
					"owner": {
						"doctype": "Student",
						"name": "STU-0001",
					},
					"context": {
						"doctype": "Student",
						"name": "STU-0001",
					},
					"is_system_managed": 1,
					"is_private": 1,
				},
				"folder_path": "student/task-0001/submissions",
				"context_path": "Student / TASK-0001 / Submissions",
				"attached_to": {
					"doctype": "Task Submission",
					"name": "TSUB-0001",
				},
				"can_preview": False,
				"can_download": True,
			}
		],
	}


def test_list_folder_items_returns_child_folders_and_files():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	folder_doc = FakeDoc(
		{
			"name": "DRF-ROOT",
			"title": "Admissions",
			"path_cache": "admissions",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Student Applicant",
			"context_name": "APP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	child_folder_doc = FakeDoc(
		{
			"name": "DRF-CHILD",
			"title": "Applicant",
			"path_cache": "admissions/applicant",
			"parent_drive_folder": "DRF-ROOT",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Student Applicant",
			"context_name": "APP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	org_doc = FakeDoc({"name": "ORG-0001"})
	_install_fake_frappe(
		exists_map={
			("Drive Folder", "DRF-ROOT"): True,
			("Organization", "ORG-0001"): True,
		},
		docs_map={
			("Drive Folder", "DRF-ROOT"): folder_doc,
			("Drive Folder", "DRF-CHILD"): child_folder_doc,
			("Organization", "ORG-0001"): org_doc,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: [
				{
					"name": "DRF-CHILD",
					"title": "Applicant",
					"path_cache": "admissions/applicant",
					"modified": "2026-03-18 11:00:00",
				}
			],
			"Drive File": lambda **kwargs: [
				{
					"name": "DF-0001",
					"display_name": "passport.pdf",
					"preview_status": "pending",
					"canonical_ref": "drv:ORG-0001:DF-0001",
					"slot": "identity_passport_passport_copy",
					"current_version_no": 1,
					"folder": "DRF-ROOT",
					"attached_doctype": "Applicant Document Item",
					"attached_name": "ADI-0001",
					"owner_doctype": "Organization",
					"owner_name": "ORG-0001",
					"modified": "2026-03-18 10:00:00",
				}
			],
			"Drive Binding": lambda **kwargs: [
				{
					"drive_file": "DF-0001",
					"binding_role": "applicant_document",
					"is_primary": 1,
					"modified": "2026-03-18 10:00:00",
				}
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_folder_items_service({"folder": "DRF-ROOT"})

	assert response == {
		"folder": {
			"id": "DRF-ROOT",
			"title": "Admissions",
			"path_cache": "admissions",
			"context_path": "Admissions",
			"folder_kind": "system_bound",
			"parent_folder": None,
			"breadcrumbs": [
				{
					"id": "DRF-ROOT",
					"title": "Admissions",
					"path_cache": "admissions",
				}
			],
			"owner": {
				"doctype": "Organization",
				"name": "ORG-0001",
			},
			"context": {
				"doctype": "Student Applicant",
				"name": "APP-0001",
			},
			"is_system_managed": 1,
			"is_private": 1,
		},
		"items": [
			{
				"item_type": "folder",
				"id": "DRF-CHILD",
				"title": "Applicant",
				"path_cache": "admissions/applicant",
				"context_path": "Admissions / Applicant",
				"folder_kind": "system_bound",
				"parent_folder": "DRF-ROOT",
				"breadcrumbs": [
					{
						"id": "DRF-ROOT",
						"title": "Admissions",
						"path_cache": "admissions",
					},
					{
						"id": "DRF-CHILD",
						"title": "Applicant",
						"path_cache": "admissions/applicant",
					},
				],
				"owner": {
					"doctype": "Organization",
					"name": "ORG-0001",
				},
				"context": {
					"doctype": "Student Applicant",
					"name": "APP-0001",
				},
				"is_system_managed": 1,
				"is_private": 1,
			},
			{
				"item_type": "file",
				"id": "DF-0001",
				"title": "passport.pdf",
				"binding_role": "applicant_document",
				"preview_status": "pending",
				"canonical_ref": "drv:ORG-0001:DF-0001",
				"slot": "identity_passport_passport_copy",
				"current_version_no": 1,
				"folder": {
					"id": "DRF-ROOT",
					"title": "Admissions",
					"path_cache": "admissions",
					"context_path": "Admissions",
					"folder_kind": "system_bound",
					"parent_folder": None,
					"breadcrumbs": [
						{
							"id": "DRF-ROOT",
							"title": "Admissions",
							"path_cache": "admissions",
						}
					],
					"owner": {
						"doctype": "Organization",
						"name": "ORG-0001",
					},
					"context": {
						"doctype": "Student Applicant",
						"name": "APP-0001",
					},
					"is_system_managed": 1,
					"is_private": 1,
				},
				"folder_path": "admissions",
				"context_path": "Admissions",
				"attached_to": {
					"doctype": "Applicant Document Item",
					"name": "ADI-0001",
				},
				"can_preview": False,
				"can_download": True,
			},
		],
	}


def test_list_workspace_roots_returns_only_accessible_root_folders():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	organization_doc = FakeDoc({"name": "ORG-0001"})
	forbidden_owner = FakeDoc({"name": "ORG-0002", "permission_error": True})
	root_a = FakeDoc(
		{
			"name": "DRF-ROOT-A",
			"title": "Admissions",
			"path_cache": "admissions",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Student Applicant",
			"context_name": "APP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	root_b = FakeDoc(
		{
			"name": "DRF-ROOT-B",
			"title": "Private Root",
			"path_cache": "private-root",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0002",
			"folder_kind": "system_bound",
			"context_doctype": "Organization",
			"context_name": "ORG-0002",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	child = FakeDoc(
		{
			"name": "DRF-CHILD",
			"title": "Child",
			"path_cache": "admissions/child",
			"parent_drive_folder": "DRF-ROOT-A",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Student Applicant",
			"context_name": "APP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("Organization", "ORG-0002"): True,
			("Drive Folder", "DRF-ROOT-A"): True,
			("Drive Folder", "DRF-ROOT-B"): True,
			("Drive Folder", "DRF-CHILD"): True,
		},
		docs_map={
			("Organization", "ORG-0001"): organization_doc,
			("Organization", "ORG-0002"): forbidden_owner,
			("Drive Folder", "DRF-ROOT-A"): root_a,
			("Drive Folder", "DRF-ROOT-B"): root_b,
			("Drive Folder", "DRF-CHILD"): child,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: [
				{
					"name": "DRF-ROOT-A",
					"title": "Admissions",
					"path_cache": "admissions",
					"parent_drive_folder": None,
					"owner_doctype": "Organization",
					"owner_name": "ORG-0001",
					"folder_kind": "system_bound",
					"context_doctype": "Student Applicant",
					"context_name": "APP-0001",
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-19 09:00:00",
				},
				{
					"name": "DRF-ROOT-B",
					"title": "Private Root",
					"path_cache": "private-root",
					"parent_drive_folder": None,
					"owner_doctype": "Organization",
					"owner_name": "ORG-0002",
					"folder_kind": "system_bound",
					"context_doctype": "Organization",
					"context_name": "ORG-0002",
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-19 08:00:00",
				},
				{
					"name": "DRF-CHILD",
					"title": "Child",
					"path_cache": "admissions/child",
					"parent_drive_folder": "DRF-ROOT-A",
					"owner_doctype": "Organization",
					"owner_name": "ORG-0001",
					"folder_kind": "system_bound",
					"context_doctype": "Student Applicant",
					"context_name": "APP-0001",
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-19 07:00:00",
				},
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_workspace_roots_service({})

	assert response == {
		"roots": [
			{
				"id": "DRF-ROOT-A",
				"title": "Admissions",
				"path_cache": "admissions",
				"context_path": "Admissions",
				"folder_kind": "system_bound",
				"parent_folder": None,
				"breadcrumbs": [
					{
						"id": "DRF-ROOT-A",
						"title": "Admissions",
						"path_cache": "admissions",
					}
				],
				"owner": {
					"doctype": "Organization",
					"name": "ORG-0001",
				},
				"context": {
					"doctype": "Student Applicant",
					"name": "APP-0001",
				},
				"is_system_managed": 1,
				"is_private": 1,
			}
		]
	}


def test_list_folder_items_filters_unreadable_children_and_files():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	root_doc = FakeDoc(
		{
			"name": "DRF-EMP-ROOT",
			"title": "Employees",
			"path_cache": "employees",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Employee",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	readable_employee = FakeDoc({"name": "EMP-0001"})
	forbidden_employee = FakeDoc({"name": "EMP-0002", "permission_error": True})
	child_visible = FakeDoc(
		{
			"name": "DRF-EMP-0001",
			"title": "EMP-0001",
			"path_cache": "employees/emp-0001",
			"parent_drive_folder": "DRF-EMP-ROOT",
			"owner_doctype": "Employee",
			"owner_name": "EMP-0001",
			"folder_kind": "staff_documents",
			"context_doctype": "Employee",
			"context_name": "EMP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	child_hidden = FakeDoc(
		{
			"name": "DRF-EMP-0002",
			"title": "EMP-0002",
			"path_cache": "employees/emp-0002",
			"parent_drive_folder": "DRF-EMP-ROOT",
			"owner_doctype": "Employee",
			"owner_name": "EMP-0002",
			"folder_kind": "staff_documents",
			"context_doctype": "Employee",
			"context_name": "EMP-0002",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	organization_doc = FakeDoc({"name": "ORG-0001"})
	_install_fake_frappe(
		exists_map={
			("Drive Folder", "DRF-EMP-ROOT"): True,
			("Organization", "ORG-0001"): True,
			("Employee", "EMP-0001"): True,
			("Employee", "EMP-0002"): True,
			("Drive Folder", "DRF-EMP-0001"): True,
			("Drive Folder", "DRF-EMP-0002"): True,
		},
		docs_map={
			("Drive Folder", "DRF-EMP-ROOT"): root_doc,
			("Drive Folder", "DRF-EMP-0001"): child_visible,
			("Drive Folder", "DRF-EMP-0002"): child_hidden,
			("Organization", "ORG-0001"): organization_doc,
			("Employee", "EMP-0001"): readable_employee,
			("Employee", "EMP-0002"): forbidden_employee,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: [
				{
					"name": "DRF-EMP-0001",
					"title": "EMP-0001",
					"path_cache": "employees/emp-0001",
					"parent_drive_folder": "DRF-EMP-ROOT",
					"owner_doctype": "Employee",
					"owner_name": "EMP-0001",
					"folder_kind": "staff_documents",
					"context_doctype": "Employee",
					"context_name": "EMP-0001",
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-20 10:00:00",
				},
				{
					"name": "DRF-EMP-0002",
					"title": "EMP-0002",
					"path_cache": "employees/emp-0002",
					"parent_drive_folder": "DRF-EMP-ROOT",
					"owner_doctype": "Employee",
					"owner_name": "EMP-0002",
					"folder_kind": "staff_documents",
					"context_doctype": "Employee",
					"context_name": "EMP-0002",
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-20 09:00:00",
				},
			],
			"Drive File": lambda **kwargs: [
				{
					"name": "DF-EMP-0001",
					"display_name": "profile.jpg",
					"preview_status": "ready",
					"canonical_ref": "drv:ORG-0001:DF-EMP-0001",
					"slot": "profile_image",
					"current_version_no": 1,
					"folder": "DRF-EMP-0001",
					"attached_doctype": "Employee",
					"attached_name": "EMP-0001",
					"owner_doctype": "Employee",
					"owner_name": "EMP-0001",
					"modified": "2026-03-20 08:00:00",
				},
				{
					"name": "DF-EMP-0002",
					"display_name": "secret.jpg",
					"preview_status": "ready",
					"canonical_ref": "drv:ORG-0001:DF-EMP-0002",
					"slot": "profile_image",
					"current_version_no": 1,
					"folder": "DRF-EMP-0002",
					"attached_doctype": "Employee",
					"attached_name": "EMP-0002",
					"owner_doctype": "Employee",
					"owner_name": "EMP-0002",
					"modified": "2026-03-20 07:00:00",
				},
			],
			"Drive Binding": lambda **kwargs: [
				{
					"drive_file": "DF-EMP-0001",
					"binding_role": "employee_image",
					"is_primary": 1,
					"modified": "2026-03-20 08:00:00",
				},
				{
					"drive_file": "DF-EMP-0002",
					"binding_role": "employee_image",
					"is_primary": 1,
					"modified": "2026-03-20 07:00:00",
				},
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_folder_items_service({"folder": "DRF-EMP-ROOT"})

	assert [item["id"] for item in response["items"]] == ["DRF-EMP-0001", "DF-EMP-0001"]


def test_list_workspace_home_prioritizes_review_targets_then_personal_contexts():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	applicant_doc = FakeDoc({"name": "APP-0001"})
	employee_doc = FakeDoc({"name": "EMP-SELF"})
	organization_doc = FakeDoc({"name": "ORG-0001"})
	root_doc = FakeDoc(
		{
			"name": "DRF-ROOT-A",
			"title": "Admissions",
			"path_cache": "admissions",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Student Applicant",
			"context_name": "APP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Student Applicant", "APP-0001"): True,
			("Employee", "EMP-SELF"): True,
			("Organization", "ORG-0001"): True,
			("Drive Folder", "DRF-ROOT-A"): True,
		},
		docs_map={
			("Student Applicant", "APP-0001"): applicant_doc,
			("Employee", "EMP-SELF"): employee_doc,
			("Organization", "ORG-0001"): organization_doc,
			("Drive Folder", "DRF-ROOT-A"): root_doc,
		},
		get_all_handlers={
			"Applicant Review Assignment": lambda **kwargs: (
				[
					{
						"name": "ARA-0001",
						"student_applicant": "APP-0001",
						"target_type": "Applicant Health Profile",
						"target_name": "AHP-0001",
						"source_event": "health_declared_complete",
						"modified": "2026-03-20 12:00:00",
					}
				]
				if kwargs["filters"].get("assigned_to_user") == "reviewer@example.com"
				else []
			),
			"Employee": lambda **kwargs: (
				[
					{
						"name": "EMP-SELF",
						"employee_full_name": "Reviewer Self",
					}
				]
				if kwargs["filters"].get("user_id") == "reviewer@example.com"
				else []
			),
			"Student Applicant": lambda **kwargs: [],
			"Student": lambda **kwargs: [],
			"Drive Folder": lambda **kwargs: [
				{
					"name": "DRF-ROOT-A",
					"title": "Admissions",
					"path_cache": "admissions",
					"parent_drive_folder": None,
					"owner_doctype": "Organization",
					"owner_name": "ORG-0001",
					"folder_kind": "system_bound",
					"context_doctype": "Student Applicant",
					"context_name": "APP-0001",
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-20 11:00:00",
				}
			],
		},
		session_user="reviewer@example.com",
		roles=["Nurse"],
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_workspace_home_service({})

	assert [section["key"] for section in response["sections"]] == ["reviewing", "mine", "roots"]
	assert response["sections"][0]["items"][0]["href"] == "/drive_workspace?doctype=Student%20Applicant&name=APP-0001"
	assert response["sections"][1]["items"][0]["href"] == "/drive_workspace?doctype=Employee&name=EMP-SELF"
	assert response["sections"][2]["items"][0]["href"] == "/drive_workspace?folder=DRF-ROOT-A"
	assert response["suggested_target"]["href"] == "/drive_workspace?doctype=Student%20Applicant&name=APP-0001"
	assert response["suggested_target"]["auto_open"] is False
