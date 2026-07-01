import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { nebari } from '@nebari/starlight';
import searchIndexes from './src/generated/search-indexes.json';

export default defineConfig({
  site: 'https://packs.nebari.dev',
  integrations: [
    starlight({
      title: 'Nebari Software Packs',
      plugins: [nebari()],
      // Dashboard-specific styling (hero + pack catalog). Loads after the
      // @nebari/starlight theme CSS so it can build on the brand tokens.
      customCss: ['./src/styles/dashboard.css'],
      // Unified multisite search: merge each pack's same-origin Pagefind bundle.
      // searchIndexes is [] until packs adopt Starlight (sub-project C).
      pagefind: { mergeIndex: searchIndexes.map((bundlePath) => ({ bundlePath })) },
    }),
  ],
});
