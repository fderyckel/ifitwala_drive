(function () {
	'use strict';

	function $(selector) {
		return document.querySelector(selector);
	}

	function getQueryParam(key) {
		const value = new URLSearchParams(window.location.search).get(key);
		return (value || '').trim();
	}

	async function resolveCsrfToken() {
		if (window.csrf_token) return window.csrf_token;
		const meta = document.querySelector('meta[name="csrf-token"]');
		if (meta && meta.content) return meta.content;
		return '';
	}

	async function callApi(method, payload) {
		const csrf = await resolveCsrfToken();
		const response = await fetch('/api/method/' + method, {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				'Content-Type': 'application/json',
				...(csrf ? { 'X-Frappe-CSRF-Token': csrf } : {}),
			},
			body: JSON.stringify(payload || {}),
		});
		const data = await response.json().catch(function () {
			return {};
		});
		if (!response.ok || data.exception || data.exc) {
			throw new Error(data.message || response.statusText || 'Request failed');
		}
		return data.message || data;
	}

	function escapeHtml(value) {
		return String(value == null ? '' : value)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#039;');
	}

	function setStatus(message, tone) {
		const node = $('#drive-workspace-status');
		if (!node) return;
		node.textContent = message || '';
		node.dataset.tone = tone || 'neutral';
		node.hidden = !message;
	}

	function setHeadings(primary, secondary, modeLabel) {
		$('#drive-workspace-mode').textContent = modeLabel || 'Drive workspace';
		$('#drive-workspace-heading').textContent = primary || 'Drive workspace';
		$('#drive-workspace-subheading').textContent = secondary || '';
	}

	function renderIdle() {
		setHeadings(
			'Open a Drive context or folder',
			'Use query parameters like ?folder=<id> or ?doctype=<DocType>&name=<record>.',
			'Drive workspace'
		);
		$('#drive-workspace-breadcrumbs').innerHTML = '';
		$('#drive-workspace-list').innerHTML =
			'<article class="drive-card drive-card--empty"><h3>No target selected</h3><p>This page is designed to be deep-linked from contextual Ifitwala_Ed surfaces while remaining owned by Ifitwala_drive.</p></article>';
	}

	function folderLink(folderId) {
		return '/drive_workspace?folder=' + encodeURIComponent(folderId);
	}

	function renderBreadcrumbs(breadcrumbs) {
		const node = $('#drive-workspace-breadcrumbs');
		if (!node) return;
		node.innerHTML = '';
		(breadcrumbs || []).forEach(function (crumb) {
			const link = document.createElement('a');
			link.className = 'drive-crumb';
			link.href = folderLink(crumb.id);
			link.textContent = crumb.title || crumb.id;
			node.appendChild(link);
		});
	}

	function fileBadgeLabel(file) {
		return file.preview_status || file.binding_role || 'File';
	}

	function folderBadgeLabel(folder) {
		return folder.folder_kind || 'Folder';
	}

	function renderFolderRow(item) {
		return (
			'<article class="drive-card">' +
			'<div class="drive-card__head">' +
			'<div>' +
			'<p class="drive-card__meta">Folder</p>' +
			'<h3>' + escapeHtml(item.title) + '</h3>' +
			(item.context_path ? '<p class="drive-card__path">' + escapeHtml(item.context_path) + '</p>' : '') +
			'</div>' +
			'<span class="drive-badge">' + escapeHtml(folderBadgeLabel(item)) + '</span>' +
			'</div>' +
			'<div class="drive-card__actions">' +
			'<a class="drive-button" href="' + folderLink(item.id) + '">Open folder</a>' +
			'</div>' +
			'</article>'
		);
	}

	function renderFileRow(item) {
		const previewDisabled = item.can_preview ? '' : ' disabled';
		const downloadDisabled = item.can_download ? '' : ' disabled';
		return (
			'<article class="drive-card">' +
			'<div class="drive-card__head">' +
			'<div>' +
			'<p class="drive-card__meta">' +
			escapeHtml([item.binding_role, item.slot].filter(Boolean).join(' · ') || 'File') +
			'</p>' +
			'<h3>' + escapeHtml(item.title || item.id) + '</h3>' +
			(item.context_path ? '<p class="drive-card__path">' + escapeHtml(item.context_path) + '</p>' : '') +
			(item.attached_to && item.attached_to.doctype && item.attached_to.name
				? '<p class="drive-card__path">Attached to ' +
				  escapeHtml(item.attached_to.doctype) +
				  ' · ' +
				  escapeHtml(item.attached_to.name) +
				  '</p>'
				: '') +
			'</div>' +
			'<span class="drive-badge">' + escapeHtml(fileBadgeLabel(item)) + '</span>' +
			'</div>' +
			'<div class="drive-card__actions">' +
			'<button class="drive-button js-preview"' + previewDisabled + ' data-drive-file-id="' + escapeHtml(item.id) + '" data-canonical-ref="' + escapeHtml(item.canonical_ref || '') + '">Preview</button>' +
			'<button class="drive-button js-download"' + downloadDisabled + ' data-drive-file-id="' + escapeHtml(item.id) + '" data-canonical-ref="' + escapeHtml(item.canonical_ref || '') + '">Download</button>' +
			(item.folder && item.folder.id
				? '<a class="drive-button drive-button--quiet" href="' + folderLink(item.folder.id) + '">Open folder</a>'
				: '') +
			'</div>' +
			'</article>'
		);
	}

	function renderRows(rows) {
		const node = $('#drive-workspace-list');
		if (!node) return;
		if (!rows || !rows.length) {
			node.innerHTML =
				'<article class="drive-card drive-card--empty"><h3>No items returned</h3><p>This Drive surface is empty for the current context.</p></article>';
			return;
		}
		node.innerHTML = rows
			.map(function (item) {
				return item.item_type === 'folder' ? renderFolderRow(item) : renderFileRow(item);
			})
			.join('');
	}

	async function issueGrant(kind, driveFileId, canonicalRef) {
		const payload = canonicalRef
			? { drive_file_id: driveFileId, canonical_ref: canonicalRef }
			: { drive_file_id: driveFileId };
		const method =
			kind === 'preview'
				? 'ifitwala_drive.api.access.issue_preview_grant'
				: 'ifitwala_drive.api.access.issue_download_grant';
		const response = await callApi(method, payload);
		window.open(response.url, '_blank', 'noopener');
	}

	function bindActions() {
		document.querySelectorAll('.js-preview').forEach(function (button) {
			button.addEventListener('click', async function () {
				if (button.disabled) return;
				try {
					setStatus('');
					await issueGrant(
						'preview',
						button.getAttribute('data-drive-file-id'),
						button.getAttribute('data-canonical-ref')
					);
				} catch (error) {
					setStatus(error.message || 'Unable to open preview.', 'error');
				}
			});
		});

		document.querySelectorAll('.js-download').forEach(function (button) {
			button.addEventListener('click', async function () {
				if (button.disabled) return;
				try {
					setStatus('');
					await issueGrant(
						'download',
						button.getAttribute('data-drive-file-id'),
						button.getAttribute('data-canonical-ref')
					);
				} catch (error) {
					setStatus(error.message || 'Unable to prepare download.', 'error');
				}
			});
		});
	}

	async function loadWorkspace() {
		const folder = getQueryParam('folder');
		const doctype = getQueryParam('doctype');
		const name = getQueryParam('name');
		const bindingRole = getQueryParam('binding_role');

		setStatus('');

		if (!folder && !(doctype && name)) {
			renderIdle();
			return;
		}

		try {
			if (folder) {
				setHeadings('Loading folder...', '', 'Folder browse');
				const response = await callApi('ifitwala_drive.api.folders.list_folder_items', {
					folder: folder,
					include_folders: 1,
					include_files: 1,
					limit: 100,
					offset: 0,
				});
				setHeadings(
					response.folder.title,
					response.folder.context_path || response.folder.path_cache || 'Folder browse mode',
					'Folder browse'
				);
				renderBreadcrumbs(response.folder.breadcrumbs || []);
				renderRows(response.items || []);
				bindActions();
				return;
			}

			setHeadings(doctype + ' · ' + name, 'Loading context files...', 'Context files');
			const response = await callApi('ifitwala_drive.api.folders.list_context_files', {
				doctype: doctype,
				name: name,
				...(bindingRole ? { binding_role: bindingRole } : {}),
			});
			setHeadings(
				doctype + ' · ' + name,
				bindingRole ? 'Context files for binding role ' + bindingRole : 'Context file view',
				'Context files'
			);
			const fileRows = (response.files || []).map(function (row) {
				return Object.assign({ item_type: 'file' }, row);
			});
			const breadcrumbs = fileRows[0] && fileRows[0].folder ? fileRows[0].folder.breadcrumbs : [];
			renderBreadcrumbs(breadcrumbs || []);
			renderRows(fileRows);
			bindActions();
		} catch (error) {
			setStatus(error.message || 'Unable to load Drive workspace.', 'error');
			$('#drive-workspace-list').innerHTML =
				'<article class="drive-card drive-card--empty"><h3>Workspace unavailable</h3><p>The Drive surface could not be loaded for this request.</p></article>';
		}
	}

	document.addEventListener('DOMContentLoaded', loadWorkspace);
})();
