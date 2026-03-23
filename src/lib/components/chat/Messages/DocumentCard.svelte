<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import {
		showDocxPreview,
		showControls,
		docxPreviewContent
	} from '$lib/stores';
	import { downloadChatAsDocx } from '$lib/apis/utils';
	import { uploadToGoogleDrive } from '$lib/utils/google-drive-picker';

	const i18n = getContext('i18n');

	export let title: string = 'Document';
	export let content: string = '';
	export let role: string = 'assistant';
	export let files: any[] = [];
	export let codeExecutions: any[] = [];

	let downloading = false;
	let exporting = false;

	const openPreview = () => {
		docxPreviewContent.set({ role, content, title });
		showDocxPreview.set(true);
		showControls.set(true);
	};

	const handleDownload = async (e: MouseEvent) => {
		e.stopPropagation();
		if (downloading) return;
		downloading = true;
		try {
			const blob = await downloadChatAsDocx(localStorage.token, title, [
				{ role, content, files, code_executions: codeExecutions }
			]);
			if (blob) {
				saveAs(blob, `${title}.docx`);
			}
		} catch (err) {
			console.error('Failed to download DOCX:', err);
			toast.error('Failed to download document');
		} finally {
			downloading = false;
		}
	};

	const handleGoogleDocs = async (e: MouseEvent) => {
		e.stopPropagation();
		if (exporting) return;
		exporting = true;
		try {
			const blob = await downloadChatAsDocx(localStorage.token, title, [
				{ role, content, files, code_executions: codeExecutions }
			]);
			if (blob) {
				const url = await uploadToGoogleDrive(blob, `${title}.docx`, true);
				if (url) {
					window.open(url, '_blank');
				}
			}
		} catch (err) {
			console.error('Failed to export to Google Docs:', err);
			toast.error('Failed to export to Google Docs');
		} finally {
			exporting = false;
		}
	};
</script>

<button
	class="w-full max-w-lg flex items-center gap-3 p-3 rounded-2xl bg-white dark:bg-gray-850 border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition cursor-pointer text-left group"
	type="button"
	on:click={openPreview}
>
	<!-- Document icon -->
	<div
		class="size-11 shrink-0 flex justify-center items-center bg-black/20 dark:bg-white/10 text-white rounded-xl"
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="currentColor"
			aria-hidden="true"
			class="size-5"
		>
			<path
				fill-rule="evenodd"
				d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0 0 16.5 9h-1.875a1.875 1.875 0 0 1-1.875-1.875V5.25A3.75 3.75 0 0 0 9 1.5H5.625ZM7.5 15a.75.75 0 0 1 .75-.75h7.5a.75.75 0 0 1 0 1.5h-7.5A.75.75 0 0 1 7.5 15Zm.75 2.25a.75.75 0 0 0 0 1.5H12a.75.75 0 0 0 0-1.5H8.25Z"
				clip-rule="evenodd"
			/>
			<path
				d="M12.971 1.816A5.23 5.23 0 0 1 14.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 0 1 3.434 1.279 9.768 9.768 0 0 0-6.963-6.963Z"
			/>
		</svg>
	</div>

	<!-- Title and subtitle -->
	<div class="flex flex-col justify-center min-w-0 flex-1">
		<div class="dark:text-gray-100 text-sm font-medium line-clamp-1">
			{title}
		</div>
		<div class="text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('Document')} · DOCX
		</div>
	</div>

	<!-- Action buttons -->
	<div class="flex items-center gap-2 shrink-0">
		<!-- Google Drive button -->
		<button
			type="button"
			class="size-9 flex items-center justify-center rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition"
			title={$i18n.t('Google Docs')}
			disabled={exporting}
			on:click={handleGoogleDocs}
		>
			{#if exporting}
				<svg class="size-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
				</svg>
			{:else}
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 87.3 78" class="size-5">
					<path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H0c0 1.55.4 3.1 1.2 4.5z" fill="#0066da" />
					<path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0-1.2 4.5h27.5z" fill="#00ac47" />
					<path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5H59.8l5.95 10.3z" fill="#ea4335" />
					<path d="M43.65 25 57.4 1.2C56.05.4 54.5 0 52.9 0H34.4c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d" />
					<path d="M59.8 53H27.5L13.75 76.8c1.35.8 2.9 1.2 4.5 1.2h36.85c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc" />
					<path d="M73.4 26.5 60.65 4.5c-.8-1.4-1.95-2.5-3.3-3.3L43.6 25l16.2 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00" />
				</svg>
			{/if}
		</button>

		<!-- Download button -->
		<button
			type="button"
			class="px-4 py-2 text-sm font-medium rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 dark:text-gray-100 transition"
			disabled={downloading}
			on:click={handleDownload}
		>
			{#if downloading}
				{$i18n.t('Downloading...')}
			{:else}
				{$i18n.t('Download')}
			{/if}
		</button>
	</div>
</button>
