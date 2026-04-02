<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
	browseContext,
	browseFolder,
	issueDownloadGrant,
	issuePreviewGrant,
	listWorkspaceHome,
	parseWorkspaceQuery,
} from "@/features/workspace/api";
import { performGovernedUpload } from "@/features/workspace/uploads";
import type {
	FileSummary,
	FolderBreadcrumb,
	FolderItem,
	FolderSummary,
	UploadAction,
	WorkspaceHomeSection,
	WorkspaceHomeTarget,
} from "@/features/workspace/types";

type StatusTone = "neutral" | "loading" | "error";
type SidebarNodeKind = "home" | "folder" | "context";

type SidebarNode = {
	id: string;
	label: string;
	caption?: string | null;
	href: string;
	kind: SidebarNodeKind;
	isActive: boolean;
};

type SidebarSection = {
	key: string;
	label: string;
	items: SidebarNode[];
};

const modeLabel = ref("Workspace");
const heading = ref("Governed Files");
const subheading = ref("Browse governed files with record-based access.");
const statusMessage = ref("");
const statusTone = ref<StatusTone>("neutral");
const breadcrumbs = ref<FolderBreadcrumb[]>([]);
const folderSummary = ref<FolderSummary | null>(null);
const items = ref<FolderItem[]>([]);
const homeSections = ref<WorkspaceHomeSection[]>([]);
const suggestedTarget = ref<WorkspaceHomeTarget | null>(null);
const locationUploadActions = ref<UploadAction[]>([]);

const uploadDialogOpen = ref(false);
const uploadBusy = ref(false);
const uploadError = ref("");
const uploadFile = ref<File | null>(null);
const uploadFieldValues = ref<Record<string, string>>({});
const selectedUploadActionId = ref("");
const fileInputKey = ref(0);

const query = parseWorkspaceQuery(window.location.search);

const hasTarget = computed(() => Boolean(query.folder || (query.doctype && query.name)));
const isHomeView = computed(() => !hasTarget.value);
const currentLocationHref = computed(() => `${window.location.pathname}${window.location.search}`);
const homeLocationCount = computed(() =>
	homeSections.value.reduce((count, section) => count + section.items.length, 0)
);
const orderedItems = computed(() =>
	[...items.value].sort((left, right) => {
		if (left.item_type === right.item_type) return 0;
		return left.item_type === "folder" ? -1 : 1;
	})
);
const scopeTitle = computed(() => {
	if (folderSummary.value?.title) return folderSummary.value.title;
	if (query.doctype && query.name) return `${query.doctype} · ${query.name}`;
	return "Workspace";
});
const scopeDetail = computed(() => {
	if (folderSummary.value?.context_path) return folderSummary.value.context_path;
	if (folderSummary.value?.path_cache) return folderSummary.value.path_cache;
	if (query.bindingRole) return `Filtered to ${query.bindingRole}`;
	if (query.doctype && query.name) return "Open the folders or files governed by this record.";
	if (homeLocationCount.value) return "Open a governed location to browse or upload files.";
	return "No governed files are available to this account yet.";
});
const locationBadges = computed(() => {
	const badges: string[] = [];
	if (isHomeView.value) {
		badges.push("Record governed", "Read only");
		return badges;
	}
	if (query.folder) badges.push("Folder");
	if (query.doctype && query.name) badges.push("Context");
	if (folderSummary.value?.folder_kind) badges.push(folderSummary.value.folder_kind);
	if (folderSummary.value?.is_private) badges.push("Private");
	else if (folderSummary.value?.is_private === 0) badges.push("Shared");
	if (locationUploadActions.value.length) badges.push("Upload enabled");
	return badges;
});
const selectedUploadAction = computed<UploadAction | null>(() => {
	if (!locationUploadActions.value.length) return null;
	return (
		locationUploadActions.value.find((action) => action.id === selectedUploadActionId.value) ||
		locationUploadActions.value[0]
	);
});
const sidebarSections = computed<SidebarSection[]>(() => {
	const sections: SidebarSection[] = [
		{
			key: "workspace",
			label: "Workspace",
			items: [
				{
					id: "workspace-home",
					label: "Home",
					caption: "All readable governed locations",
					href: "/drive_workspace",
					kind: "home",
					isActive: isHomeView.value,
				},
			],
		},
	];

	for (const section of homeSections.value) {
		if (!section.items.length) continue;
		sections.push({
			key: section.key,
			label: section.label,
			items: section.items.map((target) => ({
				id: target.id,
				label: target.label,
				caption: target.caption || target.badge || section.description || "",
				href: target.href,
				kind: target.target_kind === "folder" ? "folder" : "context",
				isActive: currentLocationHref.value === target.href,
			})),
		});
	}

	return sections;
});

