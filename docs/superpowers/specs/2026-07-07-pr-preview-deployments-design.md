# Design: PR preview deployments for the dashboard site

- Date: 2026-07-07
- Repo: `software-pack-dashboard` (serves `packs.nebari.dev`)
- Status: design approved, pending spec review
- Author: Chuck McAndrew

## Context

The dashboard is deployed to Cloudflare Pages via **Direct Upload** from CI:
`.github/workflows/portal-deploy.yml` runs `generate.py --landing`, builds the
Astro site with `bun run build`, and runs
`wrangler pages deploy site/dist --project-name=software-pack-dashboard --branch=main`.
It also deploys the routing Worker (`packs-portal-worker`) that fronts
`packs.nebari.dev`.

Two facts shape this work:

- **Direct Upload never auto-creates previews.** A preview only exists if a
  workflow explicitly deploys a non-production branch. There is no Cloudflare
  Pages Git integration on this project.
- **The only `pull_request`-triggered workflow is `lint-and-test.yml`**, which
  runs `pytest` and a `generate.py --dry-run`. It never builds or deploys the
  site.

So a PR that changes the site (theme, layout, content structure) cannot be
reviewed as a rendered page before it merges to `main` and deploys to
production. This design adds that capability.

The landing page content is **not committed**: `site/src/content/docs/index.md`
is gitignored and produced by `generate.py --landing` at deploy time. Any
preview must therefore regenerate it. `site/src/generated/search-indexes.json`
**is** committed (refreshed by `refresh.yml`), so it does not need
regeneration.

## Goal

On a pull request that changes the site, build the site and deploy it to a
Cloudflare Pages **preview** URL, then post that URL back to the PR. Reviewers
get a live rendering of the change without merging to production. Production
(`packs.nebari.dev`) and the routing Worker are never touched by a preview.

## Key decisions

1. **Mechanism: reuse the existing Direct Upload path.** A new PR-triggered
   workflow builds exactly as `portal-deploy.yml` does, but deploys to a
   preview branch (`pr-<number>`) instead of `main`, and skips the Worker.
   Rejected: Cloudflare Pages Git integration (its build sandbox cannot run
   `generate.py` with Python + `DASHBOARD_PAT`, and it would duplicate the
   Direct Upload deploy); a separate ephemeral Pages project (more moving parts,
   no benefit).

2. **Content: regenerate, do not expect committed content.** The preview runs
   `generate.py --landing site/src/content/docs/index.md`. It does not run
   `generate_routes.py` (that targets the Worker, which previews do not touch).

3. **Token: `DASHBOARD_PAT || GITHUB_TOKEN`**, the same pattern
   `lint-and-test.yml` already uses. Previews are same-repo-only (see decision
   4), so `DASHBOARD_PAT` is available and the preview matches production,
   including the private packs. The same private-pack metadata is already
   published on the public `packs.nebari.dev`, so this is not a new disclosure.

4. **Scope: same-repo PRs that touch the site.** The job is guarded by
   `if: github.event.pull_request.head.repo.full_name == github.repository`.
   Fork PRs receive no secrets from GitHub, so the Cloudflare deploy could not
   authenticate; the guard skips them cleanly rather than failing. The trigger
   uses a path filter: `site/**`, `generate.py`, and the preview workflow file
   itself (a `generate.py` change alters the rendered landing page even when
   `site/**` is untouched).

5. **Comment: one sticky comment per PR.** The preview URL is posted via the
   `gh` CLI, keyed on a hidden `<!-- preview-url -->` marker: edit the existing
   comment if present, otherwise create it. This avoids one comment per push and
   avoids introducing a third-party action right after removing the deprecated
   node20 ones.

6. **Out of scope (YAGNI):** deleting the preview on PR close (Cloudflare prunes
   preview deployments on its own), previewing the routing Worker, and any
   change to `portal-deploy.yml`.

## Architecture

New file `.github/workflows/preview-deploy.yml`, kept separate from
`lint-and-test.yml` so test and deploy-preview concerns, permissions, and
concurrency stay isolated (mirrors `portal-deploy.yml`).

```
name: Preview deploy

on:
  pull_request:
    paths: ['site/**', 'generate.py', '.github/workflows/preview-deploy.yml']

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: preview-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  preview:
    # Same-repo PRs only; fork PRs have no secrets and are skipped cleanly.
    if: github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    steps:
      - actions/checkout@v7
      - actions/setup-python@v6 (3.12) + pip install -r requirements.txt
      - python generate.py --landing site/src/content/docs/index.md
          env GITHUB_TOKEN: ${{ secrets.DASHBOARD_PAT || secrets.GITHUB_TOKEN }}
      - oven-sh/setup-bun@v2
      - cd site && bun install --frozen-lockfile && bun run build
      - cloudflare/wrangler-action@v4  (id: deploy)
          apiToken / accountId from secrets
          command: pages deploy site/dist
                   --project-name=software-pack-dashboard
                   --branch=pr-${{ github.event.pull_request.number }}
      - Sticky comment step (gh CLI):
          url = steps.deploy.outputs.pages-deployment-alias-url
          upsert PR comment carrying the <!-- preview-url --> marker
```

