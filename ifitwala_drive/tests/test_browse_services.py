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
		return None


def _install_fake_frappe(*, exists_map=None, docs_map=None, get_all_handlers=None):
	exists_map = exists_map or {}
	docs_map = docs_map or {}
	get_all_handlers = get_all_handlers or {}

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
