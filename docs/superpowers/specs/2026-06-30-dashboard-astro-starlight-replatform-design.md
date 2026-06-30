# Design: dashboard re-platform to Astro + Starlight

- Date: 2026-06-30
- Repo: `software-pack-dashboard` (serves `packs.nebari.dev`)
- Status: design approved, pending spec review
- Author: Chuck McAndrew

## Context

This repo builds the Nebari software-pack portal at `packs.nebari.dev`. Today:

- `generate.py` reads `tracked-packs.yaml`, fetches each pack's
  `pack-metadata.yaml` + GitHub API fields, and renders `README.md` (the full
  dashboard) and `site/content/_index.md` (a Hugo landing page: intro + a simple
  4-column pack table).
- The site in `site/` is a Hugo site that imports the `nebari-hugo-theme` module.
- `generate_routes.py` renders `worker/src/routes.json` mapping a pack slug to
  its Cloudflare Pages host.
- A Cloudflare Worker (`worker/`) proxies `packs.nebari.dev/<slug>/` to the right
  pack host; everything else falls through to the dashboard host.
- `.github/workflows/portal-deploy.yml` renders the landing, builds with Hugo,
  and deploys `site/public` to Cloudflare Pages plus the Worker.
- `.github/workflows/refresh.yml` regenerates the dashboard hourly (the `chore:
  refresh dashboard` commits) and on push.

This is **sub-project B** of the Hugo to Astro+Starlight migration. Sub-project
A (`@nebari/starlight`, the shared Starlight theme plugin) is complete: built,
tested, reviewed, tagged `v0.1.0`, and pushed to `nebari-dev/starlight`.

## Goal

Re-platform the dashboard site from Hugo to **Astro + Starlight**, themed by
`@nebari/starlight`, and host the **unified Pagefind multisite search** here.
This advances the ecosystem goals of unified presentation (4), unified search
(5), and a single entry point (6) for the central portal, while leaving the
federated per-pack deploy model intact.

## Scope decision: clean re-platform

A **clean re-platform**, not an expansion. The site stays a **single landing
page** (intro + the existing simple 4-column table: Pack / Level / Owner /
Docs), now rendered by Astro + Starlight with Nebari branding and the hosted
unified search. Explicitly NOT in scope:

- An interactive/filterable pack catalog (deferred; the table stays as-is).
- Bringing documentation in-repo. The "Building a software pack" guide stays a
  separately-proxied site (the Worker `building-a-software-pack` extra-route is
  unchanged); the landing keeps linking to `/building-a-software-pack/`.
- Per-pack Starlight adoption and PR-preview/versioning (that is sub-project C).

## Key decisions

1. **Site framework:** Astro + Starlight, package-managed with **Bun** (matches
   the `@nebari/starlight` and `nebari-design` toolchain). The Astro app replaces
   the Hugo site; `site/hugo.toml`, `site/go.mod`, `site/go.sum`, and the
   `nebari-hugo-theme` dependency are removed.
2. **Landing layout:** Starlight's `template: splash` (hero + full-width content,
   no sidebar/TOC), appropriate for a one-page front door.
3. **Consume `@nebari/starlight`:** via the **v0.1.0 GitHub Release tarball**
   asset (`"@nebari/starlight":
   "https://github.com/nebari-dev/starlight/releases/download/v0.1.0/<tarball>.tgz"`).
   This works with no npm account, keeps the `@nebari` name, and is resolvable in
   Cloudflare CI. Swap to the npm version once `@nebari/starlight` is published.
4. **Landing content stays generated:** `generate.py` continues to render the
   landing, but writes a **Starlight content file** (`src/content/docs/index.mdx`,
   YAML frontmatter, `template: splash`) instead of the Hugo `_index.md`. Same
   intro + 4-column table; only the file format and front matter change.
5. **Unified search:** the dashboard's Pagefind search merges each pack's index
   via `mergeIndex('/<slug>/pagefind/')`. Because the Worker proxies every pack
   same-origin under `packs.nebari.dev/<slug>/`, no CORS config is needed. The
   **slug list is generated from `tracked-packs.yaml`** (packs with
   `docs_site: true`, the same source `generate_routes.py` uses) and consumed by
   the dashboard's search integration. The list is empty today, so search covers
   only the dashboard; it expands automatically as packs come online.

