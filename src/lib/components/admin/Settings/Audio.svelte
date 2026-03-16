<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext } from 'svelte';
	const dispatch = createEventDispatcher();

	import { getBackendConfig } from '$lib/apis';
	import {
		getAudioConfig,
		updateAudioConfig,
		getModels as _getModels,
		getVoices as _getVoices
	} from '$lib/apis/audio';
	import { config, settings } from '$lib/stores';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';

	import { TTS_RESPONSE_SPLIT } from '$lib/types';

	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import Textarea from '$lib/components/common/Textarea.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	export let saveHandler: () => void;

	// Audio
	let TTS_OPENAI_API_BASE_URL = '';
	let TTS_OPENAI_API_KEY = '';
	let TTS_API_KEY = '';
	let TTS_ENGINE = '';
	let TTS_MODEL = '';
	let TTS_VOICE = '';
	let TTS_OPENAI_PARAMS = '';
	let TTS_SPLIT_ON: TTS_RESPONSE_SPLIT = TTS_RESPONSE_SPLIT.PUNCTUATION;
	let TTS_AZURE_SPEECH_REGION = '';
	let TTS_AZURE_SPEECH_BASE_URL = '';
	let TTS_AZURE_SPEECH_OUTPUT_FORMAT = '';

	let STT_OPENAI_API_BASE_URL = '';
	let STT_OPENAI_API_KEY = '';
	let STT_ENGINE = '';
	let STT_MODEL = '';
	let STT_SUPPORTED_CONTENT_TYPES = '';
	let STT_WHISPER_MODEL = '';
	let STT_AZURE_API_KEY = '';
	let STT_AZURE_REGION = '';
	let STT_AZURE_LOCALES = '';
	let STT_AZURE_BASE_URL = '';
	let STT_AZURE_MAX_SPEAKERS = '';
	let STT_DEEPGRAM_API_KEY = '';
	let STT_MISTRAL_API_KEY = '';
	let STT_MISTRAL_API_BASE_URL = '';
	let STT_MISTRAL_USE_CHAT_COMPLETIONS = false;

	let STT_WHISPER_MODEL_LOADING = false;

	// Realtime voice mode
	let REALTIME_ENABLED = false;
	let REALTIME_MODEL = 'openai/gpt-audio-mini';
	let REALTIME_API_BASE_URL = 'https://openrouter.ai/api/v1';
	let REALTIME_API_KEY = '';
	let REALTIME_RESPONSE_MODE = 'streaming';
	let REALTIME_VISION_MODEL = 'google/gemini-2.5-flash';
	let REALTIME_BARGE_IN_ENABLED = true;
	let REALTIME_BARGE_IN_THRESHOLD = 0.06;
	let REALTIME_VOICE_THRESHOLD = 12;
	let REALTIME_MAX_HISTORY_TURNS = 8;
	let REALTIME_SUMMARY_MODEL = '';
	let REALTIME_SUMMARY_PROMPT = 'Summarize this conversation context in 3-5 sentences, preserving all key facts, decisions and topics discussed:';
	let REALTIME_STT_ENABLED = false;
	let REALTIME_CAMERA_INTERVAL = 2;

	// eslint-disable-next-line no-undef
	let voices: SpeechSynthesisVoice[] = [];
	let models: Awaited<ReturnType<typeof _getModels>>['models'] = [];

	const getModels = async () => {
		if (TTS_ENGINE === '') {
			models = [];
		} else {
			const res = await _getModels(
				localStorage.token,
				$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
			).catch((e) => {
				toast.error(`${e}`);
			});

			if (res) {
				console.log(res);
				models = res.models;
			}
		}
	};

	const getVoices = async () => {
		if (TTS_ENGINE === '') {
			const getVoicesLoop = setInterval(() => {
				voices = speechSynthesis.getVoices();

				// do your loop
				if (voices.length > 0) {
					clearInterval(getVoicesLoop);
					voices.sort((a, b) => a.name.localeCompare(b.name, $i18n.resolvedLanguage));
				}
			}, 100);
		} else {
			const res = await _getVoices(localStorage.token).catch((e) => {
				toast.error(`${e}`);
			});

			if (res) {
				console.log(res);
				voices = res.voices;
				voices.sort((a, b) => a.name.localeCompare(b.name, $i18n.resolvedLanguage));
			}
		}
	};

	const updateConfigHandler = async () => {
		let openaiParams = {};
		try {
			openaiParams = TTS_OPENAI_PARAMS ? JSON.parse(TTS_OPENAI_PARAMS) : {};
			TTS_OPENAI_PARAMS = JSON.stringify(openaiParams, null, 2);
		} catch (e) {
			toast.error($i18n.t('Invalid JSON format for Parameters'));
			return;
		}

		const res = await updateAudioConfig(localStorage.token, {
			tts: {
				OPENAI_API_BASE_URL: TTS_OPENAI_API_BASE_URL,
				OPENAI_API_KEY: TTS_OPENAI_API_KEY,
				OPENAI_PARAMS: openaiParams,
				API_KEY: TTS_API_KEY,
				ENGINE: TTS_ENGINE,
				MODEL: TTS_MODEL,
				VOICE: TTS_VOICE,
				AZURE_SPEECH_REGION: TTS_AZURE_SPEECH_REGION,
				AZURE_SPEECH_BASE_URL: TTS_AZURE_SPEECH_BASE_URL,
				AZURE_SPEECH_OUTPUT_FORMAT: TTS_AZURE_SPEECH_OUTPUT_FORMAT,
				SPLIT_ON: TTS_SPLIT_ON
			},
			stt: {
				OPENAI_API_BASE_URL: STT_OPENAI_API_BASE_URL,
				OPENAI_API_KEY: STT_OPENAI_API_KEY,
				ENGINE: STT_ENGINE,
				MODEL: STT_MODEL,
				SUPPORTED_CONTENT_TYPES: STT_SUPPORTED_CONTENT_TYPES.split(','),
				WHISPER_MODEL: STT_WHISPER_MODEL,
				DEEPGRAM_API_KEY: STT_DEEPGRAM_API_KEY,
				AZURE_API_KEY: STT_AZURE_API_KEY,
				AZURE_REGION: STT_AZURE_REGION,
				AZURE_LOCALES: STT_AZURE_LOCALES,
				AZURE_BASE_URL: STT_AZURE_BASE_URL,
				AZURE_MAX_SPEAKERS: STT_AZURE_MAX_SPEAKERS,
				MISTRAL_API_KEY: STT_MISTRAL_API_KEY,
				MISTRAL_API_BASE_URL: STT_MISTRAL_API_BASE_URL,
				MISTRAL_USE_CHAT_COMPLETIONS: STT_MISTRAL_USE_CHAT_COMPLETIONS
			},
			realtime: {
				ENABLED: REALTIME_ENABLED,
				MODEL: REALTIME_MODEL,
				API_BASE_URL: REALTIME_API_BASE_URL,
				API_KEY: REALTIME_API_KEY,
				RESPONSE_MODE: REALTIME_RESPONSE_MODE,
				VISION_MODEL: REALTIME_VISION_MODEL,
				BARGE_IN_ENABLED: REALTIME_BARGE_IN_ENABLED,
				BARGE_IN_THRESHOLD: REALTIME_BARGE_IN_THRESHOLD,
				VOICE_THRESHOLD: REALTIME_VOICE_THRESHOLD,
				MAX_HISTORY_TURNS: REALTIME_MAX_HISTORY_TURNS,
				SUMMARY_MODEL: REALTIME_SUMMARY_MODEL,
				SUMMARY_PROMPT: REALTIME_SUMMARY_PROMPT,
				STT_ENABLED: REALTIME_STT_ENABLED,
				CAMERA_INTERVAL: REALTIME_CAMERA_INTERVAL
			}
		});

		if (res) {
			saveHandler();
			config.set(await getBackendConfig());
		}
	};

	const sttModelUpdateHandler = async () => {
		STT_WHISPER_MODEL_LOADING = true;
		await updateConfigHandler();
		STT_WHISPER_MODEL_LOADING = false;
	};

	onMount(async () => {
		const res = await getAudioConfig(localStorage.token);

		if (res) {
			console.log(res);
			TTS_OPENAI_API_BASE_URL = res.tts.OPENAI_API_BASE_URL;
			TTS_OPENAI_API_KEY = res.tts.OPENAI_API_KEY;
			TTS_OPENAI_PARAMS = JSON.stringify(res?.tts?.OPENAI_PARAMS ?? '', null, 2);
			TTS_API_KEY = res.tts.API_KEY;

			TTS_ENGINE = res.tts.ENGINE;
			TTS_MODEL = res.tts.MODEL;
			TTS_VOICE = res.tts.VOICE;

			TTS_SPLIT_ON = res.tts.SPLIT_ON || TTS_RESPONSE_SPLIT.PUNCTUATION;

			TTS_AZURE_SPEECH_REGION = res.tts.AZURE_SPEECH_REGION;
			TTS_AZURE_SPEECH_BASE_URL = res.tts.AZURE_SPEECH_BASE_URL;
			TTS_AZURE_SPEECH_OUTPUT_FORMAT = res.tts.AZURE_SPEECH_OUTPUT_FORMAT;

			STT_OPENAI_API_BASE_URL = res.stt.OPENAI_API_BASE_URL;
			STT_OPENAI_API_KEY = res.stt.OPENAI_API_KEY;

			STT_ENGINE = res.stt.ENGINE;
			STT_MODEL = res.stt.MODEL;
			STT_SUPPORTED_CONTENT_TYPES = (res?.stt?.SUPPORTED_CONTENT_TYPES ?? []).join(',');
			STT_WHISPER_MODEL = res.stt.WHISPER_MODEL;
			STT_AZURE_API_KEY = res.stt.AZURE_API_KEY;
			STT_AZURE_REGION = res.stt.AZURE_REGION;
			STT_AZURE_LOCALES = res.stt.AZURE_LOCALES;
			STT_AZURE_BASE_URL = res.stt.AZURE_BASE_URL;
			STT_AZURE_MAX_SPEAKERS = res.stt.AZURE_MAX_SPEAKERS;
			STT_DEEPGRAM_API_KEY = res.stt.DEEPGRAM_API_KEY;
			STT_MISTRAL_API_KEY = res.stt.MISTRAL_API_KEY;
			STT_MISTRAL_API_BASE_URL = res.stt.MISTRAL_API_BASE_URL;
			STT_MISTRAL_USE_CHAT_COMPLETIONS = res.stt.MISTRAL_USE_CHAT_COMPLETIONS;

			if (res.realtime) {
				REALTIME_ENABLED = res.realtime.ENABLED ?? false;
				REALTIME_MODEL = res.realtime.MODEL ?? 'openai/gpt-audio-mini';
				REALTIME_API_BASE_URL = res.realtime.API_BASE_URL ?? 'https://openrouter.ai/api/v1';
				REALTIME_API_KEY = res.realtime.API_KEY ?? '';
				REALTIME_RESPONSE_MODE = res.realtime.RESPONSE_MODE ?? 'streaming';
				REALTIME_VISION_MODEL = res.realtime.VISION_MODEL ?? 'google/gemini-2.5-flash';
				REALTIME_BARGE_IN_ENABLED = res.realtime.BARGE_IN_ENABLED ?? true;
				REALTIME_BARGE_IN_THRESHOLD = res.realtime.BARGE_IN_THRESHOLD ?? 0.06;
				REALTIME_VOICE_THRESHOLD = res.realtime.VOICE_THRESHOLD ?? 12;
				REALTIME_MAX_HISTORY_TURNS = res.realtime.MAX_HISTORY_TURNS ?? 8;
				REALTIME_SUMMARY_MODEL = res.realtime.SUMMARY_MODEL ?? '';
				REALTIME_SUMMARY_PROMPT = res.realtime.SUMMARY_PROMPT ?? 'Summarize this conversation context in 3-5 sentences, preserving all key facts, decisions and topics discussed:';
				REALTIME_STT_ENABLED = res.realtime.STT_ENABLED ?? false;
				REALTIME_CAMERA_INTERVAL = res.realtime.CAMERA_INTERVAL ?? 2;
			}
		}

		await getVoices();
		await getModels();
	});
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		await updateConfigHandler();
		dispatch('save');
	}}
