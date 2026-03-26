<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
	browseContext,
	browseFolder,
	issueDownloadGrant,
	issuePreviewGrant,
	listWorkspaceHome,
	parseWorkspaceQuery
} from '@/features/workspace/api'
import type {
	FileSummary,
	FolderBreadcrumb,
	FolderItem,
	FolderSummary,
	WorkspaceHomeSection,
	WorkspaceHomeTarget
} from '@/features/workspace/types'

type StatusTone = 'neutral' | 'loading' | 'error'

type HomeRow = {
	id: string
	label: string
	caption?: string | null
	badge?: string | null
	href: string
	targetKind: 'folder' | 'context'
	sectionLabel: string
}

type RailNode = {
	id: string
	label: string
	caption: string
	href?: string
	isActive: boolean
	isMuted: boolean
}

const modeLabel = ref('Drive')
const heading = ref('Governed Files')
const subheading = ref('Browse governed files with record-based access.')
const statusMessage = ref('')
const statusTone = ref<StatusTone>('neutral')
const breadcrumbs = ref<FolderBreadcrumb[]>([])
const folderSummary = ref<FolderSummary | null>(null)
const items = ref<FolderItem[]>([])
const homeSections = ref<WorkspaceHomeSection[]>([])
const suggestedTarget = ref<WorkspaceHomeTarget | null>(null)

const query = parseWorkspaceQuery(window.location.search)

const hasTarget = computed(() => Boolean(query.folder || (query.doctype && query.name)))
const isHomeView = computed(() => !hasTarget.value)
const homeRows = computed<HomeRow[]>(() =>
	homeSections.value.flatMap((section) =>
		section.items.map((target) => ({
			id: target.id,
			label: target.label,
			caption: target.caption,
			badge: target.badge,
			href: target.href,
			targetKind: target.target_kind,
			sectionLabel: section.label
		}))
	)
)
const orderedItems = computed(() =>
	[...items.value].sort((left, right) => {
		if (left.item_type === right.item_type) return 0
		return left.item_type === 'folder' ? -1 : 1
	})
)
const scopeTitle = computed(() => {
	if (folderSummary.value?.title) return folderSummary.value.title
	if (query.doctype && query.name) return `${query.doctype} · ${query.name}`
	return 'Workspace'
})
const scopeDetail = computed(() => {
	if (folderSummary.value?.context_path) return folderSummary.value.context_path
	if (folderSummary.value?.path_cache) return folderSummary.value.path_cache
	if (query.bindingRole) return `Filtered to ${query.bindingRole}`
	if (query.doctype && query.name) return 'Read-only governed context'
	if (homeRows.value.length) return 'Choose a governed folder or context to open.'
	return 'No governed files are available to this account yet.'
})
const locationBadges = computed(() => {
	const badges: string[] = []
	if (isHomeView.value) {
		badges.push('Read only', 'Record governed')
		if (suggestedTarget.value?.badge) badges.push(suggestedTarget.value.badge)
		return badges
	}
	if (query.folder) badges.push('Folder')
	if (query.doctype && query.name) badges.push('Context')
	if (folderSummary.value?.folder_kind) badges.push(folderSummary.value.folder_kind)
	if (folderSummary.value?.is_private) badges.push('Private')
	return badges
})

function setStatus(message = '', tone: StatusTone = 'neutral') {
	statusMessage.value = message
	statusTone.value = tone
}

function folderLink(folderId: string): string {
	return `/drive_workspace?folder=${encodeURIComponent(folderId)}`
}

function titleForFile(file: FileSummary): string {
	return file.title || file.id || 'Untitled file'
}

function itemKindLabel(item: FolderItem | HomeRow): string {
	if ('targetKind' in item) return item.targetKind === 'folder' ? 'Folder' : 'Context'
	if (item.item_type === 'folder') return 'Folder'
	return item.binding_role || item.slot || 'File'
}

function itemLocationLabel(item: FolderItem | HomeRow): string {
	if ('targetKind' in item) return item.sectionLabel
	if (item.item_type === 'folder') return item.context_path || item.path_cache || 'Folder'
	return item.context_path || item.folder_path || 'Governed file'
}

