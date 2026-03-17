import { OPENROUTER_API_BASE_URL } from '$lib/constants';

type OpenRouterConfig = {
	ENABLE_OPENROUTER_API: boolean;
	OPENROUTER_API_BASE_URL: string;
	OPENROUTER_API_KEY: string;
	OPENROUTER_API_CONFIG: Record<string, any>;
};

export const getOpenRouterConfig = async (token: string = ''): Promise<OpenRouterConfig> => {
	let error = null;

	const res = await fetch(`${OPENROUTER_API_BASE_URL}/config`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = 'Server connection failed';
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateOpenRouterConfig = async (
	token: string = '',
	config: OpenRouterConfig
): Promise<OpenRouterConfig> => {
	let error = null;

	const res = await fetch(`${OPENROUTER_API_BASE_URL}/config/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({ ...config })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = 'Server connection failed';
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getOpenRouterModels = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${OPENROUTER_API_BASE_URL}/models`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = `OpenRouter: ${err?.error?.message ?? 'Network Problem'}`;
			return [];
		});

	if (error) {
		throw error;
	}

	return res;
};

export const verifyOpenRouterConnection = async (
	token: string = '',
	url: string,
	key: string
) => {
	let error = null;

	const res = await fetch(`${OPENROUTER_API_BASE_URL}/verify`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({ url, key })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = `OpenRouter: ${err?.error?.message ?? err?.detail ?? 'Network Problem'}`;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getOpenRouterGenerationStats = async (
	token: string = '',
	generationId: string
) => {
	let error = null;

	const res = await fetch(`${OPENROUTER_API_BASE_URL}/generation/${generationId}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = 'Server connection failed';
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
