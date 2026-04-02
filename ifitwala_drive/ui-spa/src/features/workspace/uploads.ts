import { callFrappeApi } from '@/lib/frappeApi'

import type { UploadAction } from './types'

type UploadTarget = {
	method?: string
	url: string
	headers?: Record<string, unknown>
}

type UploadSessionResponse = {
	upload_session_id: string
	upload_strategy: string
	upload_target: UploadTarget
}

export type FinalizeUploadResponse = {
	drive_file_id?: string
	drive_file_version_id?: string
	file_id?: string
	canonical_ref?: string | null
	status: string
	preview_status?: string | null
	file_url?: string | null
}

function isSameOriginUrl(rawUrl: string): boolean {
	try {
		const url = new URL(rawUrl, window.location.origin)
		return url.origin === window.location.origin
	} catch {
		return false
	}
}

function normalizeHeaders(
	headers: Record<string, unknown> | undefined,
	options: { excludeContentType?: boolean } = {}
): Record<string, string> {
	const { excludeContentType = false } = options
	const normalized: Record<string, string> = {}
	for (const [key, value] of Object.entries(headers || {})) {
		if (value == null) continue
		if (excludeContentType && key.toLowerCase() === 'content-type') continue
		if (key.toLowerCase() === 'content-length') continue
		normalized[key] = String(value)
	}
	return normalized
}

function buildUploadPayload(
	action: UploadAction,
	file: File,
	fieldValues: Record<string, string>
): Record<string, unknown> {
	const payload: Record<string, unknown> = {
		...action.payload,
		filename_original: file.name,
		expected_size_bytes: file.size
	}
	if (file.type) payload.mime_type_hint = file.type

	for (const field of action.fields || []) {
		const value = (fieldValues[field.name] || '').trim()
		if (!value) continue
		payload[field.name] = value
	}
	return payload
}

async function uploadProxyPost(target: UploadTarget, file: File): Promise<void> {
	const formData = new FormData()
	formData.append('file', file, file.name)

	const response = await fetch(target.url, {
		method: target.method || 'POST',
		credentials: 'same-origin',
		headers: normalizeHeaders(target.headers, { excludeContentType: true }),
		body: formData
	})

	if (!response.ok) {
		throw new Error((await response.text().catch(() => '')) || 'Upload failed')
	}
}

async function uploadPut(target: UploadTarget, file: File): Promise<void> {
	const response = await fetch(target.url, {
		method: target.method || 'PUT',
		credentials: isSameOriginUrl(target.url) ? 'same-origin' : 'omit',
		headers: normalizeHeaders(target.headers),
		body: file
	})

	if (!response.ok) {
		throw new Error((await response.text().catch(() => '')) || 'Upload failed')
	}
}

async function uploadToTarget(session: UploadSessionResponse, file: File): Promise<void> {
	const target = session.upload_target
	if (session.upload_strategy === 'proxy_post') {
		await uploadProxyPost(target, file)
		return
	}

	await uploadPut(target, file)
}

export async function performGovernedUpload(
	action: UploadAction,
	file: File,
	fieldValues: Record<string, string>
): Promise<FinalizeUploadResponse> {
	const session = await callFrappeApi<UploadSessionResponse>(
		action.api_method,
		buildUploadPayload(action, file, fieldValues)
	)
	await uploadToTarget(session, file)
	return callFrappeApi<FinalizeUploadResponse>('ifitwala_drive.api.uploads.finalize_upload_session', {
		upload_session_id: session.upload_session_id,
		received_size_bytes: file.size
	})
}
