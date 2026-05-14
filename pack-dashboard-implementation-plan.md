# Pack Dashboard Implementation Plan

This document specifies an implementation plan for the **Nebari pack dashboard**: a generated markdown table that gives pre-sales engineers (and the team) a single view of every first-party software pack, its current maturity level, ownership, and demo readiness.

It is written to be implemented by Claude Code without further clarification. Where a decision could go either way, this document picks one — implementers should follow the document rather than re-deriving choices.

---

## 1. Context

Nebari ships ~15 first-party software packs (e.g. `nebari-data-science-pack`, `nebari-llm-serving-pack`). They are at varying maturity levels. Pre-sales engineers preparing customer demos currently have no single source of truth telling them which packs are demo-ready, who owns them, when they last shipped, or when they were last successfully demoed.

The maturity levels are defined in `nebari-dev/nebari-software-pack-template/docs/release-readiness-checklist.md`. The four active levels are **Experimental**, **Alpha**, **Beta**, **GA**. **Deprecated** is an orthogonal status.

This project implements the **dashboard** — a separate repo that pulls a metadata file from each tracked pack repo, augments it with GitHub-derived data, and renders a single `dashboard.md`.

---

## 2. Goals and Non-Goals

### Goals
- A single, always-up-to-date `dashboard.md` listing every tracked pack with its current level, owner, integration status, last release, last commit, and last demo.
- Visible flags for packs that are stale, missing metadata, or have a lapsed demo at Alpha+.
- Onboarding a new pack to the dashboard is a single PR to the dashboard repo (add a line to `tracked-packs.yaml`) plus adding `pack-metadata.yaml` to the pack repo.
- Zero ongoing maintenance per pack — pack authors edit their own metadata file in their own repo; the dashboard regenerates automatically.

### Non-Goals (v1)
- A web UI with filtering, search, or auth. The output is markdown rendered by GitHub.
- Real-time updates. Daily cron is enough; manual `workflow_dispatch` covers urgent regenerations.
- Parsing each pack's README to verify its declared maturity level matches the checklist state. Trust the declared level. Pre-sales signoff catches mismatches.
- Push triggers from pack repos. The dashboard pulls; packs don't push. (See `Out of Scope` for the optional `repository_dispatch` extension.)
- Discovery via GitHub topic tags or naming conventions. The tracked-packs list is explicit.
- Tracking community-contributed packs. First-party only.

---

## 3. System Overview

```
nebari-dev/pack-dashboard (this repo)
├── tracked-packs.yaml          # registry of first-party packs
├── generate.py                 # the generator script
├── dashboard.md                # the generated output (committed)
├── schema/
│   └── pack-metadata.schema.json
├── tests/
│   ├── fixtures/
│   └── test_generate.py
└── .github/workflows/
    └── refresh.yml             # cron + workflow_dispatch

nebari-dev/<each-pack-repo>
└── pack-metadata.yaml          # added by pack author
```

**Flow:** GitHub Actions in `pack-dashboard` runs `generate.py` on a daily cron. The script reads `tracked-packs.yaml`, fetches each pack's `pack-metadata.yaml` and GitHub API data, renders `dashboard.md`, and commits the result if it changed.

---

## 4. The `pack-metadata.yaml` File

### 4.1 Location

A file named `pack-metadata.yaml` at the root of each tracked pack repository, on the default branch.

### 4.2 Schema

```yaml
# Required fields
name: string                       # must match the GitHub repo name exactly
display_name: string               # human-readable name shown on the dashboard
description: string                # one-line description, max 200 chars
level: experimental | alpha | beta | ga
owner: string                      # GitHub username of accountable engineer (no @ prefix)
deprecated: bool

# Optional fields
sunset_date: string                # ISO 8601 date (YYYY-MM-DD). Required if deprecated: true.
product_owner: string | null       # GitHub username. Required if level == ga.
nebariapp_integration: none | partial | full | na  # default: na
scope:
  standalone-supported: yes | no   # default: no

last_promoted_at: string           # ISO 8601 date
last_promoted_pr: int              # PR number in the pack repo
last_presales_demo: string         # ISO 8601 date
last_presales_demo_by: string      # GitHub username
demo_notes: string                 # free-form notes for pre-sales, max 500 chars

links:
  docs: string                     # URL to extended docs
  demo: string                     # URL to a demo recording or live demo
```

### 4.3 Field reference