function rowHref(item: FolderItem | HomeRow): string | undefined {
	if ('targetKind' in item) return item.href
	if (item.item_type === 'folder') return folderLink(item.id)
	return undefined
}

function titleForItem(item: FolderItem | HomeRow): string {
	if ('targetKind' in item) return item.label
	if (item.item_type === 'folder') return item.title
	return titleForFile(item)
}

function descriptionForItem(item: FolderItem | HomeRow): string {
	if ('targetKind' in item) return item.caption || item.sectionLabel
	if (item.item_type === 'folder') return item.context_path || item.path_cache || 'Folder'
	if (item.attached_to?.doctype && item.attached_to?.name) {
		return `Attached to ${item.attached_to.doctype} · ${item.attached_to.name}`
	}
	return item.folder_path || item.context_path || 'Governed file'
}

function currentRootKey(): string {
	if (query.doctype === 'Student Applicant') return 'admissions'
	if (query.doctype === 'Student') return 'students'
	if (query.doctype === 'Employee') return 'employees'
	if (query.doctype === 'Task' || query.doctype === 'Task Submission') return 'teaching'
	if (folderSummary.value?.title?.toLowerCase().includes('media')) return 'media'
	return 'my-drive'
}

function findFirstHomeTarget(predicate: (target: WorkspaceHomeTarget) => boolean): WorkspaceHomeTarget | null {
	for (const section of homeSections.value) {
		for (const target of section.items) {
			if (predicate(target)) return target
		}
	}
	return null
}

const railNodes = computed<RailNode[]>(() => {
	const admissions = findFirstHomeTarget((target) => target.doctype === 'Student Applicant')
	const students = findFirstHomeTarget((target) => target.doctype === 'Student')
	const employees = findFirstHomeTarget((target) => target.doctype === 'Employee')
	const teaching = findFirstHomeTarget(
		(target) => target.doctype === 'Task' || target.doctype === 'Task Submission'
	)
	const media = findFirstHomeTarget(
		(target) =>
			target.doctype === 'Organization' ||
			target.badge === 'Folder' ||
			target.label.toLowerCase().includes('media')
	)
	const currentKey = currentRootKey()

	return [
		{
			id: 'my-drive',
			label: 'My Drive',
			caption: 'Your governed folders and contexts',
			href: '/drive_workspace',
			isActive: isHomeView.value || currentKey === 'my-drive',
			isMuted: false
		},
		{
			id: 'admissions',
			label: 'Admissions',
			caption: 'Applicants and admissions evidence',
			href: admissions?.href,
			isActive: currentKey === 'admissions',
			isMuted: !admissions
		},
		{
			id: 'students',
			label: 'Students',
			caption: 'Student profiles and records',
			href: students?.href,
			isActive: currentKey === 'students',
			isMuted: !students
		},
		{
			id: 'employees',
			label: 'Employees',
			caption: 'Employee profile and HR files',
			href: employees?.href,
			isActive: currentKey === 'employees',
			isMuted: !employees
		},
		{
			id: 'teaching',
			label: 'Teaching',
			caption: 'Tasks, resources, and submissions',
			href: teaching?.href,
			isActive: currentKey === 'teaching',
			isMuted: !teaching
		},
		{
			id: 'media',
			label: 'Media',
			caption: 'Organization and school assets',
			href: media?.href,
			isActive: currentKey === 'media',
			isMuted: !media
		}
	]
})

async function openGrant(kind: 'preview' | 'download', file: FileSummary) {
	setStatus('')
	const grant =
		kind === 'preview'
			? await issuePreviewGrant(file.drive_file_id || file.id, file.canonical_ref)
			: await issueDownloadGrant(file.drive_file_id || file.id, file.canonical_ref)
	window.open(grant.url, '_blank', 'noopener')
}

