# Contributing to the Nebari pack dashboard

This repo generates `README.md` (the dashboard you see on the repo's front page) from a registry of tracked packs plus each pack's `pack-metadata.yaml`. The dashboard refreshes every hour, on any push to this repo, and on demand via the `Refresh pack dashboard` workflow.

There are three things you might want to do here.

---

## I'm a pack author. How do I get my pack on the dashboard?

You'll do this once per pack and then forget about it. The data flow is one-way: the dashboard pulls from your repo, you never push to the dashboard.

### Step 1: Add `pack-metadata.yaml` to your pack repo

In **your pack's repo**, on the **default branch**, at the **root**, add a file called `pack-metadata.yaml`.

A fully commented template with every field, when it's required, what the allowed values are, and what each field controls on the dashboard, lives here:

> [`schema/pack-metadata.example.yaml`](schema/pack-metadata.example.yaml)

Copy that file into your pack repo, rename it to `pack-metadata.yaml`, delete the lines you don't need, and fill in the rest. The minimum required fields are `name`, `display_name`, `level`, `owner`, and `deprecated`. (`description` is optional - the dashboard's Description column is sourced from the GitHub repo description, not this file.)

### Step 2: Validate locally before pushing

The dashboard won't fail loudly if your file is broken - it'll just render your row with a `⚠️ metadata-invalid` flag and the specific error in the Notes column. Catching the problem locally is faster:

```bash
pip install check-jsonschema
check-jsonschema --schemafile https://raw.githubusercontent.com/nebari-dev/software-pack-dashboard/main/schema/pack-metadata.schema.json pack-metadata.yaml
```

Should print `ok -- validation done`. If it doesn't, fix the errors it reports.

### Step 3: Commit and merge to your default branch

Open a PR in your pack repo with the new file, merge it. That's the moment the dashboard starts reading from your repo.

### Step 4: Add your repo to `tracked-packs.yaml` here

Open a PR against this repo (`nebari-dev/software-pack-dashboard`) adding one line to [`tracked-packs.yaml`](tracked-packs.yaml):

```yaml
packs:
  ...
  - repo: nebari-dev/your-pack-repo
```

On merge, the dashboard regenerates within a few seconds and your row appears.

### What happens after that?

- The dashboard refreshes every hour (cron at `:00 UTC`).
- You can force a refresh any time via Actions → "Refresh pack dashboard" → "Run workflow", or:
  ```bash
  gh workflow run "Refresh pack dashboard" --repo nebari-dev/software-pack-dashboard
  ```
- To change your pack's status (e.g. promote alpha → beta, change owner, add demo notes, mark deprecated), edit `pack-metadata.yaml` in **your** pack repo. **No PR to this repo is needed** - the regenerator picks the change up on the next cron tick.

### Common gotchas

- The file must be at the **repo root**, not in `charts/` or `docs/` or anywhere else.
- It must be on the **default branch** (typically `main`). Branches are not consulted.
- `name:` must match your GitHub repo name exactly. A mismatch produces `metadata-invalid`.
- `deprecated: true` requires `sunset_date`. The dashboard moves deprecated packs into a separate table at the bottom, so pre-sales doesn't pitch them.
- `level: ga` requires a non-null `product_owner`. The `⚠️ no-product-owner` flag exists specifically to catch this.

---

## How should I tag releases?

Packs version their releases with [EffVer](https://jacobtomlinson.dev/effver/) (Effort Versioning): `vMACRO.MESO.MICRO`. The three numbers signal how much work an upgrade will cost the people consuming your pack, not how big the change felt to write:

- **MICRO** - a drop-in. Bug fixes and additive features that need no action from existing users.
- **MESO** - some effort. A larger fix or a small breaking change that needs a little adoption work.
- **MACRO** - significant effort. A breaking overhaul; users should plan time to upgrade.

While a pack is pre-1.0, EffVer collapses to `0.MACRO.MICRO`: the leading `0` marks the in-development phase, a breaking or significant change bumps the middle number (`0.2.0`), and a drop-in fix bumps the last (`0.1.1`).

### Tag format

- **Always prefix with `v`**: `v0.1.0`, `v1.2.0`. Do not prefix with the repo name (`nebari-foo-pack-0.1.0`) or anything else. One repo, one tag scheme.
- Tags must be three numeric segments. Prereleases use a SemVer-style suffix (`-alpha.N`).

### Maturity maps to the version like this

| Maturity | Tag shape | Example |
|---|---|---|
| Alpha | `v0.1.0-alpha.N` (prerelease) | `v0.1.0-alpha.3` |
| Beta | bare `v0.x.y` (the whole `0.x` line) | `v0.1.0`, `v0.2.1` |
| GA | `v1.0.0` and up | `v1.0.0`, `v1.1.0` |

Two things that trip people up:

- **Beta is the entire `v0.x.y` line, not a single tag.** Once you ship `v0.1.0` you keep versioning within `0.x` - a fix is `v0.1.1`, a breaking change is `v0.2.0`. All still beta. Leaving `0.x` for `v1.0.0` is the deliberate "this is stable now" signal.
- **Maturity is whatever `level` says in `pack-metadata.yaml`, not what the tag implies.** The version string usually lines up with it, but `level` is the source of truth - don't infer a pack's maturity from its tag. And don't renumber a published higher version downward just to match a label: fix the `level` instead, or cut the next release at a corrected number.

The full maturity model and promotion criteria live in the [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md).

---

## I'm not a pack author but want to change the generator, schema, or output

1. Make the change locally.
2. Run the tests: `python -m pytest tests/`.
3. Smoke-test the generator against the real org:
   ```bash
   GITHUB_TOKEN=$(gh auth token) python generate.py --dry-run
   ```
4. Open a PR. CI runs the tests and the dry-run.

Backwards compatibility for schema changes: every field tracked packs already use must keep working, or the existing packs will all start flagging `metadata-invalid` in unison. Either keep both old and new fields readable, or roll the change out as a coordinated PR train across the affected pack repos.

---

## I just want to read the dashboard

You're in the wrong place. Go look at [`README.md`](README.md). The whole point of this repo is that you should never need to come into it as a reader.

---

## Reference

- Maturity model, promotion criteria, and full release checklist: [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md)
- Schema: [`schema/pack-metadata.schema.json`](schema/pack-metadata.schema.json)
- Annotated example: [`schema/pack-metadata.example.yaml`](schema/pack-metadata.example.yaml)
- Registry of tracked packs: [`tracked-packs.yaml`](tracked-packs.yaml)
