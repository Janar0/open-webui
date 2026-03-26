<script lang="ts">
	import { getContext } from 'svelte';
	import Badge from '$lib/components/common/Badge.svelte';

	const i18n = getContext('i18n');

	export let skill: any;
	export let installed: boolean = false;
	export let installing: boolean = false;
	export let hasUpdate: boolean = false;
	export let onInstall: () => void = () => {};
	export let onUninstall: () => void = () => {};
	export let onConfigure: () => void = () => {};
	export let onUpdate: () => void = () => {};
	export let onDetail: () => void = () => {};
</script>

<button
	class="flex flex-col justify-between w-full text-left border border-gray-100 dark:border-gray-850 rounded-xl p-4 hover:bg-gray-50 dark:hover:bg-gray-850 transition cursor-pointer"
	on:click={onDetail}
>
	<div class="w-full">
		<div class="flex items-start justify-between gap-2">
			<div class="flex items-center gap-2 min-w-0">
				{#if skill.emoji}
					<span class="text-xl flex-shrink-0">{skill.emoji}</span>
				{/if}
				<h3 class="font-medium text-sm truncate">{skill.name || skill.slug || ''}</h3>
			</div>

			<div class="flex-shrink-0">
				{#if installed}
					<div class="flex items-center gap-1">
						{#if hasUpdate}
							<button
								class="text-xs px-2 py-0.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-500/20 transition"
								on:click|stopPropagation={onUpdate}
							>
								{$i18n.t('Update')}
							</button>
						{/if}
						<button
							class="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition"
							on:click|stopPropagation={onConfigure}
						>
							{$i18n.t('Configure')}
						</button>
						<button
							class="text-xs px-2 py-0.5 text-red-500 hover:bg-red-500/10 rounded-lg transition"
							on:click|stopPropagation={onUninstall}
						>
							{$i18n.t('Uninstall')}
						</button>
					</div>
				{:else}
					<button
						class="text-xs px-3 py-1 bg-black dark:bg-white text-white dark:text-black rounded-lg hover:opacity-80 transition disabled:opacity-50"
						disabled={installing}
						on:click|stopPropagation={onInstall}
					>
						{#if installing}
							{$i18n.t('Installing...')}
						{:else}
							{$i18n.t('Install')}
						{/if}
					</button>
				{/if}
			</div>
		</div>

		{#if skill.description}
			<p class="text-xs text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-2">
				{skill.description}
			</p>
		{/if}
	</div>

	<div class="flex items-center gap-2 mt-3 text-xs text-gray-400 dark:text-gray-500">
		{#if skill.owner || skill.author}
			<span>{skill.owner || skill.author}</span>
		{/if}
		{#if skill.version}
			<span>v{skill.version}</span>
		{/if}
		{#if skill.requires_bins && skill.requires_bins.length > 0}
			<span
				class="px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded"
				title={$i18n.t('Requires sandbox: {{bins}}', {
					bins: skill.requires_bins.join(', ')
				})}
			>
				{$i18n.t('Sandbox')}
			</span>
		{/if}
		{#if skill.tags && skill.tags.length > 0}
			{#each skill.tags.slice(0, 3) as tag}
				<Badge type="muted" content={tag} />
			{/each}
		{/if}
	</div>
</button>