watch(
	locationUploadActions,
	(actions) => {
		if (!actions.length) {
			selectedUploadActionId.value = "";
			return;
		}

		if (!actions.some((action) => action.id === selectedUploadActionId.value)) {
			selectedUploadActionId.value = actions[0].id;
		}
	},
	{ immediate: true }
);

watch(
	selectedUploadAction,
	(action) => {
		const nextValues: Record<string, string> = {};
		for (const field of action?.fields || []) {
			nextValues[field.name] = uploadFieldValues.value[field.name] || "";
		}
		uploadFieldValues.value = nextValues;
	},
	{ immediate: true }
);

function setStatus(message = "", tone: StatusTone = "neutral") {
	statusMessage.value = message;
	statusTone.value = tone;
}

function folderLink(folderId: string): string {
	return `/drive_workspace?folder=${encodeURIComponent(folderId)}`;
}

function titleForFile(file: FileSummary): string {
	return file.title || file.id || "Untitled file";
}

function itemKindLabel(item: FolderItem): string {
	if (item.item_type === "folder") return "Folder";
	return item.binding_role || item.slot || "File";
}

function itemLocationLabel(item: FolderItem): string {
	if (item.item_type === "folder") return item.context_path || item.path_cache || "Folder";
	return item.context_path || item.folder_path || "Governed file";
}

function rowHref(item: FolderItem): string | undefined {
	if (item.item_type === "folder") return folderLink(item.id);
	return undefined;
}

function titleForItem(item: FolderItem): string {
	if (item.item_type === "folder") return item.title;
	return titleForFile(item);
}

function descriptionForItem(item: FolderItem): string {
	if (item.item_type === "folder") return item.context_path || item.path_cache || "Folder";
	if (item.attached_to?.doctype && item.attached_to?.name) {
		return `Attached to ${item.attached_to.doctype} · ${item.attached_to.name}`;
	}
	return item.folder_path || item.context_path || "Governed file";
}

function iconClass(kind: SidebarNodeKind | "file"): string {
	return `drive-entry-icon--${kind}`;
}

function targetBadgeLabel(target: WorkspaceHomeTarget): string {
	return target.badge || (target.target_kind === "folder" ? "Folder" : "Context");
}

async function openGrant(kind: "preview" | "download", file: FileSummary) {
	try {
		setStatus("");
		const grant =
			kind === "preview"
				? await issuePreviewGrant(file.drive_file_id || file.id, file.canonical_ref)
				: await issueDownloadGrant(file.drive_file_id || file.id, file.canonical_ref);
		window.open(grant.url, "_blank", "noopener");
	} catch (error) {
		const message =
			error instanceof Error
				? error.message
				: `Unable to open the ${kind} link for this file.`;
		setStatus(message, "error");
	}
}

async function loadHomeNavigation(showStatus = false): Promise<boolean> {
	try {
		if (showStatus) setStatus("Loading workspace...", "loading");
		const response = await listWorkspaceHome();
		homeSections.value = response.sections;
		suggestedTarget.value = response.suggested_target || null;
		if (
			isHomeView.value &&
			response.suggested_target?.auto_open &&
			response.suggested_target.href
		) {
			window.location.replace(response.suggested_target.href);
			return true;
		}
		if (showStatus) setStatus("");
		return false;
	} catch (error) {
		const message =
			error instanceof Error ? error.message : "Unable to load workspace navigation.";
		if (showStatus) setStatus(message, "error");
		if (!homeSections.value.length) homeSections.value = [];
		suggestedTarget.value = null;
		return false;
	}
}