| Field | Required | Type | Notes |
|---|---|---|---|
| `name` | yes | string | Must equal the GitHub repo name (e.g. `nebari-data-science-pack`). Used to cross-check the file is in the right repo. |
| `display_name` | yes | string | Title-case, used as the link text on the dashboard. |
| `description` | yes | string | One sentence. Shown in a column on the dashboard. |
| `level` | yes | enum | `experimental` \| `alpha` \| `beta` \| `ga`. Lowercase. |
| `owner` | yes | string | Single GitHub username (no `@`). For multiple owners, use the most accountable one; others go in `CODEOWNERS`. |
| `deprecated` | yes | bool | `true` or `false`. |
| `sunset_date` | conditional | ISO date | Required when `deprecated: true`. Omit or null otherwise. |
| `product_owner` | conditional | string \| null | Required (non-null) when `level: ga`. May be null at other levels. |
| `nebariapp_integration` | no | enum | `none` \| `partial` \| `full` \| `na`. Default `na`. Use `na` for packs that aren't applications. |
| `scope.standalone-supported` | no | bool | Whether the pack installs without the operator. Default `no`. |
| `last_promoted_at` | no | ISO date | Date of the most recent level promotion. |
| `last_promoted_pr` | no | int | Number of the PR that promoted the pack. |
| `last_presales_demo` | no | ISO date | Date pre-sales last successfully demoed this pack. |
| `last_presales_demo_by` | no | string | GitHub username of the pre-sales engineer who ran the demo. |
| `demo_notes` | no | string | Free text. Surfaced on the dashboard verbatim. Use for known gotchas. |
| `links.docs` | no | URL | Extended docs (not the README). |
| `links.demo` | no | URL | Recorded or live demo link. |

### 4.4 Validation rules

The generator validates each parsed metadata file. Validation failure means the pack appears on the dashboard with a `metadata-invalid` flag and the specific error in the demo-notes column; **the rest of the dashboard still renders**. Errors are logged but do not fail the workflow.

Rules:

1. All required fields present and non-empty.
2. `name` matches the repo name in `tracked-packs.yaml`.
3. `level` is one of the four allowed enum values.
4. `nebariapp_integration` is one of the four allowed enum values (or absent).
5. `deprecated: true` implies `sunset_date` is present and parseable as ISO 8601.
6. `level: ga` implies `product_owner` is present and non-null.
7. All date fields parse as ISO 8601 (`YYYY-MM-DD`).
8. `description` ≤ 200 chars, `demo_notes` ≤ 500 chars.
9. URL fields, if present, parse as URLs (use `urllib.parse.urlparse` and check `scheme` + `netloc`).

A JSON Schema file (`schema/pack-metadata.schema.json`) MUST be included so pack authors can validate their file locally (e.g., `check-jsonschema --schemafile schema/pack-metadata.schema.json pack-metadata.yaml`).

### 4.5 Example

```yaml
name: nebari-data-science-pack
display_name: Data Science Pack
description: JupyterHub with jhub-apps for interactive data science workloads
level: alpha
owner: chuckmcandrew
deprecated: false
product_owner: null
nebariapp_integration: partial
scope:
  standalone-supported: yes
last_promoted_at: 2026-04-15
last_promoted_pr: 42
last_presales_demo: 2026-05-01
last_presales_demo_by: jdoe
demo_notes: "Use the small-instance profile for demos. Large profile times out on cluster provisioning."
links:
  docs: https://nebari.dev/docs/packs/data-science
```

---

## 5. The `tracked-packs.yaml` Registry

Lives at the root of the `pack-dashboard` repo. The format is intentionally minimal — the registry is just the list of repos to pull from. All other metadata lives in each pack's `pack-metadata.yaml`.

```yaml
# tracked-packs.yaml
# Adding a pack to this list is the formal moment of admitting it as a
# first-party tracked pack. Removing means it no longer appears on the
# dashboard. Both operations require a PR to this repo.
packs:
  - repo: nebari-dev/nebari-data-science-pack
  - repo: nebari-dev/nebari-llm-serving-pack
  # add more here
```

The `repo` field is `owner/name`. No other fields are permitted in v1.

---

## 6. Dashboard Repo Layout

```
pack-dashboard/
├── README.md                                # this is the public dashboard, see §8
├── tracked-packs.yaml
├── generate.py
├── requirements.txt                          # pyyaml only
├── schema/
│   └── pack-metadata.schema.json
├── tests/
│   ├── fixtures/
│   │   ├── valid-metadata.yaml
│   │   ├── invalid-missing-field.yaml
│   │   ├── invalid-bad-level.yaml
│   │   └── deprecated-without-sunset.yaml
│   └── test_generate.py
└── .github/
    └── workflows/
        └── refresh.yml
```

