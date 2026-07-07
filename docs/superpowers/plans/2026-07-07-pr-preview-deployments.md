# PR Preview Deployments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a same-repo PR that changes the site, deploy the built site to a Cloudflare Pages preview URL and post that URL back to the PR.

**Architecture:** A new `pull_request`-triggered workflow reuses the existing Direct Upload build (`generate.py --landing` + `bun run build`) but runs `wrangler pages deploy --branch=pr-<n>` instead of `--branch=main`, and skips the routing Worker. It posts a single sticky comment with the preview URL.

**Tech Stack:** GitHub Actions, Python 3.12, Bun, Astro/Starlight, `cloudflare/wrangler-action@v4`, Cloudflare Pages (Direct Upload), `gh` CLI + `jq`.

## Global Constraints

- Actions run on the **node24** runtime only: `actions/checkout@v7`, `actions/setup-python@v6`, `oven-sh/setup-bun@v2`, `cloudflare/wrangler-action@v4`. No node20 actions.
- **Same-repo PRs only.** Guard: `if: github.event.pull_request.head.repo.full_name == github.repository`.
- **Never** deploy `--branch=main` and **never** deploy the Worker from this workflow.
- Token for `generate.py`: `${{ secrets.DASHBOARD_PAT || secrets.GITHUB_TOKEN }}`.
- Build uses `bun install --frozen-lockfile` (same gate as prod).
- No em dashes (`—`) in any comment copy or file content. Use `-`, `:`, or rewrite.

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

Evidence cells are filled only at the verification gate, with fresh same-session output.

---

### Task 1: Author the preview-deploy workflow

**Files:**
- Create: `.github/workflows/preview-deploy.yml`

**Interfaces:**
- Consumes: repo secrets `DASHBOARD_PAT`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and the auto-provided `GITHUB_TOKEN`. Committed file `site/src/generated/search-indexes.json`. Cloudflare Pages project `software-pack-dashboard`.
- Produces: a preview deployment at `https://pr-<n>.software-pack-dashboard.pages.dev` and one sticky PR comment marked `<!-- preview-url -->`.

**Advances journeys:** 1, 2, 4, 5, 6, 7

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/preview-deploy.yml` with exactly this content:

```yaml
name: Preview deploy

on:
  pull_request:
    paths:
      - 'site/**'
      - 'generate.py'
      - '.github/workflows/preview-deploy.yml'

permissions:
  contents: read
  pull-requests: write

