<script lang="ts">
	import { onMount, onDestroy, getContext, createEventDispatcher } from 'svelte';
	import { config, models, settings, showCallOverlay } from '$lib/stores';
	import { WEBUI_BASE_URL, WEBUI_API_BASE_URL } from '$lib/constants';
	import { toast } from 'svelte-sonner';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import VideoInputMenu from './CallOverlay/VideoInputMenu.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let modelId: string;
	export let chatId: string;

	// ----- realtime config from backend (loaded in onMount) -----
	let realtimeApiUrl = '';
	let useWebSocket = false;

	// ----- abort controller for in-flight HTTP requests -----
	let abortController: AbortController | null = null;
	let isSending = false;           // true while waiting for API response
	let partialAssistantText = '';   // text collected before barge-in

	// ----- state -----
	type Status = 'connecting' | 'listening' | 'recording' | 'thinking' | 'speaking' | 'error';
	let status: Status = 'connecting';
	let statusMessage = '';
	let model: any = null;
	let wakeLock: WakeLockSentinel | null = null;

	// Conversation history for context (text only for now)
	let history: { role: string; content: string }[] = [];
	let compressedSummary = ''; // LLM-compressed old context
	let isCompressing = false;
	let transcript = '';

	// ----- WebSocket (OpenAI Realtime) -----
	let ws: WebSocket | null = null;

	// ----- Audio capture -----
	const MIN_DECIBELS = -55;
	// Loaded from admin config; fallback to safe defaults until init() completes
	let VOICE_FREQ_THRESHOLD = 12;
	let BARGE_IN_ENABLED = false;
	let BARGE_IN_RMS_THRESHOLD = 0.06;
	let MAX_HISTORY_TURNS = 8;
	let CAMERA_INTERVAL_SECS = 2;
	let audioStream: MediaStream | null = null;
	let mediaRecorder: MediaRecorder | null = null;
	let audioChunks: Blob[] = [];
	let hasStartedSpeaking = false;
	let confirmed = false;
	let audioContext: AudioContext | null = null;
	let analyser: AnalyserNode | null = null;
	let rmsLevel = 0;

	// ----- Audio playback -----
	let playbackContext: AudioContext | null = null;
	let playbackQueue: Float32Array[] = [];
	let isPlaying = false;
	let currentSource: AudioBufferSourceNode | null = null;

	// ----- Camera -----
	let camera = false;
	let cameraStream: MediaStream | null = null;
	let videoInputDevices: MediaDeviceInfo[] = [];
	let selectedVideoInputDeviceId: string | null = null;
	let cameraIntervalId: ReturnType<typeof setInterval> | null = null;

	// =========================================================
	// Utilities
	// =========================================================

	function getVoice(): string {
		if (model?.info?.meta?.tts?.voice) return model.info.meta.tts.voice;
		return $settings?.audio?.tts?.voice ?? 'alloy';
	}

	function arrayBufferToBase64(buf: Uint8Array): string {
		let s = '';
		for (let i = 0; i < buf.byteLength; i++) s += String.fromCharCode(buf[i]);
		return btoa(s);
	}

	function base64ToFloat32(b64: string): Float32Array {
		const binary = atob(b64);
		const bytes = new Uint8Array(binary.length);
		for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
		const int16 = new Int16Array(bytes.buffer);
		const f32 = new Float32Array(int16.length);
		for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768;
		return f32;
	}

	// =========================================================
	// Audio playback
	// =========================================================

	function ensurePlaybackContext() {
		if (!playbackContext || playbackContext.state === 'closed') {
			playbackContext = new AudioContext({ sampleRate: 24000 });
		}
	}

	function enqueueAudio(b64: string) {
		playbackQueue.push(base64ToFloat32(b64));
		if (!isPlaying) playNextChunk();
	}

	function playNextChunk() {
		if (playbackQueue.length === 0) {
			isPlaying = false;
			if (status === 'speaking') status = 'listening';
			return;
		}
		isPlaying = true;
		ensurePlaybackContext();

		let total = 0;
		for (const c of playbackQueue) total += c.length;
		const merged = new Float32Array(total);
		let off = 0;
		for (const c of playbackQueue) { merged.set(c, off); off += c.length; }
		playbackQueue = [];

		const buf = playbackContext!.createBuffer(1, merged.length, 24000);
		buf.getChannelData(0).set(merged);
		currentSource = playbackContext!.createBufferSource();
		currentSource.buffer = buf;
		currentSource.connect(playbackContext!.destination);
		currentSource.onended = () => { currentSource = null; playNextChunk(); };
		currentSource.start();
	}

	function stopPlayback() {
		playbackQueue = [];
		try { currentSource?.stop(); } catch {}
		currentSource = null;
		isPlaying = false;
	}

	// Play WAV/MP3 etc via Audio element (for HTTP mode response)
	function playAudioBlob(b64: string, fmt: string): Promise<void> {
		// pcm16 = raw signed 16-bit little-endian PCM at 24kHz — decode via AudioContext
		if (fmt === 'pcm16') {
			return new Promise((resolve) => {
				try {
					const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
					const int16 = new Int16Array(bytes.buffer);
					const f32 = new Float32Array(int16.length);
					for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768;
					ensurePlaybackContext();
					const buf = playbackContext!.createBuffer(1, f32.length, 24000);
					buf.getChannelData(0).set(f32);
					const src = playbackContext!.createBufferSource();
					src.buffer = buf;
					src.connect(playbackContext!.destination);
					src.onended = () => resolve();
					src.start();
				} catch {
					resolve();
				}
			});
		}
		return new Promise((resolve) => {
			const mime = fmt === 'mp3' ? 'audio/mpeg' : fmt === 'webm' ? 'audio/webm' : 'audio/wav';
			const blob = new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], { type: mime });
			const url = URL.createObjectURL(blob);
			const audio = new Audio(url);
			audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
			audio.onerror = () => { URL.revokeObjectURL(url); resolve(); };
			audio.play().catch(() => resolve());
		});
	}

	// =========================================================
	// History compression
	// =========================================================

	async function compressHistory() {
		if (isCompressing || history.length <= MAX_HISTORY_TURNS * 2) return;
		isCompressing = true;

		const keepCount = MAX_HISTORY_TURNS * 2;
		const toCompress = history.slice(0, history.length - keepCount);
		const recent = history.slice(history.length - keepCount);

		const dialogue = toCompress.map((m) => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`).join('\n');
		const prevContext = compressedSummary ? `Previous summary:\n${compressedSummary}\n\nNew exchanges:\n` : '';

		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/chat/completions`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${localStorage.token}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					model: model?.id,
					messages: [
						{
							role: 'user',
							content: `Summarize this conversation context in 3-5 sentences, preserving all key facts, decisions and topics discussed:\n\n${prevContext}${dialogue}`
						}
					],
					stream: false
				})
			});
			if (res.ok) {
				const data = await res.json();
				const summary = data.choices?.[0]?.message?.content?.trim();
				if (summary) {
					compressedSummary = summary;
					history = recent;
				}
			}
		} catch {}
		isCompressing = false;
	}

	// =========================================================
	// HTTP mode: audio chat completions
	// =========================================================

	function captureCurrentFrame(): string | null {
		if (!camera || !cameraStream) return null;
		const video = document.getElementById('rt-camera-feed') as HTMLVideoElement;
		const canvas = document.getElementById('rt-camera-canvas') as HTMLCanvasElement;
		if (!video || !canvas) return null;
		const ctx = canvas.getContext('2d');
		if (!ctx || !video.videoWidth) return null;
		const scale = Math.min(512 / video.videoWidth, 512 / video.videoHeight, 1);
		canvas.width = Math.floor(video.videoWidth * scale);
		canvas.height = Math.floor(video.videoHeight * scale);
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
		return canvas.toDataURL('image/jpeg', 0.6).split(',')[1]; // base64 only
	}

	async function sendAudioHttp(audioBlob: Blob) {
		// Cancel any previous in-flight request (barge-in)
		if (abortController) {
			abortController.abort();
			// Save whatever partial text we had from interrupted response
			if (partialAssistantText) {
				history = [...history, { role: 'assistant', content: partialAssistantText }];
				partialAssistantText = '';
			}
		}
		abortController = new AbortController();
		isSending = true;
		if (BARGE_IN_ENABLED) stopPlayback();
		status = 'thinking';

		const fd = new FormData();
		fd.append('audio', audioBlob, 'recording.wav');
		// Build context: prepend compressed summary if available, then recent history
		const contextHistory = compressedSummary
			? [{ role: 'system', content: `Conversation summary so far: ${compressedSummary}` }, ...history]
			: history;
		fd.append('history', JSON.stringify(contextHistory.slice(-(MAX_HISTORY_TURNS * 2 + (compressedSummary ? 1 : 0)))));

		// Attach camera frame only if camera is active
		if (camera) {
			const frame = captureCurrentFrame();
			if (frame) fd.append('image_b64', frame);
		}

		try {
			const res = await fetch(`${WEBUI_API_BASE_URL}/realtime/audio`, {
				method: 'POST',
				headers: { Authorization: `Bearer ${localStorage.token}` },
				body: fd,
				signal: abortController.signal
			});

			if (!res.ok) {
				const err = await res.text();
				throw new Error(err);
			}

			const contentType = res.headers.get('content-type') || '';

			if (contentType.includes('text/event-stream')) {
				// Progressive SSE: enqueue audio chunks as they arrive
				const reader = res.body!.getReader();
				const decoder = new TextDecoder();
				let buf = '';
				let transcriptText = '';
				let textText = '';
				let userText = '';
				let streamDone = false;

				while (!streamDone) {
					const { done, value } = await reader.read();
					if (done) break;
					buf += decoder.decode(value, { stream: true });
					const lines = buf.split('\n');
					buf = lines.pop()!;

					for (const line of lines) {
						if (!line.startsWith('data: ')) continue;
						let event: any;
						try { event = JSON.parse(line.slice(6)); } catch { continue; }

						if (event.type === 'audio') {
							if (status === 'thinking') status = 'speaking';
							enqueueAudio(event.data);
						} else if (event.type === 'transcript') {
							transcriptText += event.text;
							partialAssistantText = textText || transcriptText;
						} else if (event.type === 'text') {
							textText += event.text;
							partialAssistantText = textText || transcriptText;
						} else if (event.type === 'user_text') {
							userText += event.text;
						} else if (event.type === 'done') {
							streamDone = true;
							break;
						} else if (event.type === 'error') {
							throw new Error(event.detail || 'Stream error');
						}
					}
				}

				const finalText = textText || transcriptText;
				if (finalText) {
					transcript = finalText;
					const newEntries: { role: string; content: string }[] = [];
					if (userText) newEntries.push({ role: 'user', content: userText });
					newEntries.push({ role: 'assistant', content: finalText });
					history = [...history, ...newEntries];
					compressHistory();
				}
				partialAssistantText = '';

				// If no audio is playing/queued, go back to listening
				if (!isPlaying && playbackQueue.length === 0) {
					status = 'listening';
				}
			} else {
				// Non-streaming JSON response (OpenAI direct)
				const data = await res.json();
				partialAssistantText = data.text || '';

				if (data.text) {
					transcript = data.text;
					const newEntries: { role: string; content: string }[] = [];
					if (data.user_text) newEntries.push({ role: 'user', content: data.user_text });
					newEntries.push({ role: 'assistant', content: data.text });
					history = [...history, ...newEntries];
					compressHistory();
				}
				partialAssistantText = '';

				if (data.audio_base64) {
					status = 'speaking';
					await playAudioBlob(data.audio_base64, data.audio_format || 'wav');
				}
				status = 'listening';
			}
		} catch (e: any) {
			if (e?.name === 'AbortError') { status = 'listening'; return; }
			console.error('Audio chat error:', e);
			toast.error(`${e}`);
			status = 'listening';
		} finally {
			isSending = false;
		}
	}

	// =========================================================
	// Microphone capture with VAD (silence detection)
	// =========================================================

	const calculateRMS = (data: Uint8Array) => {
		let s = 0;
		for (let i = 0; i < data.length; i++) {
			const v = (data[i] - 128) / 128;
			s += v * v;
		}
		return Math.sqrt(s / data.length);
	};

	async function startRecording() {
		if (!$showCallOverlay) return;
		if (!audioStream) {
			audioStream = await navigator.mediaDevices.getUserMedia({
				audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
			});
		}

		audioChunks = [];
		hasStartedSpeaking = false;
		confirmed = false;

		// Set up analyser for RMS + VAD
		if (!audioContext || audioContext.state === 'closed') {
			audioContext = new AudioContext();
		}
		const src = audioContext.createMediaStreamSource(audioStream);
		analyser = audioContext.createAnalyser();
		analyser.minDecibels = MIN_DECIBELS;
		analyser.maxDecibels = -30;
		src.connect(analyser);

		mediaRecorder = new MediaRecorder(audioStream);
		mediaRecorder.ondataavailable = (e) => {
			if (hasStartedSpeaking && e.data.size > 0) audioChunks.push(e.data);
		};
		mediaRecorder.onstop = onRecordingStop;

		detectVoice();
	}

	function detectVoice() {
		if (!analyser || !$showCallOverlay) return;
		const domainData = new Uint8Array(analyser.frequencyBinCount);
		const timeDomainData = new Uint8Array(analyser.fftSize);
		let lastSoundTime = Date.now();

		const tick = () => {
			if (!mediaRecorder || !$showCallOverlay) return;

			analyser!.getByteTimeDomainData(timeDomainData);
			analyser!.getByteFrequencyData(domainData);
			rmsLevel = calculateRMS(timeDomainData);

			// While AI is thinking/speaking and barge-in is disabled, don't listen
			if (!BARGE_IN_ENABLED && (status === 'speaking' || status === 'thinking')) {
				requestAnimationFrame(tick);
				return;
			}

			const hasSound = domainData.some((v) => v > VOICE_FREQ_THRESHOLD);
			if (hasSound) {
				if (mediaRecorder!.state !== 'recording') {
					mediaRecorder!.start(100);
				}
				if (!hasStartedSpeaking) {
					hasStartedSpeaking = true;
					status = 'recording';
					if (BARGE_IN_ENABLED) {
						stopPlayback();
						if (abortController && isSending) {
							if (partialAssistantText) {
								history = [...history, { role: 'assistant', content: partialAssistantText }];
								partialAssistantText = '';
							}
							abortController.abort();
							isSending = false;
						}
					}
				}
				lastSoundTime = Date.now();
			}

			if (hasStartedSpeaking && Date.now() - lastSoundTime > 700) {
				confirmed = true;
				if (mediaRecorder!.state === 'recording') {
					mediaRecorder!.stop();
					return;
				}
			}

			requestAnimationFrame(tick);
		};

		requestAnimationFrame(tick);
	}

	// Encode AudioBuffer to 16-bit PCM WAV Blob
	function encodeWav(audioBuffer: AudioBuffer): Blob {
		const numChannels = 1;
		const sampleRate = audioBuffer.sampleRate;
		const samples = audioBuffer.getChannelData(0);
		const numSamples = samples.length;
		const byteLength = 44 + numSamples * 2;
		const buffer = new ArrayBuffer(byteLength);
		const view = new DataView(buffer);
		const writeStr = (off: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
		writeStr(0, 'RIFF');
		view.setUint32(4, byteLength - 8, true);
		writeStr(8, 'WAVE');
		writeStr(12, 'fmt ');
		view.setUint32(16, 16, true);
		view.setUint16(20, 1, true);
		view.setUint16(22, numChannels, true);
		view.setUint32(24, sampleRate, true);
		view.setUint32(28, sampleRate * numChannels * 2, true);
		view.setUint16(32, numChannels * 2, true);
		view.setUint16(34, 16, true);
		writeStr(36, 'data');
		view.setUint32(40, numSamples * 2, true);
		for (let i = 0; i < numSamples; i++) {
			view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 32767, true);
		}
		return new Blob([buffer], { type: 'audio/wav' });
	}

	async function chunksToWav(chunks: Blob[]): Promise<Blob> {
		const webmBlob = new Blob(chunks);
		const arrayBuffer = await webmBlob.arrayBuffer();
		const ctx = new AudioContext();
		try {
			const decoded = await ctx.decodeAudioData(arrayBuffer);
			// Downmix to mono
			const offlineCtx = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
			const src = offlineCtx.createBufferSource();
			src.buffer = decoded;
			src.connect(offlineCtx.destination);
			src.start(0);
			const rendered = await offlineCtx.startRendering();
			return encodeWav(rendered);
		} finally {
			ctx.close();
		}
	}

	async function onRecordingStop() {
		if (!$showCallOverlay) return;

		const chunks = audioChunks.slice();
		audioChunks = [];

		if (confirmed && chunks.length > 0) {
			const wavBlob = await chunksToWav(chunks);
			// Restart VAD immediately — don't wait for API response
			if ($showCallOverlay) startRecording();
			// With barge-in: allow interrupting AI while speaking
			// Without barge-in: only send after AI has finished responding
			if (BARGE_IN_ENABLED ? (!isSending || status === 'speaking') : !isSending) {
				sendAudioHttp(wavBlob);
			}
		} else {
			if ($showCallOverlay) startRecording();
		}
	}

	function stopMicrophone() {
		try { mediaRecorder?.stop(); } catch {}
		mediaRecorder = null;
		if (audioStream) {
			audioStream.getTracks().forEach((t) => t.stop());
			audioStream = null;
		}
		if (audioContext) {
			audioContext.close();
			audioContext = null;
		}
		analyser = null;
	}

	// =========================================================
	// WebSocket mode (OpenAI Realtime direct)
	// =========================================================

	function connectWs() {
		status = 'connecting';
		const base = WEBUI_BASE_URL || window.location.origin;
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const host = base.replace(/^https?:\/\//, '');
		const url = `${protocol}//${host}/api/v1/realtime?token=${localStorage.token}`;

		ws = new WebSocket(url);
		ws.onopen = () => {
			ws!.send(JSON.stringify({
				type: 'session.update',
				session: {
					modalities: ['text', 'audio'],
					voice: getVoice(),
					input_audio_format: 'pcm16',
					output_audio_format: 'pcm16',
					input_audio_transcription: { model: 'gpt-4o-mini-transcribe' },
					turn_detection: { type: 'server_vad', threshold: 0.5, silence_duration_ms: 500 }
				}
			}));
			startWsAudioCapture();
		};
		ws.onmessage = (e) => handleWsEvent(JSON.parse(e.data));
		ws.onerror = () => { status = 'error'; statusMessage = 'Connection error'; };
		ws.onclose = () => { stopWsAudioCapture(); };
	}

	// WS audio capture (AudioWorklet)
	let wsAudioCtx: AudioContext | null = null;
	let wsWorklet: AudioWorkletNode | null = null;
	let wsAudioStream: MediaStream | null = null;

	async function startWsAudioCapture() {
		wsAudioStream = await navigator.mediaDevices.getUserMedia({
			audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
		});
		wsAudioCtx = new AudioContext({ sampleRate: 24000 });
		await wsAudioCtx.audioWorklet.addModule('/audio/realtime-capture-processor.js');
		const src = wsAudioCtx.createMediaStreamSource(wsAudioStream);
		analyser = wsAudioCtx.createAnalyser();
		analyser.fftSize = 256;
		src.connect(analyser);
		wsWorklet = new AudioWorkletNode(wsAudioCtx, 'realtime-capture-processor');
		wsWorklet.port.onmessage = (e) => {
			if (e.data.type === 'audio' && ws?.readyState === WebSocket.OPEN) {
				ws.send(JSON.stringify({
					type: 'input_audio_buffer.append',
					audio: arrayBufferToBase64(new Uint8Array(e.data.samples))
				}));
			}
		};
		src.connect(wsWorklet);
		wsWorklet.connect(wsAudioCtx.destination);
		status = 'listening';
		monitorRms();
	}

	function stopWsAudioCapture() {
		wsWorklet?.disconnect();
		wsWorklet = null;
		wsAudioCtx?.close();
		wsAudioCtx = null;
		wsAudioStream?.getTracks().forEach((t) => t.stop());
		wsAudioStream = null;
	}

	function monitorRms() {
		if (!analyser) return;
		const data = new Uint8Array(analyser.fftSize);
		const loop = () => {
			if (!analyser || !$showCallOverlay) return;
			analyser.getByteTimeDomainData(data);
			rmsLevel = calculateRMS(data);
			requestAnimationFrame(loop);
		};
		requestAnimationFrame(loop);
	}

	function handleWsEvent(event: any) {
		switch (event.type) {
			case 'session.created':
			case 'session.updated':
				status = 'listening';
				break;
			case 'input_audio_buffer.speech_started':
				stopPlayback();
				ws?.send(JSON.stringify({ type: 'response.cancel' }));
				status = 'recording';
				break;
			case 'input_audio_buffer.speech_stopped':
				status = 'thinking';
				break;
			case 'response.audio.delta':
				status = 'speaking';
				if (event.delta) enqueueAudio(event.delta);
				break;
			case 'response.audio_transcript.delta':
				if (event.delta) transcript += event.delta;
				break;
			case 'response.done':
				if (!isPlaying) status = 'listening';
				break;
			case 'error':
				status = 'error';
				statusMessage = event.error?.message || 'Unknown error';
				break;
		}
	}

	// =========================================================
	// Camera
	// =========================================================

	async function getVideoInputDevices() {
		const devs = await navigator.mediaDevices.enumerateDevices();
		videoInputDevices = devs.filter((d) => d.kind === 'videoinput') as MediaDeviceInfo[];
		if (navigator.mediaDevices.getDisplayMedia) {
			videoInputDevices = [...videoInputDevices, { deviceId: 'screen', label: 'Screen Share' } as any];
		}
		if (!selectedVideoInputDeviceId && videoInputDevices.length > 0) {
			selectedVideoInputDeviceId = videoInputDevices[0].deviceId;
		}
	}

	async function startCamera() {
		await getVideoInputDevices();
		camera = true;
		await startVideoStream();
		cameraIntervalId = setInterval(sendCameraFrame, CAMERA_INTERVAL_SECS * 1000);
	}

	async function startVideoStream() {
		const video = document.getElementById('rt-camera-feed') as HTMLVideoElement;
		if (!video) return;
		if (selectedVideoInputDeviceId === 'screen') {
			cameraStream = await navigator.mediaDevices.getDisplayMedia({ video: { cursor: 'always' } as any, audio: false });
		} else {
			cameraStream = await navigator.mediaDevices.getUserMedia({
				video: { deviceId: selectedVideoInputDeviceId ? { exact: selectedVideoInputDeviceId } : undefined }
			});
		}
		if (cameraStream) {
			await getVideoInputDevices();
			video.srcObject = cameraStream;
			await video.play();
		}
	}

	function stopVideoStream() {
		cameraStream?.getTracks().forEach((t) => t.stop());
		cameraStream = null;
	}

	function stopCamera() {
		if (cameraIntervalId) { clearInterval(cameraIntervalId); cameraIntervalId = null; }
		stopVideoStream();
		camera = false;
	}

	function sendCameraFrame() {
		// For HTTP mode: attach as next user message (simplified — skip for now)
		// For WS mode: inject as conversation item
		if (!ws || ws.readyState !== WebSocket.OPEN || !cameraStream) return;
		const video = document.getElementById('rt-camera-feed') as HTMLVideoElement;
		const canvas = document.getElementById('rt-camera-canvas') as HTMLCanvasElement;
		if (!video || !canvas) return;
		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		const scale = Math.min(512 / video.videoWidth, 512 / video.videoHeight, 1);
		canvas.width = Math.floor(video.videoWidth * scale);
		canvas.height = Math.floor(video.videoHeight * scale);
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
		const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
		ws.send(JSON.stringify({
			type: 'conversation.item.create',
			item: { type: 'message', role: 'user', content: [{ type: 'input_image', image_url: dataUrl }] }
		}));
	}

	// =========================================================
	// Lifecycle
	// =========================================================

	async function init() {
		// Load realtime config from admin settings
		try {
			const res = await fetch(`${WEBUI_API_BASE_URL}/audio/config`, {
				headers: { Authorization: `Bearer ${localStorage.token}` }
			});
			if (res.ok) {
				const cfg = await res.json();
				realtimeApiUrl = cfg?.realtime?.API_BASE_URL ?? '';
				useWebSocket = realtimeApiUrl.startsWith('wss://');
				// Admin config enables it, but user's voiceInterruption setting controls it
				BARGE_IN_ENABLED = (cfg?.realtime?.BARGE_IN_ENABLED ?? false) && ($settings?.voiceInterruption ?? false);
				BARGE_IN_RMS_THRESHOLD = cfg?.realtime?.BARGE_IN_THRESHOLD ?? 0.06;
				VOICE_FREQ_THRESHOLD = cfg?.realtime?.VOICE_THRESHOLD ?? 12;
				MAX_HISTORY_TURNS = cfg?.realtime?.MAX_HISTORY_TURNS ?? 8;
				CAMERA_INTERVAL_SECS = cfg?.realtime?.CAMERA_INTERVAL ?? 2;
			}
		} catch {}

		model = $models.find((m) => m.id === modelId);
		if ('wakeLock' in navigator) {
			try { wakeLock = await navigator.wakeLock.request('screen'); } catch {}
		}

		if (useWebSocket) {
			connectWs();
		} else {
			status = 'listening';
			await startRecording();
		}
	}

	function handleInterrupt() {
		// Save partial transcript so next request has full context
		if (partialAssistantText) {
			history = [...history, { role: 'assistant', content: partialAssistantText }];
			partialAssistantText = '';
		}
		// Abort in-flight HTTP request
		if (abortController) {
			abortController.abort();
			abortController = null;
			isSending = false;
		}
		// Cancel WS response
		if (ws?.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({ type: 'response.cancel' }));
		}
		stopPlayback();
		status = 'listening';
	}

	async function cleanup() {
		abortController?.abort();
		abortController = null;
		isSending = false;
		stopPlayback();
		stopMicrophone();
		stopCamera();
		if (ws) {
			if (ws.readyState === WebSocket.OPEN) {
				ws.send(JSON.stringify({ type: 'response.cancel' }));
			}
			ws.close();
			ws = null;
		}
		stopWsAudioCapture();
		if (playbackContext) { playbackContext.close(); playbackContext = null; }
		if (wakeLock) { wakeLock.release(); wakeLock = null; }
	}

	onMount(init);
	onDestroy(cleanup);
