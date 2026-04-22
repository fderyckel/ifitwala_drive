export type FolderBreadcrumb = {
	id: string
	title: string
	display_title?: string | null
	display_code?: string | null
	path_cache?: string | null
}

export type UploadActionField = {
	name: string
	label: string
	required?: boolean
	placeholder?: string | null
	help?: string | null
}

export type UploadAction = {
	id: string
	label: string
	description: string
	api_method: string
	payload: Record<string, unknown>
	destination_label: string
	fields?: UploadActionField[]
}

export type FolderSummary = {
	id: string
	title: string
	display_title?: string | null
	display_code?: string | null
	path_cache?: string | null
	context_path?: string | null
	display_path?: string | null
	display_caption?: string | null
	folder_kind?: string | null
	parent_folder?: string | null
	breadcrumbs?: FolderBreadcrumb[]
	owner?: { doctype?: string | null; name?: string | null } | null
	context?: { doctype?: string | null; name?: string | null } | null
	is_system_managed?: boolean | null
	is_private?: boolean | null
}

export type AttachedTo = {
	doctype?: string | null
	name?: string | null
}

export type FileSummary = {
	id: string
	drive_file_id?: string
	title?: string | null
	display_title?: string | null
	canonical_ref?: string | null
	slot?: string | null
	current_version_no?: number | null
	preview_status?: string | null
	binding_role?: string | null
	folder?: FolderSummary | null
	folder_path?: string | null
	context_path?: string | null
	display_path?: string | null
	attached_to?: AttachedTo
	can_preview?: boolean
	can_download?: boolean
	item_type?: 'file'
}

export type FolderItem = (FolderSummary & { item_type: 'folder' }) | (FileSummary & { item_type: 'file' })

export type FolderBrowseResponse = {
	folder: FolderSummary
	items: FolderItem[]
	upload_actions?: UploadAction[]
}

export type WorkspaceRootsResponse = {
	roots: FolderSummary[]
}

export type WorkspaceHomeTarget = {
	id: string
	target_kind: 'folder' | 'context'
	label: string
	caption?: string | null
	display_code?: string | null
	badge?: string | null
	href: string
	folder?: string | null
	doctype?: string | null
	name?: string | null
	binding_role?: string | null
	auto_open?: boolean
}

export type WorkspaceHomeSection = {
	key: string
	label: string
	description?: string | null
	items: WorkspaceHomeTarget[]
}

export type WorkspaceHomeResponse = {
	sections: WorkspaceHomeSection[]
	suggested_target?: WorkspaceHomeTarget | null
}

export type ContextSummary = {
	doctype: string
	name: string
	display_title?: string | null
	display_code?: string | null
}

export type ContextBrowseResponse = {
	context: ContextSummary
	folders?: FolderSummary[]
	files: FileSummary[]
	items?: FolderItem[]
	upload_actions?: UploadAction[]
}

export type GrantResponse = {
	grant_type: string
	url: string
	expires_on: string
	preview_status?: string
}

export type WorkspaceQuery = {
	folder?: string
	doctype?: string
	name?: string
	bindingRole?: string
}