# One live preview build per PR; a newer push cancels the in-flight one.
concurrency:
  group: preview-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  preview:
    # Fork PRs receive no secrets, so the Cloudflare deploy could not
    # authenticate. Restrict to same-repo PRs; forks are skipped cleanly
    # (neutral status, not a failed check).
    if: github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt

      - name: Render landing content
        env:
          # Same pattern as lint-and-test.yml. DASHBOARD_PAT is available on
          # same-repo PRs and lets private packs resolve; falls back otherwise.
          GITHUB_TOKEN: ${{ secrets.DASHBOARD_PAT || secrets.GITHUB_TOKEN }}
        run: python generate.py --landing site/src/content/docs/index.md

      - uses: oven-sh/setup-bun@v2
      - name: Build landing (Astro)
        run: cd site && bun install --frozen-lockfile && bun run build

      - name: Deploy preview to Cloudflare Pages
        id: deploy
        uses: cloudflare/wrangler-action@v4
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          # Non-main branch => a Pages PREVIEW deployment, not production.
          command: pages deploy site/dist --project-name=software-pack-dashboard --branch=pr-${{ github.event.pull_request.number }}

      - name: Comment preview URL on the PR
        if: steps.deploy.outputs.pages-deployment-alias-url != '' || steps.deploy.outputs.deployment-url != ''
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          PR: ${{ github.event.pull_request.number }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
          ALIAS_URL: ${{ steps.deploy.outputs.pages-deployment-alias-url }}
          UNIQUE_URL: ${{ steps.deploy.outputs.deployment-url }}
        run: |
          set -euo pipefail
          marker='<!-- preview-url -->'
          url="${ALIAS_URL:-$UNIQUE_URL}"
          body=$(printf '%s\n\n**Preview deploy:** %s\n\nBuilt from `%s`. Redeploys on each push to this PR.' "$marker" "$url" "$HEAD_SHA")
          # Upsert a single marker comment so re-pushes update in place.
          comments=$(gh api "repos/$REPO/issues/$PR/comments" --paginate)
          id=$(printf '%s' "$comments" | jq -r --arg m "$marker" 'map(select(.body | contains($m))) | .[0].id // empty')
          if [ -n "$id" ]; then
            gh api --method PATCH "repos/$REPO/issues/comments/$id" -f body="$body"
          else
            gh api --method POST "repos/$REPO/issues/$PR/comments" -f body="$body"
          fi
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/preview-deploy.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Lint the workflow (if actionlint is available)**

Run: `command -v actionlint >/dev/null && actionlint .github/workflows/preview-deploy.yml || echo "actionlint not installed - skipping"`
Expected: either no output (clean) or `actionlint not installed - skipping`. If actionlint reports errors, fix them and re-run Step 2.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/preview-deploy.yml
git commit -m "ci: add PR preview deployments to Cloudflare Pages"
```

---

### Task 2: Verify the journeys on a live PR

This feature can only be verified by a real PR run (no local Actions harness; the Cloudflare deploy and secrets cannot be faked). The implementation PR adds `preview-deploy.yml`, which is itself in the trigger paths, so the workflow runs on this PR for the same-repo case and self-verifies rows 1, 2, 4, 7. Row 3 needs a visible site change; row 5 needs an unrelated non-site PR; row 6 is a guard inspection plus a likely waiver.

**Files:**
- Modify (temporary): `site/src/styles/dashboard.css` (a preview smoke marker, removed before merge)

**Advances journeys:** 3 (and captures evidence for 1, 2, 4, 5, 6, 7 at the verification gate)

- [ ] **Step 1: Add a survivable preview marker for journey 3**

Append this rule to `site/src/styles/dashboard.css` (a custom property survives CSS minification, unlike a comment):

```css
/* TEMP preview smoke marker - remove before merge (journey 3). */
:root { --preview-smoke: "pr-preview-check-20260707"; }
```

- [ ] **Step 2: Commit and push the branch**

```bash
git add site/src/styles/dashboard.css
git commit -m "test: temporary preview smoke marker (journey 3)"
git -c credential.helper='!gh auth git-credential' push -u https://github.com/nebari-dev/software-pack-dashboard.git ci/pr-preview-deploys
```

- [ ] **Step 3: Open the PR (self-triggers the workflow)**

```bash
gh pr create --base main --head ci/pr-preview-deploys \
  --title "ci: add PR preview deployments" \
  --body "Adds same-repo PR preview deploys to Cloudflare Pages. See docs/superpowers/specs/2026-07-07-pr-preview-deployments-design.md. Contains a temporary CSS smoke marker (last commit) to be reverted before merge."
```

- [ ] **Step 4: Watch the preview-deploy run to completion**

Run: `gh pr checks <pr> --watch`
Expected: the `preview-deploy / preview` job passes. Capture the run log for the `Deploy preview to Cloudflare Pages` step (journeys 1 and 7: shows `--branch=pr-<n>`, no `--branch=main`, no Worker deploy).

- [ ] **Step 5: Verify the preview URL (journeys 2 and 3)**

Run:
```bash
url=$(gh pr view <pr> --json comments \
  --jq '[.comments[] | select(.body | contains("<!-- preview-url -->"))][-1].body' \
  | grep -oE 'https://[a-z0-9.-]+\.pages\.dev' | head -1)
echo "$url"
curl -sI "$url" | head -1                      # journey 2: expect HTTP 200
css=$(curl -s "$url" | grep -oE '/_astro/[^"]+\.css' | head -1)
curl -s "$url$css" | grep -o 'pr-preview-check-20260707'   # journey 3: marker present
```
Expected: `HTTP/2 200` and the marker string `pr-preview-check-20260707` printed. Paste both into the journey Evidence cells.

- [ ] **Step 6: Verify sticky comment (journey 4)**

Push a trivial second commit (e.g. re-touch the CSS marker comment), wait for the re-run, then:
Run: `gh pr view <pr> --json comments --jq '[.comments[] | select(.body | contains("<!-- preview-url -->"))] | length'`
Expected: `1`. Paste into Evidence.

- [ ] **Step 7: Verify path filter (journey 5)**

Confirm no `preview-deploy` run appears on a non-site PR. Use an existing CI-only PR if one is open (e.g. the node20 PR #15), or note that a throwaway non-site PR / waiver is needed.
Run: `gh pr checks <non-site-pr>`
Expected: no `preview-deploy` entry. Paste into Evidence.

- [ ] **Step 8: Verify fork guard (journey 6)**

Inspect the `if:` guard in the committed workflow and confirm it gates on `github.event.pull_request.head.repo.full_name == github.repository`. A fork PR cannot be opened from the dev environment, so record either a fork-PR "skipped" screenshot if one is available, or a user waiver in the Evidence cell.

- [ ] **Step 9: Remove the temporary marker before merge**

```bash
git revert --no-edit HEAD   # or delete the marker rule and the "test:" commit via a follow-up commit
git -c credential.helper='!gh auth git-credential' push https://github.com/nebari-dev/software-pack-dashboard.git ci/pr-preview-deploys
```
Confirm the preview re-runs and the marker is gone from the redeployed CSS. The final PR contains only `.github/workflows/preview-deploy.yml` (plus the spec/plan docs).

---

## Self-Review

**Spec coverage:**
- Trigger (site/**, generate.py, workflow file), same-repo guard, concurrency, permissions - Task 1 Step 1. ✓
- Regenerate content with `DASHBOARD_PAT || GITHUB_TOKEN`, no `generate_routes.py` - Task 1 Step 1 (`Render landing content`). ✓
- Build with frozen lockfile - Task 1 Step 1 (`Build landing`). ✓
- Deploy to `--branch=pr-<n>`, never main, never Worker - Task 1 Step 1 + verified Task 2 Steps 4/7. ✓
- Sticky comment via gh + jq marker upsert - Task 1 Step 1 + verified Task 2 Step 6. ✓
- Out of scope (no PR-close cleanup, no Worker preview, no portal-deploy change) - honored; nothing in the plan touches them. ✓
- All 7 journeys mapped to verification steps in Task 2. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases". The workflow YAML is complete; every verification step has an exact command and expected output. `<pr>` / `<non-site-pr>` are runtime values filled at execution, not content placeholders. ✓

**Type/name consistency:** marker string `<!-- preview-url -->` and smoke marker `pr-preview-check-20260707` are used identically in authoring and verification. Output names `pages-deployment-alias-url` / `deployment-url` match the wrangler-action@v4 `action.yml`. ✓