## Architecture

### What changes
- `site/` becomes an Astro + Starlight project: `package.json` (Bun), `bun.lock`,
  `astro.config.mjs` (`starlight({ plugins: [nebari()], ... })`),
  `src/content.config.ts`, `src/content/docs/index.mdx` (generated).
- `generate.py`: the `render_landing_*` path emits the Starlight content file
  (YAML front matter + `template: splash`) at the new path; it also emits the
  generated list of docs-enabled pack slugs for the search integration (a small
  JSON file the Astro app imports). The `README.md` rendering is unchanged.
- A **search integration** in the Astro app that initializes Pagefind with
  `mergeIndex` for each generated pack slug. The exact injection point (a
  Starlight `Search` component override vs. a Pagefind-init client script added
  via Starlight config) is confirmed against the Starlight site-search +
  Pagefind multisite docs during planning.
- `.github/workflows/portal-deploy.yml`: replace the Hugo build with
  `bun install && bun run build` (Astro); change the Pages deploy directory from
  `site/public` to the Astro output (`site/dist`). The `generate.py --landing`
  render step, `generate_routes.py`, and the Worker deploy stay.

### What stays
- `generate.py`'s overall responsibility and `README.md` output.
- `generate_routes.py` and `worker/` (the subpath proxy logic is unchanged).
- `.github/workflows/refresh.yml` (hourly): runs `generate.py`, commits content,
  which triggers `portal-deploy.yml`. Behavior unchanged; it now commits a
  Starlight content file instead of a Hugo one.
- `tracked-packs.yaml`, `schema/`, the Cloudflare Pages project, and the
  `packs.nebari.dev` routing.

## Prerequisite

Create the **`v0.1.0` GitHub Release** on `nebari-dev/starlight` with the packed
tarball asset (`bun pm pack` in `packages/starlight` produces the `.tgz`; attach
it via `gh release create v0.1.0`). The tag already exists; this adds the
downloadable asset the dashboard depends on. Creating the release is an
outward-facing action and will be confirmed before it is run.

## Testing

- `bun install` resolves `@nebari/starlight` from the release tarball; `bun run
  build` (Astro) exits 0 and produces `site/dist`.
- The built site renders with Nebari branding (tokens, fonts, logo, footer from
  `@nebari/starlight`).
- The built site emits its own Pagefind index (`site/dist/pagefind/`).
- `generate.py` emits a valid Starlight content file whose table rows match
  `tracked-packs.yaml`; a test asserts the generated front matter and table.
- The search integration initializes without error when the pack-slug list is
  empty (the current zero-pack case) and merges the listed indexes when present.
- `generate.py`'s existing test suite (`tests/`) continues to pass, updated for
  the new landing output format.

## Risks and open questions

- **Starlight search mergeIndex injection point.** Pagefind supports
  `mergeIndex` at runtime, and Starlight uses Pagefind by default, but the clean
  way to inject `mergeIndex` into Starlight's search UI (component override vs.
  init script) must be confirmed against current docs during planning. Fallback:
  a custom Pagefind UI initialization on the landing page.
- **Tarball to npm swap.** When `@nebari/starlight` is published to npm, the
  dependency changes from the tarball URL to a semver range. Low-risk, one-line.
- **`@nebari` npm name** is still pending the `nebari` npm org being claimed (the
  user is currently blocked on npm signup CAPTCHA); this does not block B because
  B consumes the tarball.
- **Output directory.** Astro defaults to `dist`; confirm the Cloudflare Pages
  deploy path and `astro.config` `outDir` line up (`site/dist`).

## References to verify during planning

- Starlight site search (Pagefind default): https://starlight.astro.build/guides/site-search/
- Pagefind multisite `mergeIndex`: https://pagefind.app/docs/multisite/
- Starlight splash template / landing pages: https://starlight.astro.build/guides/pages/
- Astro `base` / `outDir` config and Cloudflare Pages deploy.