All actions are on the node24 runtime, consistent with the node20 cleanup in
the companion PR.

### Data flow

`pull_request` (same-repo, site path) -> regenerate `index.md` -> `bun build`
-> `pages deploy --branch=pr-<n>` -> Cloudflare returns
`https://pr-<n>.software-pack-dashboard.pages.dev` (alias) -> sticky comment on
the PR. Production and the Worker are never invoked.

## Journeys

| # | Item | Proof | Check method | Evidence |
|---|------|-------|--------------|----------|
| 1 | A same-repo PR touching `site/**` gets a preview build + deploy | On such a PR, the `preview-deploy` job runs and succeeds; wrangler reports a `pages deploy` to branch `pr-<n>` | narrated: the implementation PR's own Actions run - paste the successful job log showing the `pages deploy … --branch=pr-<n>` step | *(empty)* |
| 2 | A working preview URL is posted to the PR | A PR comment contains `https://pr-<n>.software-pack-dashboard.pages.dev`; `curl -sI` that URL returns HTTP 200 | narrated: text of the comment + `curl -sI` transcript showing `200` | *(empty)* |
| 3 | The preview renders the PR's changes, not production | A deliberate visible change in the PR (marker string in `dashboard.css` or content) is present in the deployed preview | narrated: `curl -s <preview-url>/_astro/*.css \| grep <marker>` (or rendered HTML) showing the change | *(empty)* |
| 4 | Re-pushing updates one sticky comment, not many | After a second push to the PR, exactly one comment carries the `<!-- preview-url -->` marker, updated to the newest deploy | narrated: `gh pr view --json comments` count of marker comments == 1 after 2 pushes | *(empty)* |
| 5 | A PR that does not touch `site/**`/`generate.py` triggers no preview | On a Python-only or CI-only PR, no `preview-deploy` run appears | narrated: `gh pr checks` / Actions list for such a PR showing no preview-deploy run | *(empty)* |
| 6 | A fork PR is skipped cleanly - no failed check, no secret use | The job `if` gates on same-repo; a fork PR shows the job skipped (neutral), never a red X, never touches secrets | narrated: inspect the guard expression + a fork-PR run showing "skipped"; likely a user waiver since a fork PR cannot be opened from the dev environment | *(empty)* |
| 7 | The preview never deploys to production or the Worker | The run only executes `pages deploy … --branch=pr-<n>` (never `--branch=main`) and never runs the Worker `deploy`; `packs.nebari.dev` is unchanged | narrated: full job log confirming only the preview branch deploy step ran | *(empty)* |

Evidence cells are filled only at the verification gate, with fresh
same-session output. Row 6 is expected to resolve as a reasoned guard
inspection plus a user waiver for the end-to-end fork case.

## Verification approach

There is no local harness for GitHub Actions (no `act`, and the Cloudflare
deploy plus secrets cannot be faked), so journeys are verified by narration on a
real PR. The implementation PR adds `preview-deploy.yml` and includes a small
`site/**` change, so it triggers the workflow on itself and self-verifies rows
1-4 and 7. Row 5 is verified against an unrelated non-site PR. Row 6 is verified
by inspecting the guard, with an end-to-end fork test waived if no fork PR is
available.

## Risks and open questions

- **Secrets on same-repo PRs:** GitHub provides secrets to same-repo PR runs,
  which is why the guard restricts to same-repo. If branch protection or repo
  settings ever restrict PR secrets, previews would silently stop; the guard
  still fails safe (skips), it does not leak.
- **Preview URL length:** Cloudflare sanitizes and truncates branch names to 28
  characters for the alias host. `pr-<number>` stays well under that.
- **First run cost:** the preview runs the full Python + bun build on each site
  PR push; `cancel-in-progress` keeps only the latest running per PR.
- **`gh` sticky-comment script:** must handle the create-vs-edit branches and
  the empty-comment-list case; covered by journey 4.

## References to verify during planning

- Cloudflare Pages Direct Upload preview behavior for non-production `--branch`
  values, and the exact alias host format.
- `cloudflare/wrangler-action@v4` output name `pages-deployment-alias-url`
  (confirmed present in the v4 `action.yml`; re-confirm the value is populated
  for a Direct Upload preview deploy).
- GitHub Actions secret availability for same-repo vs fork `pull_request` runs.
- `gh` CLI commands for listing and editing PR comments in a workflow
  (`gh pr comment`, `gh api` for comment listing/editing) under `GITHUB_TOKEN`.
