from __future__ import annotations

import importlib
import sys
import types


def _purge_modules(*prefixes: str) -> None:
	internal_prefixes = (
		"ifitwala_drive.services.integration.ifitwala_ed_bridge",
		"ifitwala_drive.services.integration._ed_delegate",
	)
	for module_name in list(sys.modules):
		if any(
			module_name == prefix or module_name.startswith(f"{prefix}.")
			for prefix in (*prefixes, *internal_prefixes)
		):
			sys.modules.pop(module_name, None)


class FakeDoc:
	def __init__(self, data=None):
		for key, value in (data or {}).items():
			setattr(self, key, value)

	def check_permission(self, permission_type=None):
		permission_errors = getattr(self, "permission_errors", None)
		if isinstance(permission_errors, dict) and permission_errors.get(permission_type):
			raise RuntimeError("Permission denied")
		if getattr(self, "permission_error", False):
			raise RuntimeError("Permission denied")
		return None


def _install_fake_frappe(
	*, exists_map=None, docs_map=None, get_all_handlers=None, session_user="tester@example.com", roles=None
):
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
		"folders": [],
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
							"display_title": "Task",
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
					"display_path": "Student / Task / Submissions",
					"display_caption": "Student / Task / Submissions",
				},
				"folder_path": "student/task-0001/submissions",
				"context_path": "Student / TASK-0001 / Submissions",
				"display_path": "Student / Task / Submissions",
				"attached_to": {
					"doctype": "Task Submission",
					"name": "TSUB-0001",
				},
				"can_preview": False,
				"can_download": True,
			}
		],
		"items": [
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
							"display_title": "Task",
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
					"display_path": "Student / Task / Submissions",
					"display_caption": "Student / Task / Submissions",
				},
				"folder_path": "student/task-0001/submissions",
				"context_path": "Student / TASK-0001 / Submissions",
				"display_path": "Student / Task / Submissions",
				"attached_to": {
					"doctype": "Task Submission",
					"name": "TSUB-0001",
				},
				"can_preview": False,
				"can_download": True,
				"item_type": "file",
			}
		],
		"upload_actions": [
			{
				"id": "task_submission_artifact",
				"label": "Upload Submission Artifact",
				"description": "Add a governed artifact to this Task Submission.",
				"api_method": "ifitwala_drive.api.submissions.upload_task_submission_artifact",
				"payload": {
					"task_submission": "TSUB-0001",
					"upload_source": "SPA",
				},
				"destination_label": "Submission Artifacts",
			}
		],
	}