**The generated dashboard is written to `README.md` of the dashboard repo**, so it renders as the repo's front page on GitHub. The `README.md` should begin with a generated-file warning banner. The generator runs idempotently: regenerating with no changes produces no commit.

---

## 7. The Generator Script (`generate.py`)

### 7.1 Inputs and outputs

**Inputs:**
- `tracked-packs.yaml` (read from disk)
- `GITHUB_TOKEN` environment variable (provided by GitHub Actions)
- The GitHub API + raw.githubusercontent.com (network)

**Outputs:**
- `README.md` overwritten with the generated dashboard
- Exit code 0 on success (even with validation failures for individual packs)
- Exit code 1 on systemic failure (e.g., GitHub API unreachable, `tracked-packs.yaml` malformed)
- stderr log lines for each pack: `INFO`, `WARN`, or `ERROR`

### 7.2 Behavior

For each pack in `tracked-packs.yaml`:

1. Fetch `pack-metadata.yaml` from the default branch via `https://raw.githubusercontent.com/<repo>/HEAD/pack-metadata.yaml`. If 404, mark the pack as `metadata-missing` and continue.
2. Parse YAML. If parsing fails, mark as `metadata-invalid` with the parse error and continue.
3. Run the validation rules in §4.4. If any fail, mark as `metadata-invalid` with the specific failures and continue. Validated fields can still be used; failed fields are dropped.
4. Fetch GitHub API data for the repo:
   - Latest release: `GET /repos/{repo}/releases/latest` → tag name + published date. May 404 (no releases yet) — that's fine, record as none.
   - Default branch last commit date: `GET /repos/{repo}/commits?per_page=1` → date of HEAD commit.
   - Open issue count: `GET /repos/{repo}` → `open_issues_count`.
5. Compute flags (see §7.4).
6. Append to the row list.

After all packs processed, render the dashboard markdown (see §8) and write to `README.md`.

If the resulting `README.md` is byte-identical to the existing one, do not commit (the workflow handles this by checking `git diff --quiet`).

### 7.3 GitHub API usage

- Use `urllib.request` from stdlib. No `requests` dependency needed.
- Authenticate with `Authorization: Bearer ${GITHUB_TOKEN}` to get a 5000/hr rate limit (vs 60/hr unauthenticated).
- Set `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`.
- For raw file fetches, no auth header needed for public repos, but include it anyway to lift rate limits.
- Cache nothing — the script runs once per cron tick, ~30 API calls total for 15 packs. Far below any limit.
- On any 5xx or network error, retry once with a 2-second backoff. On second failure, mark the pack's GitHub-derived data as unavailable but proceed.

### 7.4 Computed flags

Each pack row may show zero or more flags in a `Flags` column. Flag rules:

| Flag | Condition |
|---|---|
| `metadata-missing` | `pack-metadata.yaml` returned 404 |
| `metadata-invalid` | YAML parse failed or validation rule failed |
| `stale` | `last_commit_date` > 90 days ago and `deprecated` is false |
| `demo-lapsed` | `level` ∈ {alpha, beta, ga} AND (`last_presales_demo` is missing OR `last_presales_demo` > 60 days ago) |
| `no-product-owner` | `level: ga` and `product_owner` is null |
| `deprecated` | `deprecated: true` (this is shown in addition to other flags) |

Flag display: emoji + short label, e.g. `⚠️ stale`, `🚫 deprecated`, `🆘 metadata-missing`.

### 7.5 Error handling summary

| Situation | Behavior |
|---|---|
| `tracked-packs.yaml` missing or malformed | Exit 1 (fail the workflow). |
| Pack repo doesn't exist (404 on the repo) | Log ERROR, render row with `repo-not-found` flag, continue. |
| Pack's `pack-metadata.yaml` missing | Render row with `metadata-missing` flag, continue. |
| Pack's `pack-metadata.yaml` invalid | Render row with `metadata-invalid` flag and the specific error in `demo_notes` column, continue. |
| GitHub API returns 5xx | Retry once. If still failing, leave GitHub-derived fields blank, continue. |
| GitHub API rate limit hit | Log ERROR, exit 1. (Should not happen at this scale.) |

---

## 8. The Dashboard Output (`README.md`)

### 8.1 Structure