async function loadWorkspace() {
	if (!homeSections.value.length) {
		const redirected = await loadHomeNavigation(false);
		if (redirected) return;
	}

	if (!hasTarget.value) {
		const redirected = await loadHomeNavigation(true);
		if (redirected) return;

		modeLabel.value = "Workspace";
		heading.value = "Governed Files";
		subheading.value =
			"Open the governed folders and record-owned collections you can already access.";
		items.value = [];
		breadcrumbs.value = [];
		folderSummary.value = null;
		locationUploadActions.value = [];
		return;
	}

	try {
		setStatus("Loading location...", "loading");
		if (query.folder) {
			const response = await browseFolder(query.folder);
			modeLabel.value = "Folder";
			heading.value = response.folder.title;
			subheading.value =
				response.folder.context_path ||
				response.folder.path_cache ||
				"Governed folder browser";
			breadcrumbs.value = response.folder.breadcrumbs || [];
			folderSummary.value = response.folder;
			items.value = response.items;
			locationUploadActions.value = response.upload_actions || [];
			setStatus("");
			return;
		}

		const doctype = query.doctype as string;
		const name = query.name as string;
		const response = await browseContext(doctype, name, query.bindingRole);
		modeLabel.value = "Context";
		heading.value = `${doctype} · ${name}`;
		subheading.value = query.bindingRole
			? `Governed files filtered to ${query.bindingRole}`
			: "Governed files anchored to this record.";
		const normalizedItems: FolderItem[] = response.items?.length
			? response.items
			: response.files.map((file) => ({
					...file,
					item_type: "file",
			  }));
		const firstFolder = normalizedItems.find((item) => item.item_type === "folder") as
			| FolderSummary
			| undefined;
		const firstFileWithFolder = normalizedItems.find(
			(item) => item.item_type === "file" && item.folder
		) as FileSummary | undefined;
		breadcrumbs.value =
			firstFolder?.breadcrumbs || firstFileWithFolder?.folder?.breadcrumbs || [];
		folderSummary.value = firstFolder || firstFileWithFolder?.folder || null;
		items.value = normalizedItems;
		locationUploadActions.value = response.upload_actions || [];
		setStatus("");
	} catch (error) {
		const message = error instanceof Error ? error.message : "Unable to load this location.";
		items.value = [];
		breadcrumbs.value = [];
		folderSummary.value = null;
		locationUploadActions.value = [];
		setStatus(message, "error");
	}
}

function openUploadDialog() {
	if (!locationUploadActions.value.length) return;
	uploadDialogOpen.value = true;
	uploadBusy.value = false;
	uploadError.value = "";
	uploadFile.value = null;
	fileInputKey.value += 1;
}

function closeUploadDialog() {
	uploadDialogOpen.value = false;
	uploadBusy.value = false;
	uploadError.value = "";
	uploadFile.value = null;
	fileInputKey.value += 1;
}

function handleFileSelection(event: Event) {
	const input = event.target as HTMLInputElement;
	uploadFile.value = input.files?.[0] || null;
	uploadError.value = "";
}

async function submitUpload() {
	const action = selectedUploadAction.value;
	const file = uploadFile.value;
	if (!action) {
		uploadError.value = "No governed upload destination is available for this location.";
		return;
	}
	if (!file) {
		uploadError.value = "Choose a file to upload.";
		return;
	}

	for (const field of action.fields || []) {
		if (field.required && !(uploadFieldValues.value[field.name] || "").trim()) {
			uploadError.value = `${field.label} is required.`;
			return;
		}
	}

	uploadBusy.value = true;
	uploadError.value = "";
	setStatus(`Uploading ${file.name}...`, "loading");

	try {
		await performGovernedUpload(action, file, uploadFieldValues.value);
		closeUploadDialog();
		await loadHomeNavigation(false);
		await loadWorkspace();
		setStatus(`${file.name} uploaded to governed storage.`, "neutral");
	} catch (error) {
		const message = error instanceof Error ? error.message : "Unable to upload file.";
		uploadError.value = message;
		setStatus(message, "error");
	} finally {
		uploadBusy.value = false;
	}
}

onMounted(() => {
	void loadWorkspace();
});
</script>

