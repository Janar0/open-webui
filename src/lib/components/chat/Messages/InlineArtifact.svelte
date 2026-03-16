<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { settings } from '$lib/stores';
	import ArrowsPointingOut from '../../icons/ArrowsPointingOut.svelte';
	import Download from '../../icons/Download.svelte';
	import Tooltip from '../../common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let code = '';
	export let lang = 'html';
	export let id = '';

	let isDark = false;
	let iframe: HTMLIFrameElement;
	let iframeHeight = 200;

	function wrapContent(code: string, lang: string, bgColor: string): string {
		// IMPORTANT: do NOT use literal '<style>' inside template strings —
		// vite-plugin-svelte's CSS preprocessor scans the whole file with regex
		// and tries to parse <style> content it finds inside JS template literals.
		const colorScheme = isDark ? 'dark' : 'light';

		// Inject background + color-scheme via a script tag (no <style> needed)
		const bgInject =
			'<' + 'script' + '>' +
			`document.documentElement.style.colorScheme='${colorScheme}';` +
			`document.addEventListener('DOMContentLoaded',function(){if(document.body)document.body.style.backgroundColor='${bgColor}';});` +
			'</' + 'script' + '>';

		// Static CSS block — no JS expressions inside, built via concatenation
		const cssBlock =
			'<' + 'style' + '>' +
			'body{margin:0;padding:16px;font-family:system-ui,-apple-system,sans-serif;}' +
			'*{box-sizing:border-box;}' +
			'</' + 'style' + '>';

		if (lang === 'svg') {
			return (
				'<!DOCTYPE html><html><head><meta charset="UTF-8">' +
				bgInject +
				'</head><body style="margin:0;display:flex;justify-content:center;align-items:center;min-height:fit-content;overflow:hidden;">' +
				code +
				'</body></html>'
			);
		}

		// Already a full document — inject bg script before </head>
		if (code.match(/<html[\s>]/i) || code.match(/<!DOCTYPE/i)) {
			if (code.includes('</head>')) {
				return code.replace('</head>', bgInject + '</head>');
			}
			return bgInject + code;
		}

		// Wrap fragment
		return (
			'<!DOCTYPE html><html><head>' +
			'<meta charset="UTF-8">' +
			'<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
			cssBlock +
			bgInject +
			'</head><body>' +
			code +
			'</body></html>'
		);
	}

	function injectHeightReporter(html: string): string {
		const escapedId = id.replace(/'/g, "\\'");
		const script = `<script>
(function(){
// Force content height to be intrinsic, not stretched by iframe container
var s=document.createElement('style');
s.textContent='html,body{height:auto!important;overflow:hidden!important;}';
(document.head||document.documentElement).appendChild(s);
var _lastH=0,_t=null;
function rh(){
if(_t)clearTimeout(_t);
_t=setTimeout(function(){
_t=null;
var h=Math.max(document.documentElement.scrollHeight||0,document.body?document.body.scrollHeight:0);
if(h!==_lastH){_lastH=h;parent.postMessage({type:'iframe:artifactHeight',id:'${escapedId}',height:h},'*');}
},50);
}
if(document.readyState==='complete')rh();
else window.addEventListener('load',rh);
if(typeof ResizeObserver!=='undefined')new ResizeObserver(rh).observe(document.body||document.documentElement);
new MutationObserver(rh).observe(document.documentElement,{childList:true,subtree:true});
window.addEventListener('load',function(){setTimeout(rh,200);setTimeout(rh,800);});
})();
<\/script>`;

		if (html.includes('</body>')) {
			return html.replace('</body>', `${script}\n</body>`);
		}
		if (html.includes('</html>')) {
			return html.replace('</html>', `${script}\n</html>`);
		}
		return html + '\n' + script;
	}

	// Derive chat background color from dark mode + backgroundImageUrl setting
	$: chatBgColor = $settings?.backgroundImageUrl
		? 'transparent'
		: isDark
			? '#0a0a0a'
			: '#ffffff';

	$: srcdoc = injectHeightReporter(wrapContent(code, lang, chatBgColor));

	function onMessage(e: MessageEvent) {
		if (!iframe || e.source !== iframe.contentWindow) return;
		if (e.data?.type === 'iframe:artifactHeight' && e.data?.id === id) {
			const newHeight = Math.max(80, Math.min(e.data.height + 4, 3000));
			if (Math.abs(newHeight - iframeHeight) > 2) {
				iframeHeight = newHeight;
			}
		}
	}

	function showFullScreen() {
		if (iframe?.requestFullscreen) {
			iframe.requestFullscreen();
		}
	}

	function downloadArtifact() {
		const blob = new Blob([wrapContent(code, lang, chatBgColor)], { type: 'text/html' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `artifact-${id}.html`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}

	let _themeObserver: MutationObserver | null = null;

	onMount(() => {
		window.addEventListener('message', onMessage);
		isDark = document.documentElement.classList.contains('dark');
		_themeObserver = new MutationObserver(() => {
			isDark = document.documentElement.classList.contains('dark');
		});
		_themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
	});

	onDestroy(() => {
		window.removeEventListener('message', onMessage);
		_themeObserver?.disconnect();
	});
</script>

<div class="inline-artifact mt-2 rounded-2xl overflow-hidden border border-gray-200/50 dark:border-gray-700/50 shadow-sm">
	<iframe
		bind:this={iframe}
		title="Artifact"
		{srcdoc}
		style="height: {iframeHeight}px; transition: height 0.15s ease-out;"
		class="w-full border-0 bg-white"
		sandbox="allow-scripts allow-downloads{($settings?.iframeSandboxAllowForms ?? false)
			? ' allow-forms'
			: ''}{($settings?.iframeSandboxAllowSameOrigin ?? false) ? ' allow-same-origin' : ''}"
	></iframe>

	<div
		class="flex items-center justify-end gap-0.5 px-2.5 py-1 bg-gray-50 dark:bg-gray-900/80 border-t border-gray-200/50 dark:border-gray-700/50"
	>
		<Tooltip content={$i18n.t('Open in full screen')}>
			<button
				class="p-1 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
				on:click={showFullScreen}
			>
				<ArrowsPointingOut className="size-3.5" />
			</button>
		</Tooltip>

		<Tooltip content={$i18n.t('Download')}>
			<button
				class="p-1 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
				on:click={downloadArtifact}
			>
				<Download className="size-3.5" />
			</button>
		</Tooltip>
	</div>
</div>