async function loadWorkspace() {
	if (!hasTarget.value) {
		try {
			setStatus('Loading workspace...', 'loading')
			const response = await listWorkspaceHome()
			modeLabel.value = 'My Drive'
			heading.value = 'Governed Files'
			subheading.value = 'Browse readable folders and record-owned file collections.'
			homeSections.value = response.sections
			suggestedTarget.value = response.suggested_target || null
			items.value = []
			breadcrumbs.value = []
			folderSummary.value = null
			setStatus('')
		} catch (error) {
			const message = error instanceof Error ? error.message : 'Unable to load the workspace.'
			homeSections.value = []
			suggestedTarget.value = null
			items.value = []
			breadcrumbs.value = []
			folderSummary.value = null
			modeLabel.value = 'My Drive'
			heading.value = 'Governed Files'
			subheading.value = 'The workspace could not be loaded for this account.'
			setStatus(message, 'error')
		}
		return
	}

	try {
		setStatus('Loading location...', 'loading')
		homeSections.value = []
		suggestedTarget.value = null
		if (query.folder) {
			const response = await browseFolder(query.folder)
			modeLabel.value = 'Folder'
			heading.value = response.folder.title
			subheading.value = response.folder.context_path || response.folder.path_cache || 'Folder'
			breadcrumbs.value = response.folder.breadcrumbs || []
			folderSummary.value = response.folder
			items.value = response.items
			setStatus('')
			return
		}

		const doctype = query.doctype as string
		const name = query.name as string
		const response = await browseContext(doctype, name, query.bindingRole)
		modeLabel.value = 'Context'
		heading.value = `${doctype} · ${name}`
		subheading.value = query.bindingRole
			? `Read-only files filtered to ${query.bindingRole}`
			: 'Read-only context files'
		const normalizedItems: FolderItem[] = response.items?.length
			? response.items
			: response.files.map((file) => ({
					...file,
					item_type: 'file'
				}))
		const firstFolder = normalizedItems.find(
			(item) => item.item_type === 'folder'
		) as FolderSummary | undefined
		const firstFileWithFolder = normalizedItems.find(
			(item) => item.item_type === 'file' && item.folder
		) as FileSummary | undefined
		breadcrumbs.value = firstFolder?.breadcrumbs || firstFileWithFolder?.folder?.breadcrumbs || []
		folderSummary.value = firstFolder || firstFileWithFolder?.folder || null
		items.value = normalizedItems
		setStatus('')
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unable to load this location.'
		items.value = []
		breadcrumbs.value = []
		folderSummary.value = null
		setStatus(message, 'error')
	}
}

onMounted(() => {
	void loadWorkspace()
})
</script>

