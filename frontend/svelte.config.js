import adapter from '@sveltejs/adapter-auto';
import preprocess from "svelte-preprocess";


/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter(),
		vite: {
			optimizeDeps: {
				include: ["highlight.js", "highlight.js/lib/core"],
			},
		},
	},
	preprocess: [
		preprocess({
			postcss: true,
		}),
	],
};

export default config;
