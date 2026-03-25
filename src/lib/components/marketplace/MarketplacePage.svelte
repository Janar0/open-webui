<script lang="ts">
	import { onMount, getContext, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';

	import {
		searchCatalog,
		getCatalogSkillPreview,
		installSkill,
		uninstallSkill,
		getInstallations,
		getAuthStatus,
		saveClawHubAuth,
		removeClawHubAuth,
		checkUpdate,
		updateSkillVersion
	} from '$lib/apis/marketplace';
	import { getSkills } from '$lib/apis/skills';

	import SkillCard from './SkillCard.svelte';
	import SkillDetailModal from './SkillDetailModal.svelte';
	import ConfigModal from './ConfigModal.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	// State
	let activeTab: 'browse' | 'installed' | 'settings' = 'browse';
	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	let loading = false;
	let catalogResults: any[] = [];
	let installations: any[] = [];
	let installedSlugs: Set<string> = new Set();
	let installingSlugs: Set<string> = new Set();

	// Detail modal
	let showDetail = false;
	let detailSkill: any = null;
	let detailPreview = '';
	let detailInstalled = false;
	let detailInstalling = false;

	// Config modal
	let showConfig = false;
	let configInstallationId = '';
	let configSkillName = '';

	// Auth
	let authStatus: any = null;
	let authToken = '';
	let authLoading = false;

	onMount(async () => {
		await loadInstallations();
		await loadAuthStatus();
		await searchSkills();
	});

	async function searchSkills() {
		loading = true;
		try {
			const token = localStorage.token;
			const result = await searchCatalog(token, query);
			// ClawHub API may return array or object with items
			if (Array.isArray(result)) {
				catalogResults = result;
			} else if (result?.items) {
				catalogResults = result.items;
			} else if (result?.skills) {
				catalogResults = result.skills;
			} else {
				catalogResults = [];
			}
		} catch (err) {
			console.error('Catalog search error:', err);
			toast.error(`${$i18n.t('Failed to search catalog')}: ${err}`);
			catalogResults = [];
		} finally {
			loading = false;
		}
	}

	function handleSearchInput() {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			searchSkills();
		}, 400);
	}

	async function loadInstallations() {
		try {
			const token = localStorage.token;
			installations = await getInstallations(token);
			installedSlugs = new Set(installations.map((i: any) => i.external_slug));
		} catch (err) {
			console.error('Failed to load installations:', err);
		}
	}

	async function loadAuthStatus() {
		try {
			authStatus = await getAuthStatus(localStorage.token);
		} catch {
			authStatus = { authenticated: false };
		}
	}

	async function handleInstall(skill: any) {
		const slug = skill.slug || skill.id || '';
		if (!slug) return;

		installingSlugs.add(slug);
		installingSlugs = installingSlugs;

		try {
			const token = localStorage.token;
			const result = await installSkill(token, slug);

			toast.success($i18n.t('Skill installed successfully'));

			// If requires env vars, open config modal
			if (result.requires_env && result.requires_env.length > 0) {
				configInstallationId = result.installation_id;
				configSkillName = result.name;
				showConfig = true;
			}

			await loadInstallations();
			showDetail = false;
		} catch (err) {
			toast.error(`${$i18n.t('Failed to install skill')}: ${err}`);
		} finally {
			installingSlugs.delete(slug);
			installingSlugs = installingSlugs;
		}
	}

	async function handleUninstall(installationId: string) {
		try {
			const token = localStorage.token;
			await uninstallSkill(token, installationId);
			toast.success($i18n.t('Skill uninstalled'));
			await loadInstallations();
		} catch (err) {
			toast.error(`${$i18n.t('Failed to uninstall')}: ${err}`);
		}
	}

	async function handleUpdate(installationId: string) {
		try {
			const token = localStorage.token;
			await updateSkillVersion(token, installationId);
			toast.success($i18n.t('Skill updated'));
			await loadInstallations();
		} catch (err) {
			toast.error(`${$i18n.t('Failed to update')}: ${err}`);
		}
	}

	async function openDetail(skill: any) {
		detailSkill = skill;
		detailPreview = '';
		detailInstalled = installedSlugs.has(skill.slug || skill.id || '');
		detailInstalling = false;
		showDetail = true;

		// Load preview
		try {
			const token = localStorage.token;
			const result = await getCatalogSkillPreview(token, skill.slug || skill.id || '');
			detailPreview = result.content || '';
		} catch {
			detailPreview = '';
		}
	}

	function openConfigure(installation: any) {
		configInstallationId = installation.id;
		configSkillName = installation.meta?.name || installation.external_slug || '';
		showConfig = true;
	}

	async function handleSaveAuth() {
		if (!authToken.trim()) return;
		authLoading = true;
		try {
			const result = await saveClawHubAuth(localStorage.token, authToken.trim());
			toast.success($i18n.t('ClawHub account connected'));
			authToken = '';
			await loadAuthStatus();
		} catch (err) {
			toast.error(`${$i18n.t('Failed to connect ClawHub')}: ${err}`);
		} finally {
			authLoading = false;
		}
	}

	async function handleRemoveAuth() {
		try {
			await removeClawHubAuth(localStorage.token);
			toast.success($i18n.t('ClawHub account disconnected'));
			await loadAuthStatus();
		} catch (err) {
			toast.error(`${err}`);
		}
	}

	function getInstallationForSlug(slug: string) {
		return installations.find((i: any) => i.external_slug === slug);
	}
