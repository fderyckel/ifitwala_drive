type ApiResponse<T> = {
	message?: T
	exception?: string
	exc?: string
	_error_message?: string
}

function resolveCsrfToken(): string {
	const mount = document.getElementById('ifitwala-drive-workspace-app')
	const datasetToken = mount?.getAttribute('data-csrf-token')
	if (datasetToken) return datasetToken
	const meta = document.querySelector('meta[name="csrf-token"]')
	if (meta instanceof HTMLMetaElement && meta.content) return meta.content
	const globalToken = (window as Window & { csrf_token?: string }).csrf_token
	return globalToken || ''
}

export async function callFrappeApi<T>(method: string, payload: Record<string, unknown>): Promise<T> {
	const response = await fetch(`/api/method/${method}`, {
		method: 'POST',
		credentials: 'same-origin',
		headers: {
			'Content-Type': 'application/json',
			...(resolveCsrfToken() ? { 'X-Frappe-CSRF-Token': resolveCsrfToken() } : {})
		},
		body: JSON.stringify(payload)
	})

	const data = (await response.json().catch(() => ({}))) as ApiResponse<T>
	if (!response.ok || data.exception || data.exc) {
		throw new Error(data._error_message || data.message?.toString() || response.statusText || 'Request failed')
	}

	return (data.message ?? (data as T)) as T
}
