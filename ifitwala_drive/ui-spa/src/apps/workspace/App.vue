<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
	browseContext,
	browseFolder,
	issueDownloadGrant,
	issuePreviewGrant,
	parseWorkspaceQuery
} from '@/features/workspace/api'
import type { FileSummary, FolderBreadcrumb, FolderItem, FolderSummary } from '@/features/workspace/types'

type StatusTone = 'neutral' | 'loading' | 'error'

const modeLabel = ref('Drive workspace')
const heading = ref('Drive Workspace')
const subheading = ref(
	'Context-first browsing owned by Ifitwala_drive. This surface is generic Drive UI and should be deep-linked from educational workflows.'
)
const statusMessage = ref('')
const statusTone = ref<StatusTone>('neutral')
const breadcrumbs = ref<FolderBreadcrumb[]>([])
const folderSummary = ref<FolderSummary | null>(null)
const items = ref<FolderItem[]>([])

const query = parseWorkspaceQuery(window.location.search)

const fileCount = computed(() => items.value.filter((item) => item.item_type === 'file').length)
const folderCount = computed(() => items.value.filter((item) => item.item_type === 'folder').length)
const hasTarget = computed(() => Boolean(query.folder || (query.doctype && query.name)))

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

function badgeForFile(file: FileSummary): string {
	return file.preview_status || file.binding_role || 'File'
}

function badgeForFolder(folder: FolderSummary): string {
	return folder.folder_kind || 'Folder'
}

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
		modeLabel.value = 'Drive workspace'
		heading.value = 'Open a Drive context or folder'
		subheading.value = 'Use query parameters like ?folder=<id> or ?doctype=<DocType>&name=<record>.'
		items.value = []
		breadcrumbs.value = []
		folderSummary.value = null
		return
	}

	try {
		setStatus('Loading workspace...', 'loading')
		if (query.folder) {
			const response = await browseFolder(query.folder)
			modeLabel.value = 'Folder browse'
			heading.value = response.folder.title
			subheading.value = response.folder.context_path || response.folder.path_cache || 'Folder browse mode'
			breadcrumbs.value = response.folder.breadcrumbs || []
			folderSummary.value = response.folder
			items.value = response.items
			setStatus('')
			return
		}

		const doctype = query.doctype as string
		const name = query.name as string
		const response = await browseContext(doctype, name, query.bindingRole)
		modeLabel.value = 'Context files'
		heading.value = `${doctype} · ${name}`
		subheading.value = query.bindingRole
			? `Context files for binding role ${query.bindingRole}`
			: 'Context file view'
		const normalizedFiles: FolderItem[] = response.files.map((file) => ({
			...file,
			item_type: 'file'
		}))
		breadcrumbs.value = response.files[0]?.folder?.breadcrumbs || []
		folderSummary.value = response.files[0]?.folder || null
		items.value = normalizedFiles
		setStatus('')
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unable to load Drive workspace.'
		items.value = []
		setStatus(message, 'error')
	}
}

onMounted(() => {
	void loadWorkspace()
})
</script>

<template>
	<div class="drive-app">
		<main class="drive-shell">
			<section class="drive-panel drive-hero">
				<div>
					<p class="drive-overline">{{ modeLabel }}</p>
					<h1 class="drive-title">{{ heading }}</h1>
					<p class="drive-subtitle">{{ subheading }}</p>
				</div>

				<div v-if="statusMessage" class="drive-status" :data-tone="statusTone">
					<span>{{ statusMessage }}</span>
				</div>

				<nav v-if="breadcrumbs.length" class="drive-breadcrumbs" aria-label="Drive breadcrumbs">
					<a
						v-for="crumb in breadcrumbs"
						:key="crumb.id"
						class="drive-crumb"
						:href="folderLink(crumb.id)"
					>
						{{ crumb.title || crumb.id }}
					</a>
				</nav>
			</section>

			<section class="drive-grid">
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Folders</p>
					<p class="drive-kpi__value">{{ folderCount }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Files</p>
					<p class="drive-kpi__value">{{ fileCount }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Mode</p>
					<p class="drive-kpi__value">{{ modeLabel }}</p>
				</article>
			</section>

			<section class="drive-list">
				<article v-if="!hasTarget" class="drive-panel drive-empty">
					<h2 class="drive-card__title">No target selected</h2>
					<p class="drive-card__path">
						This workspace is designed to be deep-linked from Ifitwala_Ed context surfaces while remaining
						owned by Ifitwala_drive.
					</p>
				</article>

				<article v-else-if="!items.length && !statusMessage" class="drive-panel drive-empty">
					<h2 class="drive-card__title">No items returned</h2>
					<p class="drive-card__path">This Drive surface is empty for the current context.</p>
				</article>

				<article v-for="item in items" :key="item.item_type + ':' + item.id" class="drive-panel drive-card">
					<div class="drive-card__head">
						<div>
							<p class="drive-card__meta">
								{{
									item.item_type === 'folder'
										? 'Folder'
										: [item.binding_role, item.slot].filter(Boolean).join(' · ') || 'File'
								}}
							</p>
							<h2 class="drive-card__title">
								{{ item.item_type === 'folder' ? item.title : titleForFile(item) }}
							</h2>
							<p v-if="item.context_path" class="drive-card__path">{{ item.context_path }}</p>
							<p
								v-if="
									item.item_type === 'file' &&
									item.attached_to?.doctype &&
									item.attached_to?.name
								"
								class="drive-card__path"
							>
								Attached to {{ item.attached_to.doctype }} · {{ item.attached_to.name }}
							</p>
						</div>

						<span class="drive-badge">
							{{ item.item_type === 'folder' ? badgeForFolder(item) : badgeForFile(item) }}
						</span>
					</div>

					<div class="drive-card__actions">
						<a
							v-if="item.item_type === 'folder'"
							class="drive-button"
							:href="folderLink(item.id)"
						>
							Open folder
						</a>

						<template v-else>
							<button
								class="drive-button"
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
							<a
								v-if="item.folder?.id"
								class="drive-button drive-button--quiet"
								:href="folderLink(item.folder.id)"
							>
								Open folder
							</a>
						</template>
					</div>
				</article>
			</section>
		</main>
	</div>
</template>
