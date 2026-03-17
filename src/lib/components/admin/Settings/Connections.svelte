<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';

	const dispatch = createEventDispatcher();

	import { getOllamaConfig, updateOllamaConfig } from '$lib/apis/ollama';
	import { getOpenAIConfig, updateOpenAIConfig, getOpenAIModels } from '$lib/apis/openai';
	import {
		getOpenRouterConfig,
		updateOpenRouterConfig,
		verifyOpenRouterConnection
	} from '$lib/apis/openrouter';
	import { getModels as _getModels, getBackendConfig } from '$lib/apis';
	import { getConnectionsConfig, setConnectionsConfig } from '$lib/apis/configs';

	import { config, models, settings, user } from '$lib/stores';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';

	import OpenAIConnection from './Connections/OpenAIConnection.svelte';
	import AddConnectionModal from '$lib/components/AddConnectionModal.svelte';
	import OllamaConnection from './Connections/OllamaConnection.svelte';

	const i18n = getContext('i18n');

	const getModels = async () => {
		const models = await _getModels(
			localStorage.token,
			$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null),
			false,
			true
		);
		return models;
	};

	// External
	let OLLAMA_BASE_URLS = [''];
	let OLLAMA_API_CONFIGS = {};

	let OPENAI_API_KEYS = [''];
	let OPENAI_API_BASE_URLS = [''];
	let OPENAI_API_CONFIGS = {};

	let ENABLE_OPENAI_API: null | boolean = null;
	let ENABLE_OLLAMA_API: null | boolean = null;
	let ENABLE_OPENROUTER_API: null | boolean = null;

	let OPENROUTER_API_BASE_URL = 'https://openrouter.ai/api/v1';
	let OPENROUTER_API_KEY = '';
	let OPENROUTER_API_CONFIG: Record<string, any> = {};

	let openrouterVerifying = false;
	let openrouterVerified: boolean | null = null;
	let showOpenRouterKey = false;

	let connectionsConfig = null;

	let pipelineUrls = {};
	let showAddOpenAIConnectionModal = false;
	let showAddOllamaConnectionModal = false;

	const updateOpenAIHandler = async () => {
		if (ENABLE_OPENAI_API !== null) {
			// Remove trailing slashes
			OPENAI_API_BASE_URLS = OPENAI_API_BASE_URLS.map((url) => url.replace(/\/$/, ''));

			// Check if API KEYS length is same than API URLS length
			if (OPENAI_API_KEYS.length !== OPENAI_API_BASE_URLS.length) {
				// if there are more keys than urls, remove the extra keys
				if (OPENAI_API_KEYS.length > OPENAI_API_BASE_URLS.length) {
					OPENAI_API_KEYS = OPENAI_API_KEYS.slice(0, OPENAI_API_BASE_URLS.length);
				}

				// if there are more urls than keys, add empty keys
				if (OPENAI_API_KEYS.length < OPENAI_API_BASE_URLS.length) {
					const diff = OPENAI_API_BASE_URLS.length - OPENAI_API_KEYS.length;
					for (let i = 0; i < diff; i++) {
						OPENAI_API_KEYS.push('');
					}
				}
			}

			const res = await updateOpenAIConfig(localStorage.token, {
				ENABLE_OPENAI_API: ENABLE_OPENAI_API,
				OPENAI_API_BASE_URLS: OPENAI_API_BASE_URLS,
				OPENAI_API_KEYS: OPENAI_API_KEYS,
				OPENAI_API_CONFIGS: OPENAI_API_CONFIGS
			}).catch((error) => {
				toast.error(`${error}`);
			});

			if (res) {
				toast.success($i18n.t('OpenAI API settings updated'));
				await models.set(await getModels());
			}
		}
	};

	const updateOllamaHandler = async () => {
		if (ENABLE_OLLAMA_API !== null) {
			// Remove trailing slashes
			OLLAMA_BASE_URLS = OLLAMA_BASE_URLS.map((url) => url.replace(/\/$/, ''));

			const res = await updateOllamaConfig(localStorage.token, {
				ENABLE_OLLAMA_API: ENABLE_OLLAMA_API,
				OLLAMA_BASE_URLS: OLLAMA_BASE_URLS,
				OLLAMA_API_CONFIGS: OLLAMA_API_CONFIGS
			}).catch((error) => {
				toast.error(`${error}`);
			});

			if (res) {
				toast.success($i18n.t('Ollama API settings updated'));
				await models.set(await getModels());
			}
		}
	};

	const updateOpenRouterHandler = async () => {
		if (ENABLE_OPENROUTER_API !== null) {
			OPENROUTER_API_BASE_URL = OPENROUTER_API_BASE_URL.replace(/\/$/, '');

			const res = await updateOpenRouterConfig(localStorage.token, {
				ENABLE_OPENROUTER_API: ENABLE_OPENROUTER_API,
				OPENROUTER_API_BASE_URL: OPENROUTER_API_BASE_URL,
				OPENROUTER_API_KEY: OPENROUTER_API_KEY,
				OPENROUTER_API_CONFIG: OPENROUTER_API_CONFIG
			}).catch((error) => {
				toast.error(`${error}`);
			});

			if (res) {
				toast.success($i18n.t('OpenRouter API settings updated'));
				await models.set(await getModels());
			}
		}
	};

	const verifyOpenRouterHandler = async () => {
		openrouterVerifying = true;
		openrouterVerified = null;
		try {
			const res = await verifyOpenRouterConnection(
				localStorage.token,
				OPENROUTER_API_BASE_URL,
				OPENROUTER_API_KEY
			);
			if (res) {
				openrouterVerified = true;
				toast.success($i18n.t('OpenRouter connection verified'));
			}
		} catch (error) {
			openrouterVerified = false;
			toast.error(`${error}`);
		}
		openrouterVerifying = false;
	};

	const updateConnectionsHandler = async () => {
		const res = await setConnectionsConfig(localStorage.token, connectionsConfig).catch((error) => {
			toast.error(`${error}`);
		});

		if (res) {
			toast.success($i18n.t('Connections settings updated'));
			await models.set(await getModels());
			await config.set(await getBackendConfig());
		}
	};

	const addOpenAIConnectionHandler = async (connection) => {
		OPENAI_API_BASE_URLS = [...OPENAI_API_BASE_URLS, connection.url];
		OPENAI_API_KEYS = [...OPENAI_API_KEYS, connection.key];
		OPENAI_API_CONFIGS[OPENAI_API_BASE_URLS.length - 1] = connection.config;

		await updateOpenAIHandler();
	};

	const addOllamaConnectionHandler = async (connection) => {
		OLLAMA_BASE_URLS = [...OLLAMA_BASE_URLS, connection.url];
		OLLAMA_API_CONFIGS[OLLAMA_BASE_URLS.length - 1] = {
			...connection.config,
			key: connection.key
		};

		await updateOllamaHandler();
	};

	onMount(async () => {
		if ($user?.role === 'admin') {
			let ollamaConfig = {};
			let openaiConfig = {};
			let openrouterConfig = {};

			await Promise.all([
				(async () => {
					ollamaConfig = await getOllamaConfig(localStorage.token);
				})(),
				(async () => {
					openaiConfig = await getOpenAIConfig(localStorage.token);
				})(),
				(async () => {
					openrouterConfig = await getOpenRouterConfig(localStorage.token);
				})(),
				(async () => {
					connectionsConfig = await getConnectionsConfig(localStorage.token);
				})()
			]);

			ENABLE_OPENAI_API = openaiConfig.ENABLE_OPENAI_API;
			ENABLE_OLLAMA_API = ollamaConfig.ENABLE_OLLAMA_API;
			ENABLE_OPENROUTER_API = openrouterConfig.ENABLE_OPENROUTER_API;
			OPENROUTER_API_BASE_URL = openrouterConfig.OPENROUTER_API_BASE_URL || 'https://openrouter.ai/api/v1';
			OPENROUTER_API_KEY = openrouterConfig.OPENROUTER_API_KEY || '';
			OPENROUTER_API_CONFIG = openrouterConfig.OPENROUTER_API_CONFIG || {};

			OPENAI_API_BASE_URLS = openaiConfig.OPENAI_API_BASE_URLS;
			OPENAI_API_KEYS = openaiConfig.OPENAI_API_KEYS;
			OPENAI_API_CONFIGS = openaiConfig.OPENAI_API_CONFIGS;

			OLLAMA_BASE_URLS = ollamaConfig.OLLAMA_BASE_URLS;
			OLLAMA_API_CONFIGS = ollamaConfig.OLLAMA_API_CONFIGS;

			if (ENABLE_OPENAI_API) {
				// get url and idx
				for (const [idx, url] of OPENAI_API_BASE_URLS.entries()) {
					if (!OPENAI_API_CONFIGS[idx]) {
						// Legacy support, url as key
						OPENAI_API_CONFIGS[idx] = OPENAI_API_CONFIGS[url] || {};
					}
				}

				OPENAI_API_BASE_URLS.forEach(async (url, idx) => {
					OPENAI_API_CONFIGS[idx] = OPENAI_API_CONFIGS[idx] || {};
					if (!(OPENAI_API_CONFIGS[idx]?.enable ?? true)) {
						return;
					}
					const res = await getOpenAIModels(localStorage.token, idx);
					if (res.pipelines) {
						pipelineUrls[url] = true;
					}
				});
			}

			if (ENABLE_OLLAMA_API) {
				for (const [idx, url] of OLLAMA_BASE_URLS.entries()) {
					if (!OLLAMA_API_CONFIGS[idx]) {
						OLLAMA_API_CONFIGS[idx] = OLLAMA_API_CONFIGS[url] || {};
					}
				}
			}
		}
	});

	const submitHandler = async () => {
		updateOpenAIHandler();
		updateOllamaHandler();
		updateOpenRouterHandler();

		dispatch('save');

		await config.set(await getBackendConfig());
	};