</script>

<div class="flex flex-col h-full">
	<!-- Header -->
	<div class="flex items-center justify-between mb-4">
		<div class="flex gap-1">
			<button
				class="px-3 py-1.5 text-sm rounded-lg transition {activeTab === 'browse'
					? 'bg-gray-100 dark:bg-gray-800 font-medium'
					: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
				on:click={() => (activeTab = 'browse')}
			>
				{$i18n.t('Browse')}
			</button>
			<button
				class="px-3 py-1.5 text-sm rounded-lg transition {activeTab === 'installed'
					? 'bg-gray-100 dark:bg-gray-800 font-medium'
					: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
				on:click={() => {
					activeTab = 'installed';
					loadInstallations();
				}}
			>
				{$i18n.t('Installed')}
				{#if installations.length > 0}
					<span
						class="ml-1 text-xs bg-gray-200 dark:bg-gray-700 px-1.5 py-0.5 rounded-full"
					>
						{installations.length}
					</span>
				{/if}
			</button>
			<button
				class="px-3 py-1.5 text-sm rounded-lg transition {activeTab === 'settings'
					? 'bg-gray-100 dark:bg-gray-800 font-medium'
					: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
				on:click={() => (activeTab = 'settings')}
			>
				{$i18n.t('Settings')}
			</button>
		</div>
	</div>

	<!-- Browse Tab -->
	{#if activeTab === 'browse'}
		<div class="mb-4">
			<div class="relative">
				<div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
					<Search className="w-4 h-4 text-gray-400" />
				</div>
				<input
					type="text"
					class="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-xl bg-transparent focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-600"
					placeholder={$i18n.t('Search ClawHub skills...')}
					bind:value={query}
					on:input={handleSearchInput}
				/>
			</div>
		</div>

		{#if loading}
			<div class="flex justify-center py-12">
				<Spinner />
			</div>
		{:else if catalogResults.length === 0}
			<div class="text-center py-12 text-gray-500 dark:text-gray-400">
				<p class="text-sm">
					{query
						? $i18n.t('No skills found for "{{query}}"', { query })
						: $i18n.t('Search the ClawHub catalog to find skills')}
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
				{#each catalogResults as skill}
					{@const slug = skill.slug || skill.id || ''}
					{@const isInstalled = installedSlugs.has(slug)}
					{@const installation = getInstallationForSlug(slug)}
					<SkillCard
						{skill}
						installed={isInstalled}
						installing={installingSlugs.has(slug)}
						hasUpdate={installation?.latest_version &&
							installation.latest_version !== installation.installed_version}
						onInstall={() => handleInstall(skill)}
						onUninstall={() => installation && handleUninstall(installation.id)}
						onConfigure={() => installation && openConfigure(installation)}
						onUpdate={() => installation && handleUpdate(installation.id)}
						onDetail={() => openDetail(skill)}
					/>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- Installed Tab -->
	{#if activeTab === 'installed'}
		{#if installations.length === 0}
			<div class="text-center py-12 text-gray-500 dark:text-gray-400">
				<p class="text-sm">{$i18n.t('No marketplace skills installed yet.')}</p>
				<button
					class="mt-2 text-sm text-blue-500 hover:underline"
					on:click={() => (activeTab = 'browse')}
				>
					{$i18n.t('Browse the catalog')}
				</button>
			</div>
		{:else}
			<div class="space-y-2">
				{#each installations as installation}
					<div
						class="flex items-center justify-between p-3 border border-gray-100 dark:border-gray-850 rounded-xl"
					>
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								{#if installation.meta?.emoji}
									<span>{installation.meta.emoji}</span>
								{/if}
								<span class="font-medium text-sm truncate">
									{installation.meta?.name || installation.external_slug}
								</span>
								<span class="text-xs text-gray-400">
									v{installation.installed_version}
								</span>
								{#if installation.latest_version && installation.latest_version !== installation.installed_version}
									<span
										class="text-xs px-1.5 py-0.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded"
									>
										{$i18n.t('Update available')}: v{installation.latest_version}
									</span>
								{/if}
							</div>
							<p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
								{installation.external_slug}
								{#if installation.external_owner}
									by {installation.external_owner}
								{/if}
							</p>
						</div>
						<div class="flex items-center gap-1 flex-shrink-0">
							{#if installation.latest_version && installation.latest_version !== installation.installed_version}
								<button
									class="text-xs px-2 py-1 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-500/20 transition"
									on:click={() => handleUpdate(installation.id)}
								>
									{$i18n.t('Update')}
								</button>
							{/if}
							<button
								class="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition"
								on:click={() => openConfigure(installation)}
							>
								{$i18n.t('Configure')}
							</button>
							<button
								class="text-xs px-2 py-1 text-red-500 hover:bg-red-500/10 rounded-lg transition"
								on:click={() => handleUninstall(installation.id)}
							>
								{$i18n.t('Uninstall')}
							</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- Settings Tab -->
	{#if activeTab === 'settings'}
		<div class="max-w-lg">
			<h3 class="text-sm font-medium mb-3">{$i18n.t('ClawHub Account')}</h3>
			<p class="text-xs text-gray-500 dark:text-gray-400 mb-4">
				{$i18n.t(
					'Connect your ClawHub account for higher API rate limits and access to private skills.'
				)}
			</p>

			{#if authStatus?.authenticated}
				<div
					class="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg"
				>
					<div>
						<p class="text-sm font-medium">{$i18n.t('Connected')}</p>
						{#if authStatus.username}
							<p class="text-xs text-gray-500">{authStatus.username}</p>
						{/if}
						{#if authStatus.token_prefix}
							<p class="text-xs text-gray-400 font-mono">{authStatus.token_prefix}</p>
						{/if}
					</div>
					<button
						class="text-xs px-3 py-1.5 text-red-500 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition"
						on:click={handleRemoveAuth}
					>
						{$i18n.t('Disconnect')}
					</button>
				</div>
			{:else}
				<div class="space-y-3">
					<input
						type="password"
						class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-transparent focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-600"
						placeholder={$i18n.t('ClawHub API token (clh_...)')}
						bind:value={authToken}
					/>
					<button
						class="px-4 py-2 text-sm bg-black dark:bg-white text-white dark:text-black rounded-lg hover:opacity-80 transition disabled:opacity-50"
						disabled={authLoading || !authToken.trim()}
						on:click={handleSaveAuth}
					>
						{authLoading ? $i18n.t('Connecting...') : $i18n.t('Connect')}
					</button>
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- Modals -->
<SkillDetailModal
	bind:show={showDetail}
	skill={detailSkill}
	preview={detailPreview}
	installed={detailSkill ? installedSlugs.has(detailSkill.slug || detailSkill.id || '') : false}
	installing={detailSkill ? installingSlugs.has(detailSkill.slug || detailSkill.id || '') : false}
	onInstall={() => detailSkill && handleInstall(detailSkill)}
	onUninstall={() => {
		if (detailSkill) {
			const inst = getInstallationForSlug(detailSkill.slug || detailSkill.id || '');
			if (inst) handleUninstall(inst.id);
		}
	}}
/>

<ConfigModal
	bind:show={showConfig}
	token={localStorage.token}
	installationId={configInstallationId}
	skillName={configSkillName}
	onSave={loadInstallations}
/>