```
<top banner: "This file is auto-generated. Do not edit directly.">

# Nebari Software Packs

_Last regenerated: <ISO 8601 UTC timestamp>. [Trigger a refresh](<link to workflow_dispatch>)._

## At a glance

- N GA · N Beta · N Alpha · N Experimental · N Deprecated
- N packs flagged · breakdown: <count by flag type>

## Packs

| Pack | Level | Owner | NebariApp | Standalone | Last release | Last commit | Last demo | Flags | Notes |
|---|---|---|---|---|---|---|---|---|---|
| ... |

## Deprecated packs

<a separate table for deprecated: true packs, with columns: Pack, Was Level, Sunset date, Migration>

## How this dashboard works

<a short prose section explaining: where data comes from, who edits it, how to add a new pack, link to the maturity levels doc>

<a footer with the regen timestamp again>
```

### 8.2 Rendering rules

- **Pack column**: `[<display_name>](https://github.com/<repo>)` — link to repo.
- **Level column**: Title-case (`Experimental`, `Alpha`, `Beta`, `GA`). Bold for GA.
- **Owner column**: `@<github-username>` linked to `https://github.com/<username>`.
- **NebariApp column**: render `none`/`partial`/`full`/`na` as `None`/`Partial`/`Full`/`N/A`.
- **Standalone column**: `Yes`/`No`/`–` (em-dash if `scope.standalone-supported` is missing).
- **Last release column**: `<tag> (<MMM DD>)` if a release exists, otherwise `–`.
- **Last commit column**: `<MMM DD>` formatted relative to UTC.
- **Last demo column**: `<MMM DD> by @<user>` or `–` if missing.
- **Flags column**: space-separated emoji+label list. Empty if none.
- **Notes column**: `demo_notes` verbatim, truncated to 100 chars with `…` if longer.

Deprecated packs are listed in their own table at the bottom, removed from the main table to avoid pre-sales accidentally pitching them.

For packs with `metadata-missing` or `metadata-invalid`, show the row with placeholders (`–`) for missing fields but still show the GitHub-derived data (last commit, open issues). The flag tells you why the row is sparse.

### 8.3 Example output excerpt

```markdown
| Pack | Level | Owner | NebariApp | Standalone | Last release | Last commit | Last demo | Flags | Notes |
|---|---|---|---|---|---|---|---|---|---|
| [Data Science Pack](https://github.com/nebari-dev/nebari-data-science-pack) | Alpha | [@chuckmcandrew](https://github.com/chuckmcandrew) | Partial | Yes | v0.5.2 (Apr 12) | Apr 28 | May 1 by [@jdoe](https://github.com/jdoe) | – | Use the small-instance profile for demos. Large profile times out on c… |
| [LLM Serving Pack](https://github.com/nebari-dev/nebari-llm-serving-pack) | Experimental | [@asmeurer](https://github.com/asmeurer) | Full | No | – | May 10 | – | ⚠️ demo-lapsed | – |
```

---

## 9. GitHub Actions Workflow (`.github/workflows/refresh.yml`)

```yaml
name: Refresh pack dashboard

on:
  schedule:
    - cron: '0 3 * * *'      # 03:00 UTC daily
  workflow_dispatch: {}      # manual trigger
  push:
    branches: [main]         # regenerate when generator code changes
    paths:
      - 'generate.py'
      - 'tracked-packs.yaml'
      - 'schema/**'
      - '.github/workflows/refresh.yml'

permissions:
  contents: write            # commit the regenerated README.md

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python generate.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - name: Commit if changed
        run: |
          if git diff --quiet README.md; then
            echo "No changes."
          else
            git config user.name "pack-dashboard-bot"
            git config user.email "[email protected]"
            git add README.md
            git commit -m "chore: refresh dashboard ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
            git push
          fi
```

---

## 10. Testing

### 10.1 Unit tests (`tests/test_generate.py`)

Test the pure functions in `generate.py`:

- **Validation**: pass each fixture in `tests/fixtures/` through the validator and assert expected errors / no errors.
- **Flag computation**: given a synthetic metadata + GitHub-derived data dict, assert the correct flags are computed for `stale`, `demo-lapsed`, `no-product-owner`, `deprecated`.
- **Date formatting**: assert `Apr 28` formatting for various inputs.
- **Row rendering**: given a fully-populated metadata + derived dict, assert the rendered markdown row matches a golden string.

Use `pytest`. Tests must not touch the network.

### 10.2 Integration smoke test

A separate test, invoked manually only (not in CI):

```bash
python generate.py --tracked-packs tests/fixtures/tracked-packs-smoke.yaml --dry-run
```

