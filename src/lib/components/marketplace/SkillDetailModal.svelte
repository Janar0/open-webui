<script lang="ts">
	import { getContext } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Badge from '$lib/components/common/Badge.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let skill: any = null;
	export let preview: string = '';
	export let installed: boolean = false;
	export let installing: boolean = false;
	export let onInstall: () => void = () => {};
	export let onUninstall: () => void = () => {};
</script>

<Modal bind:show size="md">
	{#if skill}
		<div class="p-5 max-h-[70vh] overflow-y-auto">
			<div class="flex items-start justify-between gap-3 mb-4">
				<div class="flex items-center gap-3">
					{#if skill.emoji}
						<span class="text-3xl">{skill.emoji}</span>
					{/if}
					<div>
						<h2 class="text-lg font-semibold">{skill.name || skill.slug || ''}</h2>
						<div class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
							{#if skill.owner || skill.author}
								<span>{skill.owner || skill.author}</span>
							{/if}
							{#if skill.version}
								<span>v{skill.version}</span>
							{/if}
						</div>
					</div>
				</div>

				<div>
					{#if installed}
						<button
							class="px-4 py-1.5 text-sm text-red-500 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition"
							on:click={() => {
								onUninstall();
								show = false;
							}}
						>
							{$i18n.t('Uninstall')}
						</button>
					{:else}
						<button
							class="px-4 py-1.5 text-sm bg-black dark:bg-white text-white dark:text-black rounded-lg hover:opacity-80 transition disabled:opacity-50"
							disabled={installing}
							on:click={() => {
								onInstall();
							}}
						>
							{installing ? $i18n.t('Installing...') : $i18n.t('Install')}
						</button>
					{/if}
				</div>
			</div>

			{#if skill.description}
				<p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{skill.description}</p>
			{/if}

			{#if skill.tags && skill.tags.length > 0}
				<div class="flex flex-wrap gap-1.5 mb-4">
					{#each skill.tags as tag}
						<Badge type="muted" content={tag} />
					{/each}
				</div>
			{/if}

			{#if skill.requires_bins && skill.requires_bins.length > 0}
				<div class="mb-4 p-3 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 rounded-lg">
					<p class="text-sm font-medium text-amber-800 dark:text-amber-200 mb-1">
						{$i18n.t('Sandbox Required')}
					</p>
					<p class="text-xs text-amber-700 dark:text-amber-300 mb-1.5">
						{$i18n.t(
							'This skill requires CLI tools that are not available in the current environment. ' +
								'The instructions will be injected into the LLM prompt, but execution of commands is limited.'
						)}
					</p>
					<div class="flex flex-wrap gap-1.5">
						{#each skill.requires_bins as bin}
							<code class="text-xs px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded"
								>{bin}</code
							>
						{/each}
					</div>
				</div>
			{/if}

			{#if skill.requires_env && skill.requires_env.length > 0}
				<div class="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800 rounded-lg">
					<p class="text-sm font-medium text-yellow-800 dark:text-yellow-200 mb-1">
						{$i18n.t('Required Credentials')}
					</p>
					<div class="flex flex-wrap gap-1.5">
						{#each skill.requires_env as env}
							<code class="text-xs px-1.5 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 rounded"
								>{env}</code
							>
						{/each}
					</div>
				</div>
			{/if}

			{#if skill.homepage}
				<div class="mb-4">
					<a
						href={skill.homepage}
						target="_blank"
						rel="noopener noreferrer"
						class="text-sm text-blue-500 hover:underline"
					>
						{skill.homepage}
					</a>
				</div>
			{/if}

			{#if preview}
				<div class="mt-4 border-t border-gray-100 dark:border-gray-800 pt-4">
					<h3 class="text-sm font-medium mb-2">{$i18n.t('SKILL.md Preview')}</h3>
					<pre
						class="text-xs bg-gray-50 dark:bg-gray-900 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">{preview}</pre>
				</div>
			{/if}
		</div>
	{/if}
</Modal>
