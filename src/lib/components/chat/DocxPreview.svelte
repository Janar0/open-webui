<script lang="ts">
	import { onMount, getContext, createEventDispatcher } from 'svelte';
	import { marked } from 'marked';

	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import {
		showDocxPreview,
		showControls,
		docxPreviewContent
	} from '$lib/stores';
	import { downloadChatAsDocx } from '$lib/apis/utils';
	import { uploadToGoogleDrive } from '$lib/utils/google-drive-picker';

	import XMark from '../icons/XMark.svelte';
	import Download from '../icons/Download.svelte';
	import Tooltip from '../common/Tooltip.svelte';

	let downloading = false;
	let exporting = false;

	$: content = $docxPreviewContent;
	$: renderedHtml = content?.content ? marked(content.content) : '';

	const handleDownloadDocx = async () => {
		if (!content || downloading) return;
		downloading = true;
		try {
			const blob = await downloadChatAsDocx(
				localStorage.token,
				content.title || 'Document',
				[{ role: content.role, content: content.content }]
			);
			if (blob) {
				saveAs(blob, `${content.title || 'document'}.docx`);
			}
		} finally {
			downloading = false;
		}
	};

	const handleExportGoogleDocs = async () => {
		if (!content || exporting) return;
		exporting = true;
		try {
			const blob = await downloadChatAsDocx(
				localStorage.token,
				content.title || 'Document',
				[{ role: content.role, content: content.content }]
			);
			if (blob) {
				const url = await uploadToGoogleDrive(blob, `${content.title || 'Document'}.docx`, true);
				if (url) {
					window.open(url, '_blank');
				}
			}
		} catch (err) {
			console.error('Failed to export to Google Docs:', err);
		} finally {
			exporting = false;
		}
	};
</script>

<div class="w-full h-full relative flex flex-col bg-white dark:bg-gray-850" id="docx-preview-container">
	<div class="w-full h-full flex flex-col flex-1 relative">
		<!-- Header toolbar -->
		<div class="pointer-events-auto z-20 flex justify-between items-center p-2.5 font-primary text-gray-900 dark:text-white border-b border-gray-100 dark:border-gray-800">
			<div class="flex-1 flex items-center justify-between pr-1">
				<div class="flex items-center gap-2">
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-4 text-blue-500">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
					</svg>
					<span class="text-sm font-medium">{$i18n.t('Document Preview')}</span>
				</div>

				<div class="flex items-center gap-1.5">
					<Tooltip content={$i18n.t('Download as DOCX')}>
						<button
							class="bg-none border-none text-xs bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 transition rounded-md px-2 py-1 flex items-center gap-1"
							on:click={handleDownloadDocx}
							disabled={downloading}
						>
							<Download className="size-3.5" />
							<span>{downloading ? $i18n.t('Downloading...') : $i18n.t('.docx')}</span>
						</button>
					</Tooltip>

					<Tooltip content={$i18n.t('Export to Google Docs')}>
						<button
							class="bg-none border-none text-xs bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 transition rounded-md px-2 py-1 flex items-center gap-1"
							on:click={handleExportGoogleDocs}
							disabled={exporting}
						>
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="size-3.5" fill="currentColor">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/>
								<path d="M8 12h8v2H8zm0 4h8v2H8zm0-8h2v2H8z"/>
							</svg>
							<span>{exporting ? $i18n.t('Exporting...') : $i18n.t('Google Docs')}</span>
						</button>
					</Tooltip>
				</div>
			</div>

			<button
				class="self-center pointer-events-auto p-1 rounded-full bg-white dark:bg-gray-850 ml-1"
				on:click={() => {
					dispatch('close');
					showControls.set(false);
					showDocxPreview.set(false);
					docxPreviewContent.set(null);
				}}
			>
				<XMark className="size-3.5 text-gray-900 dark:text-white" />
			</button>
		</div>

		<!-- Document preview content -->
		<div class="flex-1 w-full h-full overflow-y-auto">
			{#if content}
				<div class="docx-preview max-w-3xl mx-auto px-8 py-6">
					{#if content.title}
						<h1 class="text-2xl font-bold text-gray-900 dark:text-white mb-4 pb-3 border-b-2 border-blue-500">
							{content.title}
						</h1>
					{/if}

					<div class="flex items-center gap-2 mb-4">
						<span class="text-sm font-semibold px-2 py-0.5 rounded-md {content.role === 'user' ? 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950' : 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-950'}">
							{content.role === 'user' ? $i18n.t('User') : $i18n.t('Assistant')}
						</span>
					</div>

					<div class="prose prose-sm dark:prose-invert max-w-none
						prose-headings:text-gray-900 dark:prose-headings:text-white
						prose-p:text-gray-700 dark:prose-p:text-gray-300
						prose-a:text-blue-600 dark:prose-a:text-blue-400
						prose-code:bg-gray-100 dark:prose-code:bg-gray-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
						prose-pre:bg-gray-50 dark:prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-200 dark:prose-pre:border-gray-700 prose-pre:rounded-lg
						prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:bg-gray-50 dark:prose-blockquote:bg-gray-900 prose-blockquote:pl-4 prose-blockquote:italic
						prose-table:border-collapse
						prose-th:bg-blue-500 prose-th:text-white prose-th:px-3 prose-th:py-2
						prose-td:border prose-td:border-gray-200 dark:prose-td:border-gray-700 prose-td:px-3 prose-td:py-2
						prose-img:rounded-lg prose-img:shadow-md
						prose-strong:text-gray-900 dark:prose-strong:text-white
						prose-ul:list-disc prose-ol:list-decimal
					">
						{@html renderedHtml}
					</div>
				</div>
			{:else}
				<div class="m-auto font-medium text-xs text-gray-500 dark:text-gray-400 flex items-center justify-center h-full">
					{$i18n.t('No document to preview')}
				</div>
			{/if}
		</div>
	</div>
</div>