This runs against a small list of real repos with `--dry-run` (don't write `README.md`, print to stdout instead). Used to validate behavior end-to-end before merging changes to the generator.

### 10.3 CI integration

A `lint-and-test.yml` workflow runs on every PR:
- `pip install -r requirements.txt`
- `python -m pytest tests/`
- `python generate.py --dry-run` against the actual `tracked-packs.yaml` (must exit 0)

---

## 11. Implementation Steps

Recommended order. Each step ends in a working state.

1. **Bootstrap repo.** Create `nebari-dev/pack-dashboard` with `README.md` (manual placeholder), `LICENSE` (Apache 2.0), `.gitignore`, `requirements.txt` (just `pyyaml`).
2. **Add `tracked-packs.yaml`** with the initial pack list (start with 2-3 packs; add the rest after smoke-testing).
3. **Add `schema/pack-metadata.schema.json`** matching §4.2-4.4. This is the canonical schema.
4. **Write `generate.py`** as a single file with these functions:
   - `load_tracked_packs(path) -> list[dict]`
   - `fetch_metadata(repo, token) -> tuple[dict | None, list[str]]` (returns metadata dict and list of error messages)
   - `validate_metadata(data, expected_name) -> list[str]` (returns list of error messages)
   - `fetch_github_data(repo, token) -> dict` (latest release, last commit, open issues)
   - `compute_flags(metadata, github_data, today) -> list[str]`
   - `render_dashboard(rows, generated_at) -> str`
   - `main()` orchestrates the above and writes `README.md`
   Use only Python stdlib + `pyyaml`. CLI argument `--dry-run` writes to stdout instead of `README.md`.
5. **Write `tests/test_generate.py`** with the unit tests in §10.1. Add fixtures.
6. **Write `.github/workflows/refresh.yml`** (§9) and `.github/workflows/lint-and-test.yml`.
7. **Smoke-test against the real org.** Run `python generate.py --dry-run` locally with a valid GitHub token. Verify output. Iterate until clean.
8. **Add `pack-metadata.yaml` to 2-3 pilot packs** (e.g. `nebari-data-science-pack`, `nebari-llm-serving-pack`). Coordinate with their maintainers.
9. **Merge to main, let the cron run, verify the rendered dashboard.**
10. **Document the onboarding flow** in `pack-dashboard/CONTRIBUTING.md`: "To add your pack to the dashboard: (1) add `pack-metadata.yaml` to your repo following the schema; (2) PR a new line to `tracked-packs.yaml` here."

---

## 12. Acceptance Criteria

The implementation is complete when:

1. `python generate.py --dry-run` produces a valid markdown table for the configured tracked packs without errors.
2. The GitHub Actions workflow runs on daily cron and on manual dispatch, and successfully commits a regenerated `README.md` when (and only when) the rendered output has changed.
3. A pack with no `pack-metadata.yaml` shows up on the dashboard with the `metadata-missing` flag and partial data, without breaking the rest of the dashboard.
4. A pack with malformed `pack-metadata.yaml` shows up with the `metadata-invalid` flag and the specific error, without breaking the rest of the dashboard.
5. All flags in §7.4 trigger correctly given appropriate test fixtures.
6. Unit tests pass in CI on every PR.
7. The schema file is published in the repo and pack authors can validate locally with `check-jsonschema`.
8. `README.md` ends with the regeneration timestamp.

---

## 13. Out of Scope (deferred)

These are explicitly deferred. Do not implement them in v1.

- **Push triggers from pack repos** via `repository_dispatch`. Cron is enough. Add this only after a real complaint about freshness.
- **GitHub Pages site** with filtering/search. Markdown is enough until you have 30+ packs.
- **Cross-checking declared level against checklist state.** Trust the declared level for now.
- **Slack notifications** when flags trigger (e.g., a pack going stale). Useful eventually, premature now.
- **Historical level data.** The dashboard shows current state only. Audit trail lives in PRs.
- **Tracking community packs.** First-party only.
- **A separate "GA-only" or "demo-ready" view.** The flags handle this in v1; build filtered views if pre-sales asks for them.

---

## Appendix A: Cross-reference

- Maturity levels are defined in `nebari-dev/nebari-software-pack-template/docs/release-readiness-checklist.md`.
- The schema is owned by the dashboard repo (`schema/pack-metadata.schema.json`). Pack authors should pin to a schema version once we cut the first release of the dashboard.
- The `scope.standalone-supported` flag affects which checklist items apply per the release readiness checklist; the dashboard surfaces it but does not enforce it.