def test_list_context_files_uses_semantic_task_titles_in_submission_paths():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	task_submission = FakeDoc({"name": "TSUB-0001"})
	student_doc = FakeDoc({"name": "STU-0001", "student_full_name": "Jane Doe"})
	task_doc = FakeDoc({"name": "TASK-0001", "title": "Biology Quiz 3"})
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
		exists_map={
			("Task Submission", "TSUB-0001"): True,
			("Student", "STU-0001"): True,
			("Task", "TASK-0001"): True,
		},
		docs_map={
			("Task Submission", "TSUB-0001"): task_submission,
			("Student", "STU-0001"): student_doc,
			("Task", "TASK-0001"): task_doc,
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

	folder = response["files"][0]["folder"]
	assert folder["display_path"] == "Jane Doe / Biology Quiz 3 / Submissions"
	assert folder["breadcrumbs"][0]["display_title"] == "Jane Doe"
	assert folder["breadcrumbs"][0]["display_code"] == "STU-0001"
	assert folder["breadcrumbs"][1]["display_title"] == "Biology Quiz 3"
	assert folder["breadcrumbs"][1]["display_code"] == "TASK-0001"


def test_list_context_files_returns_direct_owner_files_without_binding():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	task_submission = FakeDoc({"name": "TSUB-0002"})
	_install_fake_frappe(
		exists_map={("Task Submission", "TSUB-0002"): True},
		docs_map={
			("Task Submission", "TSUB-0002"): task_submission,
		},
		get_all_handlers={
			"Drive Binding": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [
				{
					"name": "DF-0002",
					"canonical_ref": "drv:ORG-0001:DF-0002",
					"slot": "submission",
					"display_name": "essay-final.docx",
					"current_version_no": 1,
					"preview_status": "pending",
					"folder": None,
					"attached_doctype": "Task Submission",
					"attached_name": "TSUB-0002",
					"owner_doctype": "Task Submission",
					"owner_name": "TSUB-0002",
				}
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service(
		{
			"doctype": "Task Submission",
			"name": "TSUB-0002",
		}
	)

	assert response == {
		"context": {"doctype": "Task Submission", "name": "TSUB-0002"},
		"folders": [],
		"files": [
			{
				"id": "DF-0002",
				"drive_file_id": "DF-0002",
				"canonical_ref": "drv:ORG-0001:DF-0002",
				"slot": "submission",
				"title": "essay-final.docx",
				"current_version_no": 1,
				"preview_status": "pending",
				"binding_role": "submission_artifact",
				"folder": None,
				"folder_path": None,
				"context_path": None,
				"attached_to": {
					"doctype": "Task Submission",
					"name": "TSUB-0002",
				},
				"can_preview": False,
				"can_download": True,
			}
		],
		"items": [
			{
				"id": "DF-0002",
				"drive_file_id": "DF-0002",
				"canonical_ref": "drv:ORG-0001:DF-0002",
				"slot": "submission",
				"title": "essay-final.docx",
				"current_version_no": 1,
				"preview_status": "pending",
				"binding_role": "submission_artifact",
				"folder": None,
				"folder_path": None,
				"context_path": None,
				"attached_to": {
					"doctype": "Task Submission",
					"name": "TSUB-0002",
				},
				"can_preview": False,
				"can_download": True,
				"item_type": "file",
			}
		],
		"upload_actions": [
			{
				"id": "task_submission_artifact",
				"label": "Upload Submission Artifact",
				"description": "Add a governed artifact to this Task Submission.",
				"api_method": "ifitwala_drive.api.submissions.upload_task_submission_artifact",
				"payload": {
					"task_submission": "TSUB-0002",
					"upload_source": "SPA",
				},
				"destination_label": "Submission Artifacts",
			}
		],
	}


def test_list_context_files_derives_supporting_material_role_for_supporting_material():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	material = FakeDoc({"name": "MAT-0001"})
	_install_fake_frappe(
		exists_map={("Supporting Material", "MAT-0001"): True},
		docs_map={
			("Supporting Material", "MAT-0001"): material,
		},
		get_all_handlers={
			"Drive Binding": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [
				{
					"name": "DF-MAT-0001",
					"canonical_ref": "drv:ORG-0001:DF-MAT-0001",
					"slot": "material_file",
					"display_name": "worksheet.pdf",
					"current_version_no": 1,
					"preview_status": "pending",
					"folder": None,
					"attached_doctype": "Supporting Material",
					"attached_name": "MAT-0001",
					"owner_doctype": "Supporting Material",
					"owner_name": "MAT-0001",
				}
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service(
		{
			"doctype": "Supporting Material",
			"name": "MAT-0001",
			"binding_role": "supporting_material",
		}
	)

	assert response["context"] == {"doctype": "Supporting Material", "name": "MAT-0001"}
	assert response["folders"] == []
	assert len(response["files"]) == 1
	assert response["files"][0]["binding_role"] == "supporting_material"
	assert response["items"][0]["binding_role"] == "supporting_material"
	assert response["upload_actions"] == [
		{
			"id": "supporting_material",
			"label": "Upload Material File",
			"description": "Add the governed file for this Supporting Material record.",
			"api_method": "ifitwala_drive.api.materials.upload_supporting_material",
			"payload": {
				"material": "MAT-0001",
				"upload_source": "SPA",
			},
			"destination_label": "Course Materials",
		}
	]


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


def test_list_workspace_roots_masks_opaque_root_titles():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	organization_doc = FakeDoc({"name": "ORG-0001"})
	opaque_root = FakeDoc(
		{
			"name": "DRF-ROOT-EMP",
			"title": "DRF-06B68124933A03E9",
			"path_cache": "drf-06b68124933a03e9",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Employee",
			"context_name": None,
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Organization", "ORG-0001"): True,
			("Drive Folder", "DRF-ROOT-EMP"): True,
		},
		docs_map={
			("Organization", "ORG-0001"): organization_doc,
			("Drive Folder", "DRF-ROOT-EMP"): opaque_root,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: [
				{
					"name": "DRF-ROOT-EMP",
					"title": "DRF-06B68124933A03E9",
					"path_cache": "drf-06b68124933a03e9",
					"parent_drive_folder": None,
					"owner_doctype": "Organization",
					"owner_name": "ORG-0001",
					"folder_kind": "system_bound",
					"context_doctype": "Employee",
					"context_name": None,
					"is_system_managed": 1,
					"is_private": 1,
					"modified": "2026-03-19 09:00:00",
				}
			],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_workspace_roots_service({})

	assert response == {
		"roots": [
			{
				"id": "DRF-ROOT-EMP",
				"title": "DRF-06B68124933A03E9",
				"display_title": "Employee",
				"path_cache": "drf-06b68124933a03e9",
				"context_path": "DRF-06B68124933A03E9",
				"display_path": "Employee",
				"folder_kind": "system_bound",
				"parent_folder": None,
				"breadcrumbs": [
					{
						"id": "DRF-ROOT-EMP",
						"title": "DRF-06B68124933A03E9",
						"display_title": "Employee",
						"path_cache": "drf-06b68124933a03e9",
					}
				],
				"owner": {
					"doctype": "Organization",
					"name": "ORG-0001",
				},
				"context": None,
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


def test_list_folder_items_exposes_semantic_employee_titles_with_codes():
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
	employee_doc = FakeDoc({"name": "EMP-0001", "employee_full_name": "Ada Lovelace"})
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
	organization_doc = FakeDoc({"name": "ORG-0001"})
	_install_fake_frappe(
		exists_map={
			("Drive Folder", "DRF-EMP-ROOT"): True,
			("Drive Folder", "DRF-EMP-0001"): True,
			("Organization", "ORG-0001"): True,
			("Employee", "EMP-0001"): True,
		},
		docs_map={
			("Drive Folder", "DRF-EMP-ROOT"): root_doc,
			("Drive Folder", "DRF-EMP-0001"): child_visible,
			("Organization", "ORG-0001"): organization_doc,
			("Employee", "EMP-0001"): employee_doc,
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
				}
			],
			"Drive File": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_folder_items_service({"folder": "DRF-EMP-ROOT"})

	folder = response["items"][0]
	assert folder["display_title"] == "Ada Lovelace"
	assert folder["display_code"] == "EMP-0001"
	assert folder["display_path"] == "Employees / Ada Lovelace"
	assert folder["breadcrumbs"][1]["display_title"] == "Ada Lovelace"
	assert folder["breadcrumbs"][1]["display_code"] == "EMP-0001"


def test_list_context_files_returns_employee_child_folders_when_no_files_exist():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	employee_doc = FakeDoc(
		{
			"name": "EMP-0001",
			"organization": "ORG-0001",
			"school": "SCH-0001",
		}
	)
	organization_doc = FakeDoc({"name": "ORG-0001"})
	employee_root = FakeDoc(
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
	profile_folder = FakeDoc(
		{
			"name": "DRF-EMP-PROFILE",
			"title": "Profile",
			"path_cache": "employees/emp-0001/profile",
			"parent_drive_folder": "DRF-EMP-0001",
			"owner_doctype": "Employee",
			"owner_name": "EMP-0001",
			"folder_kind": "staff_documents",
			"context_doctype": "Employee",
			"context_name": "EMP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	employees_root = FakeDoc(
		{
			"name": "DRF-EMP-ROOT",
			"title": "Employees",
			"path_cache": "employees",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Employee",
			"context_name": None,
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	employee_image_folder = FakeDoc(
		{
			"name": "DRF-EMP-IMAGE",
			"title": "Employee Image",
			"path_cache": "employees/emp-0001/profile/employee-image",
			"parent_drive_folder": "DRF-EMP-PROFILE",
			"owner_doctype": "Employee",
			"owner_name": "EMP-0001",
			"folder_kind": "staff_documents",
			"context_doctype": "Employee",
			"context_name": "EMP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Employee", "EMP-0001"): True,
			("Organization", "ORG-0001"): True,
			("Drive Folder", "DRF-EMP-ROOT"): True,
			("Drive Folder", "DRF-EMP-0001"): True,
			("Drive Folder", "DRF-EMP-PROFILE"): True,
			("Drive Folder", "DRF-EMP-IMAGE"): True,
		},
		docs_map={
			("Employee", "EMP-0001"): employee_doc,
			("Organization", "ORG-0001"): organization_doc,
			("Drive Folder", "DRF-EMP-ROOT"): employees_root,
			("Drive Folder", "DRF-EMP-0001"): employee_root,
			("Drive Folder", "DRF-EMP-PROFILE"): profile_folder,
			("Drive Folder", "DRF-EMP-IMAGE"): employee_image_folder,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: (
				[
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
						"name": "DRF-EMP-PROFILE",
						"title": "Profile",
						"path_cache": "employees/emp-0001/profile",
						"parent_drive_folder": "DRF-EMP-0001",
						"owner_doctype": "Employee",
						"owner_name": "EMP-0001",
						"folder_kind": "staff_documents",
						"context_doctype": "Employee",
						"context_name": "EMP-0001",
						"is_system_managed": 1,
						"is_private": 1,
						"modified": "2026-03-20 09:00:00",
					},
					{
						"name": "DRF-EMP-IMAGE",
						"title": "Employee Image",
						"path_cache": "employees/emp-0001/profile/employee-image",
						"parent_drive_folder": "DRF-EMP-PROFILE",
						"owner_doctype": "Employee",
						"owner_name": "EMP-0001",
						"folder_kind": "staff_documents",
						"context_doctype": "Employee",
						"context_name": "EMP-0001",
						"is_system_managed": 1,
						"is_private": 1,
						"modified": "2026-03-20 08:00:00",
					},
				]
				if kwargs["filters"].get("context_name") == "EMP-0001"
				else [
					{
						"name": "DRF-EMP-PROFILE",
						"title": "Profile",
						"path_cache": "employees/emp-0001/profile",
						"parent_drive_folder": "DRF-EMP-0001",
						"owner_doctype": "Employee",
						"owner_name": "EMP-0001",
						"folder_kind": "staff_documents",
						"context_doctype": "Employee",
						"context_name": "EMP-0001",
						"is_system_managed": 1,
						"is_private": 1,
						"modified": "2026-03-20 09:00:00",
					}
				]
			),
			"Drive Binding": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service({"doctype": "Employee", "name": "EMP-0001"})

	assert response["context"] == {"doctype": "Employee", "name": "EMP-0001"}
	assert response["files"] == []
	assert [folder["id"] for folder in response["folders"]] == ["DRF-EMP-PROFILE"]
	assert response["folders"][0]["context_path"] == "Employees / EMP-0001 / Profile"
	assert response["items"][0]["id"] == "DRF-EMP-PROFILE"
	assert response["upload_actions"] == [
		{
			"id": "employee_image",
			"label": "Upload Employee Image",
			"description": "Create or replace the governed employee profile image.",
			"api_method": "ifitwala_drive.api.media.upload_employee_image",
			"payload": {
				"employee": "EMP-0001",
				"upload_source": "SPA",
			},
			"destination_label": "Employee Image",
		}
	]


def test_list_context_files_exposes_semantic_employee_context_metadata():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	employee_doc = FakeDoc(
		{
			"name": "EMP-0001",
			"employee_full_name": "Ada Lovelace",
			"organization": "ORG-0001",
			"school": "SCH-0001",
		}
	)
	organization_doc = FakeDoc({"name": "ORG-0001"})
	employee_root = FakeDoc(
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
	profile_folder = FakeDoc(
		{
			"name": "DRF-EMP-PROFILE",
			"title": "Profile",
			"path_cache": "employees/emp-0001/profile",
			"parent_drive_folder": "DRF-EMP-0001",
			"owner_doctype": "Employee",
			"owner_name": "EMP-0001",
			"folder_kind": "staff_documents",
			"context_doctype": "Employee",
			"context_name": "EMP-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	employees_root = FakeDoc(
		{
			"name": "DRF-EMP-ROOT",
			"title": "Employees",
			"path_cache": "employees",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "system_bound",
			"context_doctype": "Employee",
			"context_name": None,
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Employee", "EMP-0001"): True,
			("Organization", "ORG-0001"): True,
			("Drive Folder", "DRF-EMP-ROOT"): True,
			("Drive Folder", "DRF-EMP-0001"): True,
			("Drive Folder", "DRF-EMP-PROFILE"): True,
		},
		docs_map={
			("Employee", "EMP-0001"): employee_doc,
			("Organization", "ORG-0001"): organization_doc,
			("Drive Folder", "DRF-EMP-ROOT"): employees_root,
			("Drive Folder", "DRF-EMP-0001"): employee_root,
			("Drive Folder", "DRF-EMP-PROFILE"): profile_folder,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: (
				[
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
						"name": "DRF-EMP-PROFILE",
						"title": "Profile",
						"path_cache": "employees/emp-0001/profile",
						"parent_drive_folder": "DRF-EMP-0001",
						"owner_doctype": "Employee",
						"owner_name": "EMP-0001",
						"folder_kind": "staff_documents",
						"context_doctype": "Employee",
						"context_name": "EMP-0001",
						"is_system_managed": 1,
						"is_private": 1,
						"modified": "2026-03-20 09:00:00",
					},
				]
				if kwargs["filters"].get("context_name") == "EMP-0001"
				else [
					{
						"name": "DRF-EMP-PROFILE",
						"title": "Profile",
						"path_cache": "employees/emp-0001/profile",
						"parent_drive_folder": "DRF-EMP-0001",
						"owner_doctype": "Employee",
						"owner_name": "EMP-0001",
						"folder_kind": "staff_documents",
						"context_doctype": "Employee",
						"context_name": "EMP-0001",
						"is_system_managed": 1,
						"is_private": 1,
						"modified": "2026-03-20 09:00:00",
					}
				]
			),
			"Drive Binding": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service({"doctype": "Employee", "name": "EMP-0001"})

	assert response["context"] == {
		"doctype": "Employee",
		"name": "EMP-0001",
		"display_title": "Ada Lovelace",
		"display_code": "EMP-0001",
	}
	assert response["folders"][0]["display_path"] == "Employees / Ada Lovelace / Profile"
	assert response["folders"][0]["breadcrumbs"][1]["display_title"] == "Ada Lovelace"
	assert response["folders"][0]["breadcrumbs"][1]["display_code"] == "EMP-0001"


def test_list_context_files_omits_upload_actions_when_context_is_not_writable():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	material = FakeDoc({"name": "MAT-READONLY", "permission_errors": {"write": True}})
	_install_fake_frappe(
		exists_map={("Supporting Material", "MAT-READONLY"): True},
		docs_map={
			("Supporting Material", "MAT-READONLY"): material,
		},
		get_all_handlers={
			"Drive Binding": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [],
			"Drive Folder": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service(
		{
			"doctype": "Supporting Material",
			"name": "MAT-READONLY",
		}
	)

	assert response["context"] == {"doctype": "Supporting Material", "name": "MAT-READONLY"}
	assert response["files"] == []
	assert response["items"] == []
	assert "upload_actions" not in response


def test_list_folder_items_exposes_task_resource_upload_action_for_task_folders():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	task_doc = FakeDoc({"name": "TASK-0001"})
	resources_folder = FakeDoc(
		{
			"name": "DRF-TASK-RESOURCES",
			"title": "Resources",
			"path_cache": "courses/course-0001/tasks/task-0001/resources",
			"owner_doctype": "Task",
			"owner_name": "TASK-0001",
			"folder_kind": "course_shared",
			"context_doctype": "Task",
			"context_name": "TASK-0001",
			"is_system_managed": 1,
			"is_private": 1,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Drive Folder", "DRF-TASK-RESOURCES"): True,
			("Task", "TASK-0001"): True,
		},
		docs_map={
			("Drive Folder", "DRF-TASK-RESOURCES"): resources_folder,
			("Task", "TASK-0001"): task_doc,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_folder_items_service({"folder": "DRF-TASK-RESOURCES"})

	assert response["folder"]["id"] == "DRF-TASK-RESOURCES"
	assert response["upload_actions"] == [
		{
			"id": "task_resource",
			"label": "Upload Resource",
			"description": "Add a governed file to this Task's Resources folder.",
			"api_method": "ifitwala_drive.api.resources.upload_task_resource",
			"payload": {
				"task": "TASK-0001",
				"upload_source": "SPA",
			},
			"destination_label": "Task Resources",
		}
	]


def test_list_folder_items_exposes_organization_logo_upload_for_logo_folder():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	organization_doc = FakeDoc({"name": "ORG-0001"})
	logos_folder = FakeDoc(
		{
			"name": "DRF-ORG-LOGOS",
			"title": "Logos",
			"path_cache": "organization-media/logos",
			"owner_doctype": "Organization",
			"owner_name": "ORG-0001",
			"folder_kind": "organization_media",
			"context_doctype": "Organization",
			"context_name": "ORG-0001",
			"is_system_managed": 1,
			"is_private": 0,
		}
	)
	_install_fake_frappe(
		exists_map={
			("Drive Folder", "DRF-ORG-LOGOS"): True,
			("Organization", "ORG-0001"): True,
		},
		docs_map={
			("Drive Folder", "DRF-ORG-LOGOS"): logos_folder,
			("Organization", "ORG-0001"): organization_doc,
		},
		get_all_handlers={
			"Drive Folder": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_folder_items_service({"folder": "DRF-ORG-LOGOS"})

	assert response["folder"]["id"] == "DRF-ORG-LOGOS"
	assert response["upload_actions"] == [
		{
			"id": "organization_logo",
			"label": "Upload Organization Logo",
			"description": "Replace the governed organization logo used across Ifitwala_Ed.",
			"api_method": "ifitwala_drive.api.media.upload_organization_logo",
			"payload": {
				"organization": "ORG-0001",
				"upload_source": "SPA",
			},
			"destination_label": "Organization Logos",
		}
	]


def test_list_context_files_exposes_applicant_profile_upload_action():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	applicant = FakeDoc({"name": "APP-0001"})
	_install_fake_frappe(
		exists_map={("Student Applicant", "APP-0001"): True},
		docs_map={
			("Student Applicant", "APP-0001"): applicant,
		},
		get_all_handlers={
			"Drive Binding": lambda **kwargs: [],
			"Drive File": lambda **kwargs: [],
			"Drive Folder": lambda **kwargs: [],
		},
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_context_files_service(
		{
			"doctype": "Student Applicant",
			"name": "APP-0001",
		}
	)

	assert response["context"] == {"doctype": "Student Applicant", "name": "APP-0001"}
	assert response["files"] == []
	assert response["items"] == []
	assert response["upload_actions"] == [
		{
			"id": "applicant_profile_image",
			"label": "Upload Applicant Image",
			"description": "Create or replace the governed applicant profile image.",
			"api_method": "ifitwala_drive.api.admissions.upload_applicant_profile_image",
			"payload": {
				"student_applicant": "APP-0001",
				"upload_source": "SPA",
			},
			"destination_label": "Applicant Profile",
		}
	]


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
	assert (
		response["sections"][0]["items"][0]["href"]
		== "/drive_workspace?doctype=Student%20Applicant&name=APP-0001"
	)
	assert response["sections"][1]["items"][0]["href"] == "/drive_workspace?doctype=Employee&name=EMP-SELF"
	assert response["sections"][2]["items"][0]["href"] == "/drive_workspace?folder=DRF-ROOT-A"
	assert (
		response["suggested_target"]["href"] == "/drive_workspace?doctype=Student%20Applicant&name=APP-0001"
	)
	assert response["suggested_target"]["auto_open"] is False


def test_list_workspace_home_includes_hr_employee_directory_targets():
	_purge_modules("frappe", "ifitwala_drive.services.folders.browse")
	readable_employee = FakeDoc({"name": "EMP-0001", "employee_full_name": "Ada Lovelace"})
	forbidden_employee = FakeDoc({"name": "EMP-0002", "permission_error": True})
	_install_fake_frappe(
		exists_map={
			("Employee", "EMP-0001"): True,
			("Employee", "EMP-0002"): True,
		},
		docs_map={
			("Employee", "EMP-0001"): readable_employee,
			("Employee", "EMP-0002"): forbidden_employee,
		},
		get_all_handlers={
			"Applicant Review Assignment": lambda **kwargs: [],
			"Employee": lambda **kwargs: (
				[
					{
						"name": "EMP-0001",
						"employee_full_name": "Ada Lovelace",
						"school": "SCH-0001",
						"modified": "2026-03-20 12:00:00",
					},
					{
						"name": "EMP-0002",
						"employee_full_name": "Hidden Person",
						"school": "SCH-0002",
						"modified": "2026-03-20 11:00:00",
					},
				]
				if kwargs["filters"].get("employment_status") == "Active"
				else []
			),
			"Student Applicant": lambda **kwargs: [],
			"Student": lambda **kwargs: [],
			"Drive Folder": lambda **kwargs: [],
		},
		session_user="hr.manager@example.com",
		roles=["HR Manager"],
	)
	module = _load_module("ifitwala_drive.services.folders.browse")

	response = module.list_workspace_home_service({})

	assert [section["key"] for section in response["sections"]] == ["employees"]
	assert response["sections"][0]["items"] == [
		{
			"id": "context:Employee:EMP-0001",
			"target_kind": "context",
			"label": "Ada Lovelace",
			"caption": "EMP-0001 \u00b7 SCH-0001",
			"display_code": "EMP-0001",
			"badge": "Employee",
			"href": "/drive_workspace?doctype=Employee&name=EMP-0001",
			"folder": None,
			"doctype": "Employee",
			"name": "EMP-0001",
			"binding_role": None,
		}
	]
	assert response["suggested_target"]["href"] == "/drive_workspace?doctype=Employee&name=EMP-0001"
	assert response["suggested_target"]["auto_open"] is True
