import { callFrappeApi } from '@/lib/frappeApi'

import type {
	ContextBrowseResponse,
	FolderBrowseResponse,
	GrantResponse,
	WorkspaceHomeResponse,
	WorkspaceRootsResponse,
	WorkspaceQuery
} from './types'

export function parseWorkspaceQuery(search: string): WorkspaceQuery {
	const params = new URLSearchParams(search)
	const read = (key: string) => {
		const value = params.get(key)
		return value ? value.trim() : ''
	}

	return {
		folder: read('folder') || undefined,
		doctype: read('doctype') || undefined,
		name: read('name') || undefined,
		bindingRole: read('binding_role') || undefined
	}
}

export function browseFolder(folder: string): Promise<FolderBrowseResponse> {
	return callFrappeApi<FolderBrowseResponse>('ifitwala_drive.api.folders.list_folder_items', {
		folder,
		include_folders: 1,
		include_files: 1,
		limit: 100,
		offset: 0
	})
}

export function listWorkspaceRoots(): Promise<WorkspaceRootsResponse> {
	return callFrappeApi<WorkspaceRootsResponse>('ifitwala_drive.api.folders.list_workspace_roots', {
		limit: 24
	})
}

export function listWorkspaceHome(): Promise<WorkspaceHomeResponse> {
	return callFrappeApi<WorkspaceHomeResponse>('ifitwala_drive.api.folders.list_workspace_home', {
		limit: 6
	})
}

export function browseContext(
	doctype: string,
	name: string,
	bindingRole?: string
): Promise<ContextBrowseResponse> {
	return callFrappeApi<ContextBrowseResponse>('ifitwala_drive.api.folders.list_context_files', {
		doctype,
		name,
		...(bindingRole ? { binding_role: bindingRole } : {})
	})
}

export function issueDownloadGrant(
	driveFileId?: string,
	canonicalRef?: string | null
): Promise<GrantResponse> {
	return callFrappeApi<GrantResponse>('ifitwala_drive.api.access.issue_download_grant', {
		...(driveFileId ? { drive_file_id: driveFileId } : {}),
		...(canonicalRef ? { canonical_ref: canonicalRef } : {})
	})
}

export function issuePreviewGrant(
	driveFileId?: string,
	canonicalRef?: string | null
): Promise<GrantResponse> {
	return callFrappeApi<GrantResponse>('ifitwala_drive.api.access.issue_preview_grant', {
		...(driveFileId ? { drive_file_id: driveFileId } : {}),
		...(canonicalRef ? { canonical_ref: canonicalRef } : {})
	})
}