>
	<div class=" space-y-3 overflow-y-scroll scrollbar-hidden h-full">
		<div class="flex flex-col gap-3">
			<div>
				<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Speech-to-Text')}</div>

				<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

				{#if STT_ENGINE !== 'web'}
					<div class="mb-2">
						<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Supported MIME Types')}</div>
						<div class="flex w-full">
							<div class="flex-1">
								<input
									class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									bind:value={STT_SUPPORTED_CONTENT_TYPES}
									placeholder={$i18n.t(
										'e.g., audio/wav,audio/mpeg,video/* (leave blank for defaults)'
									)}
								/>
							</div>
						</div>
					</div>
				{/if}

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class=" self-center text-xs font-medium">{$i18n.t('Speech-to-Text Engine')}</div>
					<div class="flex items-center relative">
						<select
							class="cursor-pointer w-fit pr-8 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
							bind:value={STT_ENGINE}
							placeholder={$i18n.t('Select an engine')}
						>
							<option value="">{$i18n.t('Whisper (Local)')}</option>
							<option value="openai">{$i18n.t('OpenAI')}</option>
							<option value="web">{$i18n.t('Web API')}</option>
							<option value="deepgram">{$i18n.t('Deepgram')}</option>
							<option value="azure">{$i18n.t('Azure AI Speech')}</option>
							<option value="mistral">{$i18n.t('MistralAI')}</option>
						</select>
					</div>
				</div>

				{#if STT_ENGINE === 'openai'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<input
								class="flex-1 w-full bg-transparent outline-hidden"
								placeholder={$i18n.t('API Base URL')}
								bind:value={STT_OPENAI_API_BASE_URL}
								required
							/>

							<SensitiveInput placeholder={$i18n.t('API Key')} bind:value={STT_OPENAI_API_KEY} />
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div>
						<div class=" mb-1.5 text-xs font-medium">{$i18n.t('STT Model')}</div>
						<div class="flex w-full">
							<div class="flex-1">
								<input
									list="model-list"
									class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									bind:value={STT_MODEL}
									placeholder={$i18n.t('Select a model')}
								/>

								<datalist id="model-list">
									<option value="whisper-1" />
								</datalist>
							</div>
						</div>
					</div>
				{:else if STT_ENGINE === 'deepgram'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<SensitiveInput placeholder={$i18n.t('API Key')} bind:value={STT_DEEPGRAM_API_KEY} />
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div>
						<div class=" mb-1.5 text-xs font-medium">{$i18n.t('STT Model')}</div>
						<div class="flex w-full">
							<div class="flex-1">
								<input
									class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									bind:value={STT_MODEL}
									placeholder={$i18n.t('Select a model (optional)')}
								/>
							</div>
						</div>
						<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('Leave model field empty to use the default model.')}
							<a
								class=" hover:underline dark:text-gray-200 text-gray-800"
								href="https://developers.deepgram.com/docs/models"
								target="_blank"
							>
								{$i18n.t('Click here to see available models.')}
							</a>
						</div>
					</div>
				{:else if STT_ENGINE === 'azure'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<SensitiveInput
								placeholder={$i18n.t('API Key')}
								bind:value={STT_AZURE_API_KEY}
								required
							/>
						</div>

						<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Azure Region')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={STT_AZURE_REGION}
										placeholder={$i18n.t('e.g., westus (leave blank for eastus)')}
									/>
								</div>
							</div>
						</div>

						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Language Locales')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={STT_AZURE_LOCALES}
										placeholder={$i18n.t('e.g., en-US,ja-JP (leave blank for auto-detect)')}
									/>
								</div>
							</div>
						</div>

						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Endpoint URL')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={STT_AZURE_BASE_URL}
										placeholder={$i18n.t('(leave blank for to use commercial endpoint)')}
									/>
								</div>
							</div>
						</div>

						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Max Speakers')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={STT_AZURE_MAX_SPEAKERS}
										placeholder={$i18n.t('e.g., 3, 4, 5 (leave blank for default)')}
									/>
								</div>
							</div>
						</div>
					</div>
				{:else if STT_ENGINE === 'mistral'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<input
								class="flex-1 w-full bg-transparent outline-hidden"
								placeholder={$i18n.t('API Base URL')}
								bind:value={STT_MISTRAL_API_BASE_URL}
								required
							/>

							<SensitiveInput placeholder={$i18n.t('API Key')} bind:value={STT_MISTRAL_API_KEY} />
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div>
						<div class=" mb-1.5 text-xs font-medium">{$i18n.t('STT Model')}</div>
						<div class="flex w-full">
							<div class="flex-1">
								<input
									class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									bind:value={STT_MODEL}
									placeholder="voxtral-mini-latest"
								/>
							</div>
						</div>
						<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('Leave empty to use the default model (voxtral-mini-latest).')}
							<a
								class=" hover:underline dark:text-gray-200 text-gray-800"
								href="https://docs.mistral.ai/capabilities/audio_transcription"
								target="_blank"
							>
								{$i18n.t('Learn more about Voxtral transcription.')}
							</a>
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div>
						<div class="flex items-center justify-between mb-2">
							<div class="text-xs font-medium">{$i18n.t('Use Chat Completions API')}</div>
							<label class="relative inline-flex items-center cursor-pointer">
								<input
									type="checkbox"
									bind:checked={STT_MISTRAL_USE_CHAT_COMPLETIONS}
									class="sr-only peer"
								/>
								<div
									class="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"
								></div>
							</label>
						</div>
						<div class="text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t(
								'Use /v1/chat/completions endpoint instead of /v1/audio/transcriptions for potentially better accuracy.'
							)}
						</div>
					</div>
				{:else if STT_ENGINE === ''}
					<div>
						<div class=" mb-1.5 text-xs font-medium">{$i18n.t('STT Model')}</div>

						<div class="flex w-full">
							<div class="flex-1 mr-2">
								<input
									class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									placeholder={$i18n.t('Set whisper model')}
									bind:value={STT_WHISPER_MODEL}
								/>
							</div>

							<button
								class="px-2.5 bg-gray-50 hover:bg-gray-200 text-gray-800 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-100 rounded-lg transition"
								on:click={() => {
									sttModelUpdateHandler();
								}}
								disabled={STT_WHISPER_MODEL_LOADING}
							>
								{#if STT_WHISPER_MODEL_LOADING}
									<div class="self-center">
										<Spinner />
									</div>
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 16 16"
										fill="currentColor"
										class="w-4 h-4"
									>
										<path
											d="M8.75 2.75a.75.75 0 0 0-1.5 0v5.69L5.03 6.22a.75.75 0 0 0-1.06 1.06l3.5 3.5a.75.75 0 0 0 1.06 0l3.5-3.5a.75.75 0 0 0-1.06-1.06L8.75 8.44V2.75Z"
										/>
										<path
											d="M3.5 9.75a.75.75 0 0 0-1.5 0v1.5A2.75 2.75 0 0 0 4.75 14h6.5A2.75 2.75 0 0 0 14 11.25v-1.5a.75.75 0 0 0-1.5 0v1.5c0 .69-.56 1.25-1.25 1.25h-6.5c-.69 0-1.25-.56-1.25-1.25v-1.5Z"
										/>
									</svg>
								{/if}
							</button>
						</div>

						<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t(`Open WebUI uses faster-whisper internally.`)}

							<a
								class=" hover:underline dark:text-gray-200 text-gray-800"
								href="https://github.com/SYSTRAN/faster-whisper"
								target="_blank"
							>
								{$i18n.t(
									`Click here to learn more about faster-whisper and see the available models.`
								)}
							</a>
						</div>
					</div>
				{/if}
			</div>

			<div>
				<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Text-to-Speech')}</div>

				<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class=" self-center text-xs font-medium">{$i18n.t('Text-to-Speech Engine')}</div>
					<div class="flex items-center relative">
						<select
							class="w-fit pr-8 cursor-pointer rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
							bind:value={TTS_ENGINE}
							placeholder={$i18n.t('Select a mode')}
							on:change={async (e) => {
								await updateConfigHandler();
								await getVoices();
								await getModels();

								if (e.target?.value === 'openai') {
									TTS_VOICE = 'alloy';
									TTS_MODEL = 'tts-1';
								} else {
									TTS_VOICE = '';
									TTS_MODEL = '';
								}
							}}
						>
							<option value="">{$i18n.t('Web API')}</option>
							<option value="transformers">{$i18n.t('Transformers')} ({$i18n.t('Local')})</option>
							<option value="openai">{$i18n.t('OpenAI')}</option>
							<option value="elevenlabs">{$i18n.t('ElevenLabs')}</option>
							<option value="azure">{$i18n.t('Azure AI Speech')}</option>
						</select>
					</div>
				</div>

				{#if TTS_ENGINE === 'openai'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<input
								class="flex-1 w-full bg-transparent outline-hidden"
								placeholder={$i18n.t('API Base URL')}
								bind:value={TTS_OPENAI_API_BASE_URL}
								required
							/>

							<SensitiveInput placeholder={$i18n.t('API Key')} bind:value={TTS_OPENAI_API_KEY} />
						</div>
					</div>
				{:else if TTS_ENGINE === 'elevenlabs'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<SensitiveInput placeholder={$i18n.t('API Key')} bind:value={TTS_API_KEY} required />
						</div>
					</div>
				{:else if TTS_ENGINE === 'azure'}
					<div>
						<div class="mt-1 flex gap-2 mb-1">
							<SensitiveInput placeholder={$i18n.t('API Key')} bind:value={TTS_API_KEY} required />
						</div>

						<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Azure Region')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={TTS_AZURE_SPEECH_REGION}
										placeholder={$i18n.t('e.g., westus (leave blank for eastus)')}
									/>
								</div>
							</div>
						</div>

						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Endpoint URL')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={TTS_AZURE_SPEECH_BASE_URL}
										placeholder={$i18n.t('(leave blank for to use commercial endpoint)')}
									/>
								</div>
							</div>
						</div>
					</div>
				{/if}

				<div class="mb-2">
					{#if TTS_ENGINE === ''}
						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Voice')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<select
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={TTS_VOICE}
									>
										<option value="" selected={TTS_VOICE !== ''}>{$i18n.t('Default')}</option>
										{#each voices as voice}
											<option
												value={voice.voiceURI}
												class="bg-gray-100 dark:bg-gray-700"
												selected={TTS_VOICE === voice.voiceURI}>{voice.name}</option
											>
										{/each}
									</select>
								</div>
							</div>
						</div>
					{:else if TTS_ENGINE === 'transformers'}
						<div>
							<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Model')}</div>
							<div class="flex w-full">
								<div class="flex-1">
									<input
										list="model-list"
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={TTS_MODEL}
										placeholder={$i18n.t('CMU ARCTIC speaker embedding name')}
									/>

									<datalist id="model-list">
										<option value="tts-1" />
									</datalist>
								</div>
							</div>
							<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
								{$i18n.t(`Open WebUI uses SpeechT5 and CMU Arctic speaker embeddings.`)}

								To learn more about SpeechT5,

								<a
									class=" hover:underline dark:text-gray-200 text-gray-800"
									href="https://github.com/microsoft/SpeechT5"
									target="_blank"
								>
									{$i18n.t(`click here`, {
										name: 'SpeechT5'
									})}.
								</a>
								To see the available CMU Arctic speaker embeddings,
								<a
									class=" hover:underline dark:text-gray-200 text-gray-800"
									href="https://huggingface.co/datasets/Matthijs/cmu-arctic-xvectors"
									target="_blank"
								>
									{$i18n.t(`click here`)}.
								</a>
							</div>
						</div>
					{:else if TTS_ENGINE === 'openai'}
						<div class=" flex gap-2">
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Voice')}</div>
								<div class="flex w-full">
									<div class="flex-1">
										<input
											list="voice-list"
											class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_VOICE}
											placeholder={$i18n.t('Select a voice')}
										/>

										<datalist id="voice-list">
											{#each voices as voice}
												<option value={voice.id}>{voice.name}</option>
											{/each}
										</datalist>
									</div>
								</div>
							</div>
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Model')}</div>
								<div class="flex w-full">
									<div class="flex-1">
										<input
											list="tts-model-list"
											class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_MODEL}
											placeholder={$i18n.t('Select a model')}
										/>

										<datalist id="tts-model-list">
											{#each models as model}
												<option value={model.id} class="bg-gray-50 dark:bg-gray-700" />
											{/each}
										</datalist>
									</div>
								</div>
							</div>
						</div>

						<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">{$i18n.t('Additional Parameters')}</div>
								<div class="flex w-full">
									<div class="flex-1">
										<Textarea
											className="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_OPENAI_PARAMS}
											placeholder={$i18n.t('Enter additional parameters in JSON format')}
											minSize={100}
										/>
									</div>
								</div>
							</div>
						</div>
					{:else if TTS_ENGINE === 'elevenlabs'}
						<div class=" flex gap-2">
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Voice')}</div>
								<div class="flex w-full">
									<div class="flex-1">
										<input
											list="voice-list"
											class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_VOICE}
											placeholder={$i18n.t('Select a voice')}
										/>

										<datalist id="voice-list">
											{#each voices as voice}
												<option value={voice.id}>{voice.name}</option>
											{/each}
										</datalist>
									</div>
								</div>
							</div>
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Model')}</div>
								<div class="flex w-full">
									<div class="flex-1">
										<input
											list="tts-model-list"
											class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_MODEL}
											placeholder={$i18n.t('Select a model')}
										/>

										<datalist id="tts-model-list">
											{#each models as model}
												<option value={model.id} class="bg-gray-50 dark:bg-gray-700" />
											{/each}
										</datalist>
									</div>
								</div>
							</div>
						</div>
					{:else if TTS_ENGINE === 'azure'}
						<div class=" flex gap-2">
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">{$i18n.t('TTS Voice')}</div>
								<div class="flex w-full">
									<div class="flex-1">
										<input
											list="voice-list"
											class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_VOICE}
											placeholder={$i18n.t('Select a voice')}
										/>

										<datalist id="voice-list">
											{#each voices as voice}
												<option value={voice.id}>{voice.name}</option>
											{/each}
										</datalist>
									</div>
								</div>
							</div>
							<div class="w-full">
								<div class=" mb-1.5 text-xs font-medium">
									{$i18n.t('Output format')}
									<a
										href="https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech?tabs=streaming#audio-outputs"
										target="_blank"
									>
										<small>{$i18n.t('Available list')}</small>
									</a>
								</div>
								<div class="flex w-full">
									<div class="flex-1">
										<input
											list="tts-model-list"
											class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
											bind:value={TTS_AZURE_SPEECH_OUTPUT_FORMAT}
											placeholder={$i18n.t('Select an output format')}
										/>
									</div>
								</div>
							</div>
						</div>
					{/if}
				</div>

				<div class="pt-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">{$i18n.t('Response splitting')}</div>
					<div class="flex items-center relative">
						<select
							class="w-fit pr-8 cursor-pointer rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
							aria-label={$i18n.t('Select how to split message text for TTS requests')}
							bind:value={TTS_SPLIT_ON}
						>
							{#each Object.values(TTS_RESPONSE_SPLIT) as split}
								<option value={split}
									>{$i18n.t(split.charAt(0).toUpperCase() + split.slice(1))}</option
								>
							{/each}
						</select>
					</div>
				</div>
				<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
					{$i18n.t(
						"Control how message text is split for TTS requests. 'Punctuation' splits into sentences, 'paragraphs' splits into paragraphs, and 'none' keeps the message as a single string."
					)}
				</div>
			</div>
		</div>

		<div>
			<div class="mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Realtime Voice Mode')}</div>

			<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

			<div class="mb-2 py-0.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">{$i18n.t('Enable Realtime Voice Mode')}</div>
				<button
					class="p-1 px-3 text-xs flex rounded-sm transition {REALTIME_ENABLED
						? 'bg-gray-200 dark:bg-gray-700'
						: ''} hover:bg-gray-200 dark:hover:bg-gray-700"
					type="button"
					on:click={() => { REALTIME_ENABLED = !REALTIME_ENABLED; }}
				>
					{#if REALTIME_ENABLED}
						{$i18n.t('On')}
					{:else}
						{$i18n.t('Off')}
					{/if}
				</button>
			</div>

			{#if REALTIME_ENABLED}
				<div class="mb-2">
					<div class="mb-1.5 text-xs font-medium">{$i18n.t('API Base URL')}</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
						bind:value={REALTIME_API_BASE_URL}
						placeholder="https://openrouter.ai/api/v1"
					/>
				</div>

				<div class="mb-2">
					<div class="mb-1.5 text-xs font-medium">{$i18n.t('API Key')}</div>
					<SensitiveInput
						placeholder={$i18n.t('API Key')}
						bind:value={REALTIME_API_KEY}
					/>
				</div>

				<div class="mb-2">
					<div class="mb-1.5 text-xs font-medium">{$i18n.t('Model')}</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
						bind:value={REALTIME_MODEL}
						placeholder="openai/gpt-audio-mini"
					/>
				</div>

				<div class="mb-2">
					<div class="mb-1.5 text-xs font-medium">{$i18n.t('Vision Model')} <span class="text-gray-400 font-normal">{$i18n.t('(for camera frame description)')}</span></div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
						bind:value={REALTIME_VISION_MODEL}
						placeholder="google/gemini-2.5-flash"
					/>
				</div>

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">{$i18n.t('Response Mode')}</div>
					<div class="flex items-center relative">
						<select
							class="cursor-pointer w-fit pr-8 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
							bind:value={REALTIME_RESPONSE_MODE}
						>
							<option value="streaming">{$i18n.t('Streaming (OpenRouter)')}</option>
							<option value="non-streaming">{$i18n.t('Non-streaming (OpenAI)')}</option>
						</select>
					</div>
				</div>

				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">{$i18n.t('Barge-in (interrupt AI while speaking)')}</div>
					<button
						class="p-1 px-3 text-xs flex rounded-sm transition {REALTIME_BARGE_IN_ENABLED
							? 'bg-gray-200 dark:bg-gray-700'
							: ''} hover:bg-gray-200 dark:hover:bg-gray-700"
						type="button"
						on:click={() => { REALTIME_BARGE_IN_ENABLED = !REALTIME_BARGE_IN_ENABLED; }}
					>
						{REALTIME_BARGE_IN_ENABLED ? $i18n.t('On') : $i18n.t('Off')}
					</button>
				</div>

				{#if REALTIME_BARGE_IN_ENABLED}
				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Barge-in Sensitivity')}
						<span class="text-gray-400 font-normal">{$i18n.t('(RMS threshold, lower = more sensitive)')}</span>
					</div>
					<div class="flex items-center gap-2">
						<input
							type="range" min="0.01" max="0.3" step="0.01"
							class="w-24 accent-black dark:accent-white"
							bind:value={REALTIME_BARGE_IN_THRESHOLD}
						/>
						<span class="text-xs w-8 text-right">{REALTIME_BARGE_IN_THRESHOLD.toFixed(2)}</span>
					</div>
				</div>
				{/if}

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Voice Detection Threshold')}
						<span class="text-gray-400 font-normal">{$i18n.t('(frequency, lower = more sensitive)')}</span>
					</div>
					<div class="flex items-center gap-2">
						<input
							type="range" min="1" max="60" step="1"
							class="w-24 accent-black dark:accent-white"
							bind:value={REALTIME_VOICE_THRESHOLD}
						/>
						<span class="text-xs w-8 text-right">{REALTIME_VOICE_THRESHOLD}</span>
					</div>
				</div>

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Max History Turns')}
						<span class="text-gray-400 font-normal">
							{REALTIME_MAX_HISTORY_TURNS === 0 ? $i18n.t('(disabled — no context)') : $i18n.t('(pairs sent to API)')}
						</span>
					</div>
					<div class="flex items-center gap-2">
						<input
							type="range" min="0" max="20" step="1"
							class="w-24 accent-black dark:accent-white"
							bind:value={REALTIME_MAX_HISTORY_TURNS}
						/>
						<span class="text-xs w-8 text-right">{REALTIME_MAX_HISTORY_TURNS}</span>
					</div>
				</div>
				<div class="mb-2 text-xs text-gray-400 dark:text-gray-500">
					{$i18n.t('Number of recent voice exchanges (user + assistant) sent as context. Older turns are compressed into a summary. Set to 0 to disable history — each exchange starts fresh.')}
				</div>

				{#if REALTIME_MAX_HISTORY_TURNS > 0}
					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="mb-2">
						<div class="mb-1.5 text-xs font-medium">
							{$i18n.t('Summary Model')}
							<span class="text-gray-400 font-normal">{$i18n.t('(for compressing old voice turns)')}</span>
						</div>
						<input
							class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
							bind:value={REALTIME_SUMMARY_MODEL}
							placeholder={$i18n.t('Leave empty to use the realtime model')}
						/>
					</div>

					<div class="mb-2">
						<div class="mb-1.5 text-xs font-medium">{$i18n.t('Summary Prompt')}</div>
						<Textarea
							className="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
							bind:value={REALTIME_SUMMARY_PROMPT}
							placeholder={$i18n.t('Prompt used to compress old conversation turns into a summary')}
							minSize={60}
						/>
						<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('The conversation text will be appended after this prompt.')}
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />
				{/if}

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">
						{$i18n.t('STT Transcription')}
						<span class="text-gray-400 font-normal">{$i18n.t('(parallel Whisper for user speech)')}</span>
					</div>
					<button
						class="p-1 px-3 text-xs flex rounded-sm transition {REALTIME_STT_ENABLED
							? 'bg-gray-200 dark:bg-gray-700'
							: ''} hover:bg-gray-200 dark:hover:bg-gray-700"
						type="button"
						on:click={() => { REALTIME_STT_ENABLED = !REALTIME_STT_ENABLED; }}
					>
						{REALTIME_STT_ENABLED ? $i18n.t('On') : $i18n.t('Off')}
					</button>
				</div>
				<div class="mb-2 text-xs text-gray-400 dark:text-gray-500">
					{$i18n.t('Runs Whisper in parallel with the audio model to transcribe user speech. Enable if your provider does not return user transcription. Adds server load.')}
				</div>

				<div class="mb-2 py-0.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Camera Frame Interval')}
						<span class="text-gray-400 font-normal">{$i18n.t('(seconds)')}</span>
					</div>
					<div class="flex items-center gap-2">
						<input
							type="range" min="0.1" max="10" step="0.1"
							class="w-24 accent-black dark:accent-white"
							bind:value={REALTIME_CAMERA_INTERVAL}
						/>
						<span class="text-xs w-10 text-right">{REALTIME_CAMERA_INTERVAL.toFixed(1)}s</span>
					</div>
				</div>
			{/if}
		</div>
	</div>
	<div class="flex justify-end text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