</script>

{#if $showCallOverlay}
	<div class="max-w-lg w-full h-full max-h-[100dvh] flex flex-col justify-between p-3 md:p-6">

		<!-- Top: camera thumbnail or spacer -->
		{#if camera}
			<button
				type="button"
				class="flex justify-center items-center w-full h-20 min-h-20"
				on:click={() => { if (status === 'speaking') handleInterrupt(); }}
			>
				<div class="{rmsLevel * 100 > 2 ? 'size-16' : 'size-12'} transition-all rounded-full bg-cover bg-center bg-no-repeat"
					style={`background-image: url('${WEBUI_API_BASE_URL}/models/model/profile/image?id=${model?.id}&lang=${$i18n.language}&voice=true');`}
				/>
			</button>
		{/if}

		<!-- Center: avatar / video / animation -->
		<div class="flex justify-center items-center flex-1 h-full w-full max-h-full">
			{#if !camera}
				<button
					type="button"
					on:click={() => { if (status === 'speaking') handleInterrupt(); }}
				>
					{#if status === 'connecting' || status === 'thinking'}
						<svg class="size-44 text-gray-900 dark:text-gray-400" viewBox="0 0 24 24" fill="currentColor">
							<style>
								.rt_dot { animation: rt_b 1.05s infinite; }
								.rt_d2 { animation-delay:.1s; }
								.rt_d3 { animation-delay:.2s; }
								@keyframes rt_b {
									0%,57.14%{animation-timing-function:cubic-bezier(.33,.66,.66,1);transform:translate(0);}
									28.57%{animation-timing-function:cubic-bezier(.33,0,.66,.33);transform:translateY(-6px);}
									100%{transform:translate(0);}
								}
							</style>
							<circle class="rt_dot" cx="4" cy="12" r="3"/>
							<circle class="rt_dot rt_d2" cx="12" cy="12" r="3"/>
							<circle class="rt_dot rt_d3" cx="20" cy="12" r="3"/>
						</svg>
					{:else}
						<div
							class="{rmsLevel * 100 > 4 ? 'size-52' : rmsLevel * 100 > 2 ? 'size-48' : rmsLevel * 100 > 1 ? 'size-44' : 'size-40'} transition-all rounded-full bg-cover bg-center bg-no-repeat"
							style={`background-image: url('${WEBUI_API_BASE_URL}/models/model/profile/image?id=${model?.id}&lang=${$i18n.language}&voice=true');`}
						/>
					{/if}
				</button>
			{:else}
				<div class="relative flex video-container w-full max-h-full pt-2 pb-4 md:py-6 px-2 h-full">
					<!-- svelte-ignore a11y-media-has-caption -->
					<video id="rt-camera-feed" autoplay class="rounded-2xl h-full min-w-full object-cover object-center" playsinline />
					<canvas id="rt-camera-canvas" style="display:none;" />
					<div class="absolute top-4 md:top-8 left-4">
						<button type="button" class="p-1.5 text-white cursor-pointer backdrop-blur-xl bg-black/10 rounded-full" on:click={stopCamera}>
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-6">
								<path d="M5.28 4.22a.75.75 0 0 0-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 1 0 1.06 1.06L8 9.06l2.72 2.72a.75.75 0 1 0 1.06-1.06L9.06 8l2.72-2.72a.75.75 0 0 0-1.06-1.06L8 6.94 5.28 4.22Z"/>
							</svg>
						</button>
					</div>
				</div>
			{/if}
		</div>

		<!-- Transcript -->
		{#if transcript}
			<div class="text-center text-sm text-gray-500 dark:text-gray-400 max-h-16 overflow-y-auto px-4 mb-2 line-clamp-3">
				{transcript}
			</div>
		{/if}

		<!-- Bottom bar -->
		<div class="flex justify-between items-center pb-2 w-full">
			<!-- Camera button -->
			<div>
				{#if camera}
					<VideoInputMenu devices={videoInputDevices} on:change={async (e) => { selectedVideoInputDeviceId = e.detail; stopVideoStream(); await startVideoStream(); }}>
						<button class="p-3 rounded-full bg-gray-50 dark:bg-gray-900" type="button">
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-5">
								<path fill-rule="evenodd" d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z" clip-rule="evenodd"/>
							</svg>
						</button>
					</VideoInputMenu>
				{:else}
					<Tooltip content={$i18n.t('Camera')}>
						<button class="p-3 rounded-full bg-gray-50 dark:bg-gray-900" type="button" on:click={async () => { await navigator.mediaDevices.getUserMedia({ video: true }); startCamera(); }}>
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z"/>
								<path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z"/>
							</svg>
						</button>
					</Tooltip>
				{/if}
			</div>

			<!-- Status label -->
			<div>
				<button type="button" on:click={() => { if (status === 'speaking') handleInterrupt(); }}>
					<div class="line-clamp-1 text-sm font-medium">
						{#if status === 'connecting'}
							{$i18n.t('Connecting...')}
						{:else if status === 'thinking'}
							{$i18n.t('Thinking...')}
						{:else if status === 'speaking'}
							{$i18n.t('Tap to interrupt')}
						{:else if status === 'recording'}
							{$i18n.t('Listening...')}
						{:else if status === 'error'}
							{statusMessage || $i18n.t('Error')}
						{:else}
							{$i18n.t('Listening...')}
						{/if}
					</div>
				</button>
			</div>

			<!-- Close button -->
			<div>
				<button class="p-3 rounded-full bg-gray-50 dark:bg-gray-900" type="button"
					on:click={async () => { await cleanup(); showCallOverlay.set(false); dispatch('close'); }}
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-5">
						<path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z"/>
					</svg>
				</button>
			</div>
		</div>
	</div>
{/if}