<template>
	<div class="drive-app">
		<main class="drive-shell drive-shell--browser">
			<aside class="drive-panel drive-sidebar">
				<div class="drive-sidebar__brand">
					<p class="drive-overline">Ifitwala Drive</p>
					<h1 class="drive-sidebar__title">Governed Files</h1>
					<p class="drive-sidebar__copy">
						Conventional file browsing with governed Ifitwala_Ed storage underneath.
					</p>
				</div>

				<div class="drive-nav">
					<section
						v-for="section in sidebarSections"
						:key="section.key"
						class="drive-nav__section"
					>
						<p class="drive-nav__label">{{ section.label }}</p>
						<div class="drive-nav__items">
							<a
								v-for="node in section.items"
								:key="node.id"
								:href="node.href"
								:class="[
									'drive-nav__item',
									node.isActive ? 'drive-nav__item--active' : '',
								]"
							>
								<span
									class="drive-entry-icon"
									:class="iconClass(node.kind)"
									aria-hidden="true"
								></span>
								<span class="drive-nav__text">
									<strong>{{ node.label }}</strong>
									<span>{{ node.caption }}</span>
								</span>
							</a>
						</div>
					</section>
				</div>

				<div class="drive-sidebar__rules">
					<p class="drive-overline">Access</p>
					<p class="drive-sidebar__copy">
						Drive browsing follows Ifitwala_Ed record permissions. Uploads appear only
						where a governed wrapper already exists.
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
						<div class="drive-toolbar__actions">
							<button
								v-if="locationUploadActions.length"
								type="button"
								class="drive-button"
								@click="openUploadDialog"
							>
								Upload Governed File
							</button>
							<button
								type="button"
								class="drive-button drive-button--quiet"
								@click="loadWorkspace"
							>
								Refresh
							</button>
						</div>
					</div>
				</header>

				<nav
					v-if="breadcrumbs.length"
					class="drive-panel drive-breadcrumbs"
					aria-label="Drive breadcrumbs"
				>
					<a
						v-for="crumb in breadcrumbs"
						:key="crumb.id"
						class="drive-crumb"
						:href="folderLink(crumb.id)"
					>
						{{ crumb.title || crumb.id }}
					</a>
				</nav>

				<div v-if="statusMessage" class="drive-panel drive-status" :data-tone="statusTone">
					<span>{{ statusMessage }}</span>
				</div>

				<section v-if="isHomeView" class="drive-panel drive-home-shell">
					<header class="drive-home-shell__head">
						<div>
							<p class="drive-overline">Drive Locations</p>
							<h3 class="drive-table-shell__title">Open A Governed Space</h3>
						</div>
						<p class="drive-table-shell__copy">{{ homeLocationCount }} locations</p>
					</header>

					<article v-if="!homeSections.length" class="drive-empty">
						<h3 class="drive-empty__title">No governed files available</h3>
						<p class="drive-empty__copy">
							This account does not currently have a readable governed folder or
							context.
						</p>
					</article>

					<div v-else class="drive-home-groups">
						<section
							v-for="section in homeSections"
							:key="section.key"
							class="drive-home-group"
						>
							<header class="drive-home-group__head">
								<div>
									<p class="drive-nav__label">{{ section.label }}</p>
									<p class="drive-home-group__copy">
										{{
											section.description ||
											"Governed locations available from this view."
										}}
									</p>
								</div>
								<span class="drive-badge">{{ section.items.length }}</span>
							</header>

							<div class="drive-browser-list">
								<article
									v-for="target in section.items"
									:key="target.id"
									class="drive-browser-row drive-browser-row--home"
								>
									<div class="drive-browser-row__main">
										<span
											class="drive-entry-icon"
											:class="
												iconClass(
													target.target_kind === 'folder'
														? 'folder'
														: 'context'
												)
											"
											aria-hidden="true"
										></span>
										<div class="drive-browser-row__text">
											<a
												class="drive-browser-row__title"
												:href="target.href"
												>{{ target.label }}</a
											>
											<p class="drive-browser-row__description">
												{{
													target.caption ||
													section.description ||
													"Governed location"
												}}
											</p>
										</div>
									</div>

									<div class="drive-browser-row__actions">
										<span class="drive-badge">{{
											targetBadgeLabel(target)
										}}</span>
										<a
											class="drive-button drive-button--quiet"
											:href="target.href"
											>Open</a
										>
									</div>
								</article>
							</div>
						</section>
					</div>
				</section>

				<section v-else class="drive-panel drive-table-shell">
					<header class="drive-table-shell__head">
						<div>
							<p class="drive-overline">Contents</p>
							<h3 class="drive-table-shell__title">{{ scopeTitle }}</h3>
						</div>
						<p class="drive-table-shell__copy">{{ orderedItems.length }} items</p>
					</header>

					<article v-if="!orderedItems.length" class="drive-empty">
						<h3 class="drive-empty__title">No items in this location</h3>
						<p class="drive-empty__copy">This governed location is currently empty.</p>
					</article>

					<div v-else class="drive-browser-list">
						<article
							v-for="item in orderedItems"
							:key="item.item_type + ':' + item.id"
							class="drive-browser-row"
						>
							<div class="drive-browser-row__main">
								<span
									class="drive-entry-icon"
									:class="
										iconClass(item.item_type === 'folder' ? 'folder' : 'file')
									"
									aria-hidden="true"
								></span>
								<div class="drive-browser-row__text">
									<a
										v-if="rowHref(item)"
										class="drive-browser-row__title"
										:href="rowHref(item)"
									>
										{{ titleForItem(item) }}
									</a>
									<span v-else class="drive-browser-row__title">
										{{ titleForItem(item) }}
									</span>
									<p class="drive-browser-row__description">
										{{ descriptionForItem(item) }}
									</p>
								</div>
							</div>

							<div class="drive-browser-row__details">
								<span class="drive-browser-row__location">{{
									itemLocationLabel(item)
								}}</span>
								<span class="drive-badge">{{ itemKindLabel(item) }}</span>
							</div>

							<div class="drive-browser-row__actions">
								<a
									v-if="item.item_type === 'folder'"
									class="drive-button drive-button--quiet"
									:href="folderLink(item.id)"
								>
									Open
								</a>
								<template v-else>
									<button
										type="button"
										class="drive-button drive-button--quiet"
										:disabled="!item.can_preview"
										@click="openGrant('preview', item)"
									>
										Preview
									</button>
									<button
										type="button"
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
										Open Folder
									</a>
								</template>
							</div>
						</article>
					</div>
				</section>
			</section>
		</main>

		<div
			v-if="uploadDialogOpen"
			class="drive-modal-backdrop"
			@click.self="!uploadBusy && closeUploadDialog()"
		>
			<section class="drive-panel drive-modal">
				<header class="drive-modal__head">
					<div>
						<p class="drive-overline">Governed Upload</p>
						<h3 class="drive-modal__title">Upload To This Location</h3>
					</div>
					<button
						type="button"
						class="drive-button drive-button--quiet"
						:disabled="uploadBusy"
						@click="closeUploadDialog"
					>
						Close
					</button>
				</header>

				<div class="drive-modal__body">
					<label class="drive-form-field">
						<span class="drive-form-field__label">Destination</span>
						<select
							v-model="selectedUploadActionId"
							class="drive-input"
							:disabled="uploadBusy"
						>
							<option
								v-for="action in locationUploadActions"
								:key="action.id"
								:value="action.id"
							>
								{{ action.label }}
							</option>
						</select>
					</label>

					<p v-if="selectedUploadAction" class="drive-modal__description">
						{{ selectedUploadAction.description }}
					</p>
					<p v-if="selectedUploadAction" class="drive-modal__destination">
						Stored in {{ selectedUploadAction.destination_label }}
					</p>

					<label
						v-for="field in selectedUploadAction?.fields || []"
						:key="field.name"
						class="drive-form-field"
					>
						<span class="drive-form-field__label">{{ field.label }}</span>
						<input
							v-model="uploadFieldValues[field.name]"
							class="drive-input"
							type="text"
							:placeholder="field.placeholder || ''"
							:required="field.required"
							:disabled="uploadBusy"
						/>
						<span v-if="field.help" class="drive-form-field__help">{{
							field.help
						}}</span>
					</label>

					<label class="drive-file-picker">
						<input
							:key="fileInputKey"
							class="drive-file-picker__input"
							type="file"
							:disabled="uploadBusy"
							@change="handleFileSelection"
						/>
						<span class="drive-file-picker__label">
							{{ uploadFile ? uploadFile.name : "Choose a file to upload" }}
						</span>
						<span class="drive-file-picker__help">
							The file will be routed through the governed Drive wrapper for this
							location.
						</span>
					</label>

					<p v-if="uploadError" class="drive-modal__error">{{ uploadError }}</p>
				</div>

				<footer class="drive-modal__footer">
					<button
						type="button"
						class="drive-button drive-button--quiet"
						:disabled="uploadBusy"
						@click="closeUploadDialog"
					>
						Cancel
					</button>
					<button
						type="button"
						class="drive-button"
						:disabled="uploadBusy"
						@click="submitUpload"
					>
						{{ uploadBusy ? "Uploading..." : "Start Upload" }}
					</button>
				</footer>
			</section>
		</div>
	</div>
</template>