<template>
	<div class="drive-app">
		<main class="drive-shell drive-shell--browser">
			<aside class="drive-panel drive-sidebar">
				<div class="drive-sidebar__brand">
					<p class="drive-overline">Ifitwala Drive</p>
					<h1 class="drive-sidebar__title">Governed Files</h1>
					<p class="drive-sidebar__copy">Google Drive-style navigation with Ifitwala_Ed structure.</p>
				</div>

				<nav class="drive-tree" aria-label="Drive navigation">
					<template v-for="node in railNodes" :key="node.id">
						<a
							v-if="node.href"
							:href="node.href"
							:class="[
								'drive-tree__node',
								node.isActive ? 'drive-tree__node--active' : '',
								node.isMuted ? 'drive-tree__node--muted' : ''
							]"
						>
							<strong>{{ node.label }}</strong>
							<span>{{ node.caption }}</span>
						</a>
						<div
							v-else
							:class="[
								'drive-tree__node',
								node.isActive ? 'drive-tree__node--active' : '',
								node.isMuted ? 'drive-tree__node--muted' : ''
							]"
						>
							<strong>{{ node.label }}</strong>
							<span>{{ node.caption }}</span>
						</div>
					</template>
				</nav>

				<div class="drive-sidebar__rules">
					<p class="drive-overline">Access</p>
					<p class="drive-sidebar__copy">
						Files remain governed by the record you can already read. The workspace is a browser, not a second ACL system.
					</p>
				</div>
			</aside>

			<section class="drive-main">
				<header class="drive-panel drive-toolbar">
					<div class="drive-toolbar__intro">
						<p class="drive-overline">{{ modeLabel }}</p>
						<h2 class="drive-toolbar__title">{{ heading }}</h2>
						<p class="drive-toolbar__copy">{{ subheading }}</p>
					</div>

					<div class="drive-toolbar__meta">
						<div class="drive-toolbar__location">
							<p class="drive-toolbar__label">Current location</p>
							<p class="drive-toolbar__value">{{ scopeTitle }}</p>
							<p class="drive-toolbar__hint">{{ scopeDetail }}</p>
						</div>
						<div class="drive-toolbar__badges">
							<span v-for="badge in locationBadges" :key="badge" class="drive-badge">
								{{ badge }}
							</span>
						</div>
					</div>
				</header>

				<nav v-if="breadcrumbs.length" class="drive-panel drive-breadcrumbs" aria-label="Drive breadcrumbs">
					<a v-for="crumb in breadcrumbs" :key="crumb.id" class="drive-crumb" :href="folderLink(crumb.id)">
						{{ crumb.title || crumb.id }}
					</a>
				</nav>

				<div v-if="statusMessage" class="drive-panel drive-status" :data-tone="statusTone">
					<span>{{ statusMessage }}</span>
				</div>

				<section class="drive-panel drive-table-shell">
					<header class="drive-table-shell__head">
						<div>
							<p class="drive-overline">Contents</p>
							<h3 class="drive-table-shell__title">
								{{ isHomeView ? 'Drive locations' : scopeTitle }}
							</h3>
						</div>
						<p class="drive-table-shell__copy">
							{{ isHomeView ? `${homeRows.length} locations` : `${orderedItems.length} items` }}
						</p>
					</header>

					<div class="drive-table">
						<div class="drive-table__head">
							<span>Name</span>
							<span>Location</span>
							<span>Type</span>
							<span>Actions</span>
						</div>

						<article v-if="isHomeView && !homeRows.length" class="drive-empty">
							<h3 class="drive-empty__title">No governed files available</h3>
							<p class="drive-empty__copy">
								This account does not currently have a readable governed folder or context.
							</p>
						</article>

						<template v-else-if="isHomeView">
							<article v-for="row in homeRows" :key="row.id" class="drive-table__row">
								<div class="drive-table__cell drive-table__cell--name">
									<a class="drive-table__name" :href="row.href">{{ row.label }}</a>
									<p class="drive-table__description">{{ descriptionForItem(row) }}</p>
								</div>
								<div class="drive-table__cell">
									<span>{{ itemLocationLabel(row) }}</span>
								</div>
								<div class="drive-table__cell">
									<span class="drive-badge">{{ row.badge || itemKindLabel(row) }}</span>
								</div>
								<div class="drive-table__cell drive-table__cell--actions">
									<a class="drive-button drive-button--quiet" :href="row.href">
										{{ row.targetKind === 'folder' ? 'Open folder' : 'Open files' }}
									</a>
								</div>
							</article>
						</template>

						<article v-else-if="!orderedItems.length" class="drive-empty">
							<h3 class="drive-empty__title">No items in this location</h3>
							<p class="drive-empty__copy">This governed location is currently empty.</p>
						</article>

						<template v-else>
							<article
								v-for="item in orderedItems"
								:key="item.item_type + ':' + item.id"
								class="drive-table__row"
							>
								<div class="drive-table__cell drive-table__cell--name">
									<a v-if="rowHref(item)" class="drive-table__name" :href="rowHref(item)">
										{{ titleForItem(item) }}
									</a>
									<span v-else class="drive-table__name">{{ titleForItem(item) }}</span>
									<p class="drive-table__description">{{ descriptionForItem(item) }}</p>
								</div>
								<div class="drive-table__cell">
									<span>{{ itemLocationLabel(item) }}</span>
								</div>
								<div class="drive-table__cell">
									<span class="drive-badge">{{ itemKindLabel(item) }}</span>
								</div>
								<div class="drive-table__cell drive-table__cell--actions">
									<a
										v-if="item.item_type === 'folder'"
										class="drive-button drive-button--quiet"
										:href="folderLink(item.id)"
									>
										Open
									</a>
									<template v-else>
										<button
											class="drive-button drive-button--quiet"
											:disabled="!item.can_preview"
											@click="openGrant('preview', item)"
										>
											Preview
										</button>
										<button
											class="drive-button"
											:disabled="!item.can_download"
											@click="openGrant('download', item)"
										>
											Download
										</button>
									</template>
								</div>
							</article>
						</template>
					</div>
				</section>
			</section>
		</main>
	</div>
</template>
