export { matchers } from './client-matchers.js';

export const components = [
	() => import("../../src/routes/__layout.svelte"),
	() => import("../runtime/components/error.svelte"),
	() => import("../../src/routes/index.svelte"),
	() => import("../../src/routes/test.svelte"),
	() => import("../../src/routes/test_2.svelte")
];

export const dictionary = {
	"": [[0, 2], [1]],
	"test": [[0, 3], [1]],
	"test_2": [[0, 4], [1]]
};