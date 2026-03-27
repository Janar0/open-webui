<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Modal from '$lib/components/common/Modal.svelte';
	import {
		updateInstallationConfig,
		getInstallationConfigSpec,
		deployToTerminal
	} from '$lib/apis/marketplace';
	import { selectedTerminalId } from '$lib/stores';

	const i18n = getContext('i18n');

	export let show = false;
	export let token = '';
	export let installationId = '';
	export let skillName = '';
	export let installation: any = null;
	export let onSave: () => void = () => {};

	let spec: any = null;
	let values: Record<string, string> = {};
	let loading = false;
	let saving = false;
	let deploying = false;

	$: if (show && installationId) {
		loadSpec();
	}

	$: scriptsDeployed = installation?.config?.scripts_deployed || false;
	$: scriptsPath = installation?.config?.scripts_path || '';
	$: hasScripts =
		installation?.config?.scripts && Object.keys(installation.config.scripts).length > 0;

	async function loadSpec() {
		loading = true;
		spec = null;
		try {
			spec = await getInstallationConfigSpec(token, installationId);
			// Initialize values empty — current_values are shown as masked labels
			values = {};
			for (const key of Object.keys(spec.properties || {})) {
				values[key] = '';
			}
		} catch (err) {
			toast.error(`Failed to load config: ${err}`);
		} finally {
			loading = false;
		}
	}

	async function handleSave() {
		saving = true;
		try {
			await updateInstallationConfig(token, installationId, values);
			toast.success($i18n.t('Configuration saved'));
			show = false;
			onSave();
		} catch (err) {
			toast.error(`Failed to save config: ${err}`);
		} finally {
			saving = false;
		}
	}

	async function handleDeploy() {
		deploying = true;
		try {
			await deployToTerminal(token, installationId, $selectedTerminalId || 'auto');
			toast.success($i18n.t('Scripts deployed to terminal'));
			onSave();
		} catch (err) {
			toast.error(`${$i18n.t('Failed to deploy')}: ${err}`);
		} finally {
			deploying = false;
		}
	}
</script>

<Modal bind:show size="sm">
	<div class="p-5">
		<div class="mb-4">
			<h3 class="text-lg font-medium">{$i18n.t('Configure')} {skillName}</h3>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
				{$i18n.t('Set required credentials and settings for this skill.')}
			</p>
		</div>

		<!-- Deploy Status -->
		{#if hasScripts}
			<div
				class="mb-4 p-3 rounded-lg border {scriptsDeployed
					? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20'
					: 'border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20'}"
			>
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium">
							{scriptsDeployed
								? $i18n.t('Scripts deployed')
								: $i18n.t('Scripts not deployed')}
						</p>
						{#if scriptsPath}
							<p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 font-mono">
								{scriptsPath}
							</p>
						{/if}
					</div>
					{#if !scriptsDeployed}
						<button
							class="text-xs px-3 py-1.5 bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-lg hover:bg-purple-500/20 transition disabled:opacity-50"
							disabled={deploying}
							on:click={handleDeploy}
						>
							{deploying ? $i18n.t('Deploying...') : $i18n.t('Deploy to Terminal')}
						</button>
					{/if}
				</div>
			</div>
		{/if}

		{#if loading}
			<div class="flex justify-center py-8">
				<div class="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-gray-600"
				></div>
			</div>
		{:else if spec && Object.keys(spec.properties || {}).length > 0}
			<div class="space-y-3">
				{#each Object.entries(spec.properties || {}) as [key, prop]}
					<div>
						<label for="config-{key}" class="block text-sm font-medium mb-1">
							{prop.title || key}
							{#if spec.required?.includes(key)}
								<span class="text-red-500">*</span>
							{/if}
						</label>
						{#if spec.current_values?.[key]}
							<p class="text-xs text-gray-400 mb-1">
								{$i18n.t('Current')}: {spec.current_values[key]}
							</p>
						{/if}
						<input
							id="config-{key}"
							type="password"
							class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-transparent focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-600"
							placeholder={prop.description || key}
							bind:value={values[key]}
						/>
					</div>
				{/each}
			</div>

			<div class="flex justify-end gap-2 mt-5">
				<button
					class="px-4 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
					on:click={() => (show = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="px-4 py-2 text-sm bg-black dark:bg-white text-white dark:text-black rounded-lg hover:opacity-80 transition disabled:opacity-50"
					disabled={saving}
					on:click={handleSave}
				>
					{saving ? $i18n.t('Saving...') : $i18n.t('Save')}
				</button>
			</div>
		{:else if !hasScripts}
			<p class="text-sm text-gray-500 py-4">{$i18n.t('No configuration required.')}</p>
		{/if}
	</div>
</Modal>
