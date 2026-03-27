<script lang="ts">
	import { onMount, getContext, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';

	import {
		searchCatalog,
		getCatalogSkillPreview,
		installSkill,
		uninstallSkill,
		getInstallations,
		checkUpdate,
		updateSkillVersion,
		deployToTerminal
	} from '$lib/apis/marketplace';
	import { getSkills } from '$lib/apis/skills';
	import { selectedTerminalId } from '$lib/stores';

	import SkillCard from './SkillCard.svelte';
	import SkillDetailModal from './SkillDetailModal.svelte';
	import ConfigModal from './ConfigModal.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	// State
	let activeTab: 'browse' | 'installed' = 'browse';
	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	let loading = false;
	let catalogResults: any[] = [];
	let nextCursor: string = '';
	let sortBy: string = 'recent';
	let installations: any[] = [];
	let installedSlugs: Set<string> = new Set();
	let installingSlugs: Set<string> = new Set();
	let deployingIds: Set<string> = new Set();

	// Detail modal
	let showDetail = false;
	let detailSkill: any = null;
	let detailPreview = '';

	// Config modal
	let showConfig = false;
	let configInstallationId = '';
	let configSkillName = '';
	// Reactively derive configInstallation so it refreshes after loadInstallations
	$: configInstallation = configInstallationId
		? installations.find((i: any) => i.id === configInstallationId) || null
		: null;

	onMount(async () => {
		await loadInstallations();
		await searchSkills();
	});

	function sortResults(items: any[]): any[] {
		if (sortBy === 'relevance') return items;
		const sorted = [...items];
		switch (sortBy) {
			case 'downloads':
				sorted.sort((a, b) => (b.downloads ?? 0) - (a.downloads ?? 0));
				break;
			case 'installs':
				sorted.sort((a, b) => (b.installs ?? 0) - (a.installs ?? 0));
				break;
			case 'name':
				sorted.sort((a, b) => (a.name ?? '').localeCompare(b.name ?? ''));
				break;
			case 'recent':
			default:
				sorted.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
				break;
		}
		return sorted;
	}

	async function searchSkills(append: boolean = false) {
		loading = true;
		try {
			const token = localStorage.token;
			const result = await searchCatalog(token, query, append ? nextCursor : '');
			let items: any[] = result?.items || [];
			nextCursor = result?.nextCursor || '';

			if (append) {
				catalogResults = sortResults([...catalogResults, ...items]);
			} else {
				catalogResults = sortResults(items);
			}
		} catch (err) {
			console.error('Catalog search error:', err);
			toast.error(`${$i18n.t('Failed to search catalog')}: ${err}`);
			if (!append) catalogResults = [];
		} finally {
			loading = false;
		}
	}

	function handleSearchInput() {
		clearTimeout(searchDebounceTimer);
		// Switch to relevance sort when querying, restore recent when cleared
		if (query && sortBy === 'recent') sortBy = 'relevance';
		else if (!query && sortBy === 'relevance') sortBy = 'recent';
		searchDebounceTimer = setTimeout(() => {
			searchSkills();
		}, 400);
	}

	function handleSortChange() {
		catalogResults = sortResults(catalogResults);
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

	async function handleInstall(skill: any) {
		const slug = skill.slug || skill.id || '';
		if (!slug) return;

		installingSlugs.add(slug);
		installingSlugs = installingSlugs;

		try {
			const token = localStorage.token;
			const result = await installSkill(token, slug);

			toast.success($i18n.t('Skill installed successfully'));

			// Show auto-deploy result
			if (result.auto_deployed && result.scripts_path) {
				toast.success(
					$i18n.t('Scripts auto-deployed to terminal at {{path}}', {
						path: result.scripts_path
					}),
					{ duration: 6000 }
				);
			}

			// Show warnings (e.g., sandbox requirements)
			if (result.warnings && result.warnings.length > 0) {
				for (const warning of result.warnings) {
					toast.warning(warning, { duration: 8000 });
				}
			}

			await loadInstallations();

			// If requires bins, open AI setup chat
			if (result.requires_bins && result.requires_bins.length > 0) {
				showDetail = false;
				openSetupChat(result);
				return;
			}

			// If requires env vars, open config modal
			if (result.requires_env && result.requires_env.length > 0) {
				configInstallationId = result.installation_id;
				configSkillName = result.name;
				showConfig = true;
			}
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

	async function handleDeploy(installationId: string) {
		deployingIds.add(installationId);
		deployingIds = deployingIds;

		try {
			const token = localStorage.token;
			// Use selected terminal or 'auto' to let backend pick first available
			await deployToTerminal(token, installationId, $selectedTerminalId || 'auto');
			toast.success($i18n.t('Scripts deployed to terminal'));
			await loadInstallations();
		} catch (err) {
			toast.error(`${$i18n.t('Failed to deploy')}: ${err}`);
		} finally {
			deployingIds.delete(installationId);
			deployingIds = deployingIds;
		}
	}

	async function openDetail(skill: any) {
		detailSkill = skill;
		detailPreview = '';
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

	function openConfigure(inst: any) {
		configInstallationId = inst.id;
		configSkillName = inst.meta?.name || inst.external_slug || '';
		showConfig = true;
	}

	function getInstallationForSlug(slug: string) {
		return installations.find((i: any) => i.external_slug === slug);
	}

	function openSetupChat(result: any) {
		const locale = (typeof localStorage !== 'undefined' && localStorage.getItem('locale')) || 'en-US';

		let prompt = `I just installed the "${result.name}" skill.`;

		if (result.requires_bins?.length > 0) {
			prompt += `\n\nTo get it working, I need to install the required CLI tool(s): **${result.requires_bins.join(', ')}**.`;
		}

		if (result.install_steps?.length > 0) {
			const brewStep = result.install_steps.find((s: any) => s.kind === 'brew');
			const aptStep = result.install_steps.find((s: any) => s.kind === 'apt' || s.kind === 'apt-get');
			if (brewStep) {
				prompt += `\n\nTo install via Homebrew:\n\`\`\`\nbrew install ${brewStep.formula}\n\`\`\``;
			} else if (aptStep) {
				prompt += `\n\nTo install via apt:\n\`\`\`\napt-get install ${aptStep.package || aptStep.formula}\n\`\`\``;
			} else {
				const firstStep = result.install_steps[0];
				if (firstStep?.label) {
					prompt += `\n\nInstall option: ${firstStep.label}`;
				}
			}
		}

		if (result.skill_content) {
			// Extract setup/auth lines from SKILL.md instructions (lines with commands like auth, setup, credentials)
			const setupLines = result.skill_content
				.split('\n')
				.filter((line: string) => /auth|setup|credential|login|api[_\s-]?key|token|configure/i.test(line))
				.slice(0, 8)
				.join('\n');
			if (setupLines) {
				prompt += `\n\n**Then configure it:**\n${setupLines}`;
			}
		}

		prompt += '\n\nPlease guide me step by step, starting by checking if the tool is installed.';

		if (!locale.startsWith('en')) {
			prompt += `\n\nNote: please respond in ${locale} — that is the user's interface language.`;
		}

		goto(`/?q=${encodeURIComponent(prompt)}`);
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
		</div>
	</div>

	<!-- Browse Tab -->
	{#if activeTab === 'browse'}
		<div class="mb-4 flex gap-2">
			<div class="relative flex-1">
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
			<select
				class="px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-xl bg-transparent focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-600"
				bind:value={sortBy}
				on:change={handleSortChange}
			>
				{#if sortBy === 'relevance'}
					<option value="relevance">{$i18n.t('Relevance')}</option>
				{/if}
				<option value="recent">{$i18n.t('Recent')}</option>
				<option value="downloads">{$i18n.t('Downloads')}</option>
				<option value="installs">{$i18n.t('Popular')}</option>
				<option value="name">{$i18n.t('Name')}</option>
			</select>
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

			{#if nextCursor}
				<div class="flex justify-center mt-4">
					<button
						class="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition"
						on:click={() => searchSkills(true)}
					>
						{$i18n.t('Load more')}
					</button>
				</div>
			{/if}
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
							{#if installation.config?.scripts && Object.keys(installation.config.scripts).length > 0}
								{#if installation.config?.scripts_deployed}
									<span
										class="text-xs px-2 py-1 text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 rounded-lg"
									>
										{$i18n.t('Deployed')}
									</span>
								{:else}
									<button
										class="text-xs px-2 py-1 bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-lg hover:bg-purple-500/20 transition disabled:opacity-50"
										disabled={deployingIds.has(installation.id)}
										on:click={() => handleDeploy(installation.id)}
									>
										{deployingIds.has(installation.id)
											? $i18n.t('Deploying...')
											: $i18n.t('Deploy to Terminal')}
									</button>
								{/if}
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
	installation={configInstallation}
	onSave={loadInstallations}
/>
