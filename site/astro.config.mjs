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
      // Unified multisite search: merge each pack's same-origin Pagefind bundle.
      // searchIndexes is [] until packs adopt Starlight (sub-project C).
      pagefind: { mergeIndex: searchIndexes.map((bundlePath) => ({ bundlePath })) },
    }),
  ],
});
