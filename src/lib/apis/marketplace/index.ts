import { WEBUI_API_BASE_URL } from '$lib/constants';

const MARKETPLACE_API = `${WEBUI_API_BASE_URL}/marketplace`;

async function apiCall(
	url: string,
	token: string,
	options: RequestInit = {}
): Promise<any> {
	const res = await fetch(url, {
		...options,
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`,
			...(options.headers || {})
		}
	});

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: res.statusText }));
		throw err.detail || 'Request failed';
	}

	return res.json();
}

// Catalog

export const searchCatalog = async (
	token: string,
	query: string = '',
	page: number = 1,
	category: string = ''
) => {
	const params = new URLSearchParams();
	if (query) params.set('q', query);
	if (page > 1) params.set('page', String(page));
	if (category) params.set('category', category);
	return apiCall(`${MARKETPLACE_API}/catalog?${params.toString()}`, token);
};

export const getCatalogSkillDetail = async (token: string, slug: string) => {
	return apiCall(`${MARKETPLACE_API}/catalog/${encodeURIComponent(slug)}/detail`, token);
};

export const getCatalogSkillPreview = async (token: string, slug: string) => {
	return apiCall(`${MARKETPLACE_API}/catalog/${encodeURIComponent(slug)}/preview`, token);
};

// Install / Uninstall

export const installSkill = async (token: string, slug: string, source: string = 'clawhub') => {
	return apiCall(`${MARKETPLACE_API}/install`, token, {
		method: 'POST',
		body: JSON.stringify({ slug, source })
	});
};

export const uninstallSkill = async (token: string, installationId: string) => {
	return apiCall(`${MARKETPLACE_API}/installations/${installationId}`, token, {
		method: 'DELETE'
	});
};

// Installations

export const getInstallations = async (token: string) => {
	return apiCall(`${MARKETPLACE_API}/installations`, token);
};

export const getInstallation = async (token: string, installationId: string) => {
	return apiCall(`${MARKETPLACE_API}/installations/${installationId}`, token);
};

// Config

export const updateInstallationConfig = async (
	token: string,
	installationId: string,
	env: Record<string, string>
) => {
	return apiCall(`${MARKETPLACE_API}/installations/${installationId}/config`, token, {
		method: 'PUT',
		body: JSON.stringify({ env })
	});
};

export const getInstallationConfigSpec = async (token: string, installationId: string) => {
	return apiCall(`${MARKETPLACE_API}/installations/${installationId}/config/spec`, token);
};

// Updates

export const checkUpdate = async (token: string, installationId: string) => {
	return apiCall(`${MARKETPLACE_API}/installations/${installationId}/check-update`, token, {
		method: 'POST'
	});
};

export const updateSkillVersion = async (token: string, installationId: string) => {
	return apiCall(`${MARKETPLACE_API}/installations/${installationId}/update`, token, {
		method: 'POST'
	});
};

// Auth

export const saveClawHubAuth = async (token: string, clawHubToken: string) => {
	return apiCall(`${MARKETPLACE_API}/auth`, token, {
		method: 'POST',
		body: JSON.stringify({ token: clawHubToken })
	});
};

export const removeClawHubAuth = async (token: string) => {
	return apiCall(`${MARKETPLACE_API}/auth`, token, { method: 'DELETE' });
};

export const getAuthStatus = async (token: string) => {
	return apiCall(`${MARKETPLACE_API}/auth/status`, token);
};