</script>

<AddConnectionModal
	bind:show={showAddOpenAIConnectionModal}
	onSubmit={addOpenAIConnectionHandler}
/>

<AddConnectionModal
	ollama
	bind:show={showAddOllamaConnectionModal}
	onSubmit={addOllamaConnectionHandler}
/>

<form class="flex flex-col h-full justify-between text-sm" on:submit|preventDefault={submitHandler}>
	<div class=" overflow-y-scroll scrollbar-hidden h-full">
		{#if ENABLE_OPENAI_API !== null && ENABLE_OLLAMA_API !== null && ENABLE_OPENROUTER_API !== null && connectionsConfig !== null}
			<div class="mb-3.5">
				<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('General')}</div>

				<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="my-2">
					<div class="mt-2 space-y-2">
						<div class="flex justify-between items-center text-sm">
							<div class="  font-medium">{$i18n.t('OpenAI API')}</div>

							<div class="flex items-center">
								<div class="">
									<Switch
										bind:state={ENABLE_OPENAI_API}
										on:change={async () => {
											updateOpenAIHandler();
										}}
									/>
								</div>
							</div>
						</div>

						{#if ENABLE_OPENAI_API}
							<div class="">
								<div class="flex justify-between items-center">
									<div class="font-medium text-xs">{$i18n.t('Manage OpenAI API Connections')}</div>

									<Tooltip content={$i18n.t(`Add Connection`)}>
										<button
											class="px-1"
											on:click={() => {
												showAddOpenAIConnectionModal = true;
											}}
											type="button"
										>
											<Plus />
										</button>
									</Tooltip>
								</div>

								<div class="flex flex-col gap-1.5 mt-1.5">
									{#each OPENAI_API_BASE_URLS as url, idx}
										<OpenAIConnection
											bind:url={OPENAI_API_BASE_URLS[idx]}
											bind:key={OPENAI_API_KEYS[idx]}
											bind:config={OPENAI_API_CONFIGS[idx]}
											pipeline={pipelineUrls[url] ? true : false}
											onSubmit={() => {
												updateOpenAIHandler();
											}}
											onDelete={() => {
												OPENAI_API_BASE_URLS = OPENAI_API_BASE_URLS.filter(
													(url, urlIdx) => idx !== urlIdx
												);
												OPENAI_API_KEYS = OPENAI_API_KEYS.filter((key, keyIdx) => idx !== keyIdx);

												let newConfig = {};
												OPENAI_API_BASE_URLS.forEach((url, newIdx) => {
													newConfig[newIdx] =
														OPENAI_API_CONFIGS[newIdx < idx ? newIdx : newIdx + 1];
												});
												OPENAI_API_CONFIGS = newConfig;
												updateOpenAIHandler();
											}}
										/>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				</div>

				<div class=" my-2">
					<div class="flex justify-between items-center text-sm mb-2">
						<div class="  font-medium">{$i18n.t('Ollama API')}</div>

						<div class="mt-1">
							<Switch
								bind:state={ENABLE_OLLAMA_API}
								on:change={async () => {
									updateOllamaHandler();
								}}
							/>
						</div>
					</div>

					{#if ENABLE_OLLAMA_API}
						<div class="">
							<div class="flex justify-between items-center">
								<div class="font-medium text-xs">{$i18n.t('Manage Ollama API Connections')}</div>

								<Tooltip content={$i18n.t(`Add Connection`)}>
									<button
										class="px-1"
										on:click={() => {
											showAddOllamaConnectionModal = true;
										}}
										type="button"
									>
										<Plus />
									</button>
								</Tooltip>
							</div>

							<div class="flex w-full gap-1.5">
								<div class="flex-1 flex flex-col gap-1.5 mt-1.5">
									{#each OLLAMA_BASE_URLS as url, idx}
										<OllamaConnection
											bind:url={OLLAMA_BASE_URLS[idx]}
											bind:config={OLLAMA_API_CONFIGS[idx]}
											{idx}
											onSubmit={() => {
												updateOllamaHandler();
											}}
											onDelete={() => {
												OLLAMA_BASE_URLS = OLLAMA_BASE_URLS.filter((url, urlIdx) => idx !== urlIdx);

												let newConfig = {};
												OLLAMA_BASE_URLS.forEach((url, newIdx) => {
													newConfig[newIdx] =
														OLLAMA_API_CONFIGS[newIdx < idx ? newIdx : newIdx + 1];
												});
												OLLAMA_API_CONFIGS = newConfig;
											}}
										/>
									{/each}
								</div>
							</div>

							<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
								{$i18n.t('Trouble accessing Ollama?')}
								<a
									class=" text-gray-300 font-medium underline"
									href="https://github.com/open-webui/open-webui#troubleshooting"
									target="_blank"
								>
									{$i18n.t('Click here for help.')}
								</a>
							</div>
						</div>
					{/if}
				</div>

				<div class="my-2">
					<div class="flex justify-between items-center text-sm mb-2">
						<div class="font-medium">{$i18n.t('OpenRouter API')}</div>

						<div class="mt-1">
							<Switch
								bind:state={ENABLE_OPENROUTER_API}
								on:change={async () => {
									updateOpenRouterHandler();
								}}
							/>
						</div>
					</div>

					{#if ENABLE_OPENROUTER_API}
						<div class="space-y-2">
							<div>
								<div class="font-medium text-xs mb-1">{$i18n.t('API Base URL')}</div>
								<input
									class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									placeholder="https://openrouter.ai/api/v1"
									bind:value={OPENROUTER_API_BASE_URL}
								/>
							</div>

							<div>
								<div class="font-medium text-xs mb-1">{$i18n.t('API Key')}</div>
								<div class="flex gap-2">
									<div class="flex-1 relative">
										<input
											class="w-full rounded-lg py-2 px-4 pr-10 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											placeholder={$i18n.t('Enter OpenRouter API Key')}
											bind:value={OPENROUTER_API_KEY}
											type={showOpenRouterKey ? 'text' : 'password'}
										/>
										<button
											class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-500 dark:text-gray-400"
											type="button"
											on:click={() => {
												showOpenRouterKey = !showOpenRouterKey;
											}}
										>
											{showOpenRouterKey ? '🙈' : '👁'}
										</button>
									</div>

									<Tooltip content={$i18n.t('Verify Connection')}>
										<button
											class="px-3 py-2 text-sm rounded-lg {openrouterVerified === true
												? 'bg-green-500/20 text-green-700 dark:text-green-300'
												: openrouterVerified === false
													? 'bg-red-500/20 text-red-700 dark:text-red-300'
													: 'bg-gray-50 dark:bg-gray-850 text-gray-600 dark:text-gray-300'} hover:opacity-80 transition"
											type="button"
											on:click={verifyOpenRouterHandler}
											disabled={openrouterVerifying}
										>
											{#if openrouterVerifying}
												<Spinner className="size-4" />
											{:else}
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
													<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z" clip-rule="evenodd" />
												</svg>
											{/if}
										</button>
									</Tooltip>
								</div>
							</div>

							<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
								{$i18n.t('OpenRouter provides access to 400+ AI models with automatic fallback, provider routing, and unified pricing.')}
							</div>
						</div>
					{/if}
				</div>

				<div class="my-2">
					<div class="flex justify-between items-center text-sm">
						<div class="  font-medium">{$i18n.t('Direct Connections')}</div>

						<div class="flex items-center">
							<div class="">
								<Switch
									bind:state={connectionsConfig.ENABLE_DIRECT_CONNECTIONS}
									on:change={async () => {
										updateConnectionsHandler();
									}}
								/>
							</div>
						</div>
					</div>

					<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t(
							'Direct Connections allow users to connect to their own OpenAI compatible API endpoints.'
						)}
					</div>
				</div>

				<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="my-2">
					<div class="flex justify-between items-center text-sm">
						<div class=" text-xs font-medium">{$i18n.t('Cache Base Model List')}</div>

						<div class="flex items-center">
							<div class="">
								<Switch
									bind:state={connectionsConfig.ENABLE_BASE_MODELS_CACHE}
									on:change={async () => {
										updateConnectionsHandler();
									}}
								/>
							</div>
						</div>
					</div>

					<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t(
							'Base Model List Cache speeds up access by fetching base models only at startup or on settings save—faster, but may not show recent base model changes.'
						)}
					</div>
				</div>
			</div>
		{:else}
			<div class="flex h-full justify-center">
				<div class="my-auto">
					<Spinner className="size-6" />
				</div>
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
