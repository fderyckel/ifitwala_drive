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
const homeSections = ref<WorkspaceHomeSection[]>([])
const suggestedTarget = ref<WorkspaceHomeTarget | null>(null)

const query = parseWorkspaceQuery(window.location.search)

const hasTarget = computed(() => Boolean(query.folder || (query.doctype && query.name)))
const homeItemCount = computed(() =>
	homeSections.value.reduce((total, section) => total + section.items.length, 0)
)
const folderCount = computed(() =>
	hasTarget.value
		? items.value.filter((item) => item.item_type === 'folder').length
		: homeSections.value.reduce(
				(total, section) =>
					total + section.items.filter((item) => item.target_kind === 'folder').length,
				0
			)
)
const fileCount = computed(() =>
	hasTarget.value
		? items.value.filter((item) => item.item_type === 'file').length
		: homeSections.value.reduce(
				(total, section) =>
					total + section.items.filter((item) => item.target_kind === 'context').length,
				0
			)
)
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
	const count = hasTarget.value ? items.value.length : homeItemCount.value
	return `${count} ${count === 1 ? (hasTarget.value ? 'item' : 'view') : hasTarget.value ? 'items' : 'views'}`
})
const scopeTitle = computed(() => {
	if (folderSummary.value?.title) return folderSummary.value.title
	if (query.doctype && query.name) return `${query.doctype} · ${query.name}`
	return 'My Drive'
})
const scopeDetail = computed(() => {
	if (folderSummary.value?.context_path) return folderSummary.value.context_path
	if (folderSummary.value?.path_cache) return folderSummary.value.path_cache
	if (query.bindingRole) return `Binding role: ${query.bindingRole}`
	if (query.doctype && query.name) return 'Context-governed browse'
	if (homeSections.value.length && suggestedTarget.value?.label) {
		return `${suggestedTarget.value.label} is suggested first, and the rest of your readable Drive views are grouped below.`
	}
	if (homeSections.value.length) return 'Choose a governed view based on documents you can already read.'
	return 'No governed file views are available to your current permissions yet.'
})
const scopeBadges = computed(() => {
	if (!hasTarget.value) {
		const badges = ['Governed by record access', 'Context first']
		if (suggestedTarget.value?.badge) badges.push(suggestedTarget.value.badge)
		return badges.slice(0, 4)
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
			caption: hasTarget.value ? 'Return to your governed Drive home' : 'Your governed Drive home',
			href: '/drive_workspace',
			isActive: !hasTarget.value,
			isMuted: false
		}
	]

	if (!hasTarget.value) {
		homeSections.value.slice(0, 3).forEach((section) => {
			const firstItem = section.items[0]
			if (!firstItem?.href) return
			links.push({
				label: section.label,
				caption: firstItem.label,
				href: firstItem.href,
				isActive: false,
				isMuted: false
			})
		})
	}

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
			const response = await listWorkspaceHome()
			if (response.suggested_target?.auto_open && response.suggested_target.href) {
				window.location.replace(response.suggested_target.href)
				return
			}
			modeLabel.value = 'Workspace home'
			heading.value = 'Your Drive workspace'
			subheading.value = response.suggested_target?.label
				? `Suggested next view: ${response.suggested_target.label}.`
				: response.sections.length
					? 'Open a governed view you are already allowed to read.'
					: 'No governed file views are available for your current permissions yet.'
			homeSections.value = response.sections
			suggestedTarget.value = response.suggested_target || null
			items.value = []
			breadcrumbs.value = []
			folderSummary.value = null
			setStatus('')
		} catch (error) {
			const message =
				error instanceof Error ? error.message : 'Unable to load Drive workspace home.'
			items.value = []
			homeSections.value = []
			suggestedTarget.value = null
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
		homeSections.value = []
		suggestedTarget.value = null
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
		modeLabel.value = 'Context browse'
		heading.value = `${doctype} · ${name}`
		subheading.value = query.bindingRole
			? `Context browse for binding role ${query.bindingRole}`
			: 'Context folders and files'
		const normalizedItems: FolderItem[] = response.items?.length
			? response.items
			: response.files.map((file) => ({
					...file,
					item_type: 'file'
				}))
		const firstFolder = normalizedItems.find((item) => item.item_type === 'folder') as FolderSummary | undefined
		const firstFileWithFolder = normalizedItems.find(
			(item) => item.item_type === 'file' && item.folder
		) as FileSummary | undefined
		breadcrumbs.value = firstFolder?.breadcrumbs || firstFileWithFolder?.folder?.breadcrumbs || []
		folderSummary.value = firstFolder || firstFileWithFolder?.folder || null
		items.value = normalizedItems
		setStatus('')
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unable to load Drive workspace.'
		items.value = []
		homeSections.value = []
		suggestedTarget.value = null
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
					<div class="drive-context-card__examples" v-if="!hasTarget && homeSections.length">
						<p class="drive-context-card__hint">Sections</p>
						<code v-for="section in homeSections" :key="section.key" class="drive-code-pill">
							{{ section.label }}
						</code>
					</div>
				</aside>
			</section>

			<section class="drive-summary-grid">
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">Folders</p>
					<p class="drive-kpi__value">{{ folderCount }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">{{ hasTarget ? 'Files' : 'Contexts' }}</p>
					<p class="drive-kpi__value">{{ fileCount }}</p>
				</article>
				<article class="drive-panel drive-kpi">
					<p class="drive-kpi__label">{{ hasTarget ? 'Items' : 'Views' }}</p>
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
							<h2 class="drive-section-title">{{ hasTarget ? scopeTitle : 'Ready for your governed view' }}</h2>
						</div>
						<p class="drive-section-copy">
							{{
								hasTarget
									? itemCountLabel
									: homeSections.length
										? 'Readable Drive views for your account.'
										: 'No governed views discovered for this account yet.'
							}}
						</p>
					</header>

					<section class="drive-list">
						<article v-if="!hasTarget && !homeSections.length" class="drive-empty">
							<h2 class="drive-card__title">No governed views available</h2>
							<p class="drive-card__path">
								This account does not currently have any readable Drive context or folder to open.
							</p>
						</article>

						<div v-else-if="!hasTarget" class="drive-home-sections">
							<section
								v-for="section in homeSections"
								:key="section.key"
								class="drive-home-section"
							>
								<header class="drive-home-section__head">
									<div>
										<p class="drive-overline">{{ section.label }}</p>
										<h3 class="drive-home-section__title">{{ section.label }}</h3>
										<p v-if="section.description" class="drive-home-section__copy">
											{{ section.description }}
										</p>
									</div>
									<span class="drive-badge">{{ section.items.length }}</span>
								</header>

								<div class="drive-home-targets">
									<article
										v-for="target in section.items"
										:key="target.id"
										class="drive-home-target"
									>
										<div class="drive-home-target__body">
											<p class="drive-row__meta">
												{{ target.target_kind === 'folder' ? 'Folder' : 'Context' }}
											</p>
											<h3 class="drive-row__title">{{ target.label }}</h3>
											<p v-if="target.caption" class="drive-row__meta">{{ target.caption }}</p>
										</div>
										<div class="drive-home-target__actions">
											<span class="drive-badge">{{ target.badge || 'Drive' }}</span>
											<a class="drive-button" :href="target.href">
												{{ target.target_kind === 'folder' ? 'Open folder' : 'Open files' }}
											</a>
										</div>
									</article>
								</div>
							</section>
						</div>

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
