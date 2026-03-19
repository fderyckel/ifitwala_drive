<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
	browseContext,
	browseFolder,
	issueDownloadGrant,
	issuePreviewGrant,
	listWorkspaceRoots,
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
const hasVisibleRoots = computed(() => !hasTarget.value && items.value.length > 0)
const currentContextUrl = computed(() => {
	if (!(query.doctype && query.name)) return ''
	const params = new URLSearchParams({
		doctype: query.doctype,
		name: query.name
	})
	if (query.bindingRole) params.set('binding_role', query.bindingRole)
	return `/drive_workspace?${params.toString()}`
})
const itemCountLabel = computed(() => {
	if (!hasTarget.value) return 'Awaiting target'
	const count = items.value.length
	return `${count} ${count === 1 ? 'item' : 'items'}`
})
const scopeTitle = computed(() => {
	if (folderSummary.value?.title) return folderSummary.value.title
	if (query.doctype && query.name) return `${query.doctype} · ${query.name}`
	return 'No target selected'
})
const scopeDetail = computed(() => {
	if (folderSummary.value?.context_path) return folderSummary.value.context_path
	if (folderSummary.value?.path_cache) return folderSummary.value.path_cache
	if (query.bindingRole) return `Binding role: ${query.bindingRole}`
	if (query.doctype && query.name) return 'Context-governed browse'
	if (hasVisibleRoots.value) return 'Choose a governed root available to your permissions.'
	return 'No governed roots are available to your current permissions yet.'
})
const scopeBadges = computed(() => {
	if (!hasTarget.value) {
		return ['Drive-owned surface', 'Context first']
	}

	const badges: string[] = []
	if (query.folder) badges.push('Folder browse')
	if (query.doctype && query.name) badges.push('Context browse')
	if (folderSummary.value?.folder_kind) badges.push(folderSummary.value.folder_kind)
	if (folderSummary.value?.is_system_managed) badges.push('System managed')
	if (folderSummary.value?.is_private) badges.push('Private')
	if (query.bindingRole) badges.push(query.bindingRole)
	return badges.slice(0, 4)
})
const railLinks = computed(() => {
	const links = [
		{
			label: 'Workspace home',
			caption: 'Await a governed deep link',
			href: '/drive_workspace',
			isActive: !hasTarget.value,
			isMuted: false
		}
	]

	if (query.folder) {
		links.push({
			label: 'Current folder',
			caption: scopeTitle.value,
			href: folderLink(query.folder),
			isActive: true,
			isMuted: false
		})
	}

	if (currentContextUrl.value) {
		links.push({
			label: 'Current context',
			caption: `${query.doctype} · ${query.name}`,
			href: currentContextUrl.value,
			isActive: !query.folder,
			isMuted: false
		})
	}

	links.push(
		{
			label: 'Recent',
			caption: 'Planned workspace view',
			href: '',
			isActive: false,
			isMuted: true
		},
		{
			label: 'Shared with me',
			caption: 'Planned workspace view',
			href: '',
			isActive: false,
			isMuted: true
		}
	)

	return links
})
const orderedItems = computed(() => {
	return [...items.value].sort((left, right) => {
		if (left.item_type === right.item_type) return 0
		return left.item_type === 'folder' ? -1 : 1
	})
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
		try {
			setStatus('Loading workspace home...', 'loading')
			const response = await listWorkspaceRoots()
			modeLabel.value = 'Workspace home'
			heading.value = 'Your Drive workspace'
			subheading.value = response.roots.length
				? 'Browse governed roots available to your current permissions.'
				: 'No governed file roots are available for your current permissions yet.'
			items.value = response.roots.map((root) => ({ ...root, item_type: 'folder' as const }))
			breadcrumbs.value = []
			folderSummary.value = null
			setStatus('')
		} catch (error) {
			const message =
				error instanceof Error ? error.message : 'Unable to load Drive workspace home.'
			items.value = []
			modeLabel.value = 'Workspace home'
			heading.value = 'Drive workspace unavailable'
			subheading.value = 'The workspace home could not be loaded for this account.'
			breadcrumbs.value = []
			folderSummary.value = null
			setStatus(message, 'error')
		}
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
			<section class="drive-hero-grid">
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

				<aside class="drive-panel drive-context-card">
					<p class="drive-context-card__eyebrow">Current scope</p>
					<h2 class="drive-context-card__title">{{ scopeTitle }}</h2>
					<p class="drive-context-card__body">{{ scopeDetail }}</p>
					<div class="drive-context-card__badges">
						<span v-for="badge in scopeBadges" :key="badge" class="drive-badge drive-badge--soft">
							{{ badge }}
						</span>
					</div>
					<div class="drive-context-card__examples" v-if="!hasTarget">
						<p class="drive-context-card__hint">Examples</p>
						<code class="drive-code-pill">Open Drive from an Applicant, Task, Student, or Organization view</code>
					</div>
				</aside>
			</section>

			<section class="drive-summary-grid">
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Folders</p>
					<p class="drive-kpi__value">{{ folderCount }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Files</p>
					<p class="drive-kpi__value">{{ fileCount }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Items</p>
					<p class="drive-kpi__value">{{ itemCountLabel }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Mode</p>
					<p class="drive-kpi__value">{{ modeLabel }}</p>
				</article>
			</section>

			<section class="drive-body-grid">
				<aside class="drive-panel drive-rail">
					<div class="drive-rail__section">
						<p class="drive-overline">Browse</p>
						<template v-for="link in railLinks" :key="link.label">
							<a
								v-if="link.href"
								:href="link.href"
								:class="[
									'drive-rail__item',
									link.isActive ? 'drive-rail__item--active' : '',
									link.isMuted ? 'drive-rail__item--muted' : ''
								]"
							>
								<strong>{{ link.label }}</strong>
								<span>{{ link.caption }}</span>
							</a>
							<div
								v-else
								:class="[
									'drive-rail__item',
									link.isActive ? 'drive-rail__item--active' : '',
									link.isMuted ? 'drive-rail__item--muted' : ''
								]"
							>
								<strong>{{ link.label }}</strong>
								<span>{{ link.caption }}</span>
							</div>
						</template>
					</div>

					<div class="drive-rail__section">
						<p class="drive-overline">Rules</p>
						<p class="drive-rail__note">
							Files should usually be found from educational context first and workspace views second.
						</p>
					</div>
				</aside>

				<section class="drive-panel drive-content-panel">
					<header class="drive-section-header">
						<div>
							<p class="drive-overline">Workspace contents</p>
							<h2 class="drive-section-title">{{ hasTarget ? scopeTitle : 'Ready for a governed view' }}</h2>
						</div>
						<p class="drive-section-copy">
							{{
								hasTarget
									? itemCountLabel
									: hasVisibleRoots
										? 'Available governed roots for your account.'
										: 'No governed roots discovered for this account yet.'
							}}
						</p>
					</header>

					<section class="drive-list">
						<article v-if="!hasTarget && !items.length" class="drive-empty">
							<h2 class="drive-card__title">No governed roots available</h2>
							<p class="drive-card__path">
								This account does not currently have any accessible Drive roots. That usually means
								no Drive-enabled workflow has created files for this permission scope yet.
							</p>
						</article>

						<article v-else-if="!items.length && !statusMessage" class="drive-empty">
							<h2 class="drive-card__title">No items returned</h2>
							<p class="drive-card__path">This Drive surface is empty for the current context.</p>
						</article>

						<div v-else class="drive-row-list">
							<article
								v-for="item in orderedItems"
								:key="item.item_type + ':' + item.id"
								class="drive-row"
							>
								<div class="drive-row__glyph">
									{{ item.item_type === 'folder' ? 'FD' : 'FI' }}
								</div>
								<div class="drive-row__body">
									<div class="drive-row__headline">
										<h3 class="drive-row__title">
											{{ item.item_type === 'folder' ? item.title : titleForFile(item) }}
										</h3>
										<span class="drive-badge">
											{{ item.item_type === 'folder' ? badgeForFolder(item) : badgeForFile(item) }}
										</span>
									</div>
									<p class="drive-row__meta">
										{{
											item.item_type === 'folder'
												? 'Folder'
												: [item.binding_role, item.slot].filter(Boolean).join(' · ') || 'File'
										}}
									</p>
									<p v-if="item.context_path" class="drive-row__meta">{{ item.context_path }}</p>
									<p
										v-if="
											item.item_type === 'file' &&
											item.attached_to?.doctype &&
											item.attached_to?.name
										"
										class="drive-row__meta"
									>
										Attached to {{ item.attached_to.doctype }} · {{ item.attached_to.name }}
									</p>
								</div>
								<div class="drive-row__actions">
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
									</template>
									<a
										v-if="item.item_type === 'file' && item.folder?.id"
										class="drive-button drive-button--quiet"
										:href="folderLink(item.folder.id)"
									>
										Open folder
									</a>
								</div>
							</article>
						</div>
					</section>
				</section>
			</section>
		</main>
	</div>
</template>
