<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Modal from '$lib/components/common/Modal.svelte';
	import { updateInstallationConfig, getInstallationConfigSpec } from '$lib/apis/marketplace';

	const i18n = getContext('i18n');

	export let show = false;
	export let token = '';
	export let installationId = '';
	export let skillName = '';
	export let onSave: () => void = () => {};

	let spec: any = null;
	let values: Record<string, string> = {};
	let loading = false;
	let saving = false;

	$: if (show && installationId) {
		loadSpec();
	}

	async function loadSpec() {
		loading = true;
		spec = null;
		try {
			spec = await getInstallationConfigSpec(token, installationId);
			// Initialize values from current config or empty
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
</script>

<Modal bind:show size="sm">
	<div class="p-5">
		<div class="mb-4">
			<h3 class="text-lg font-medium">{$i18n.t('Configure')} {skillName}</h3>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
				{$i18n.t('Set required credentials and settings for this skill.')}
			</p>
		</div>

		{#if loading}
			<div class="flex justify-center py-8">
				<div class="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-gray-600"
				></div>
			</div>
		{:else if spec}
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
		{:else}
			<p class="text-sm text-gray-500 py-4">{$i18n.t('No configuration required.')}</p>
		{/if}
	</div>
</Modal>
