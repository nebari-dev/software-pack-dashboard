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

Copy that file into your pack repo, rename it to `pack-metadata.yaml`, delete the lines you don't need, and fill in the rest. The minimum required fields are `name`, `display_name`, `description`, `level`, `owner`, and `deprecated`.

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

- Maturity model and promotion criteria: [`MATURITY-MODEL.md`](MATURITY-MODEL.md)
- Detailed GA release checklist: [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md)
- Schema: [`schema/pack-metadata.schema.json`](schema/pack-metadata.schema.json)
- Annotated example: [`schema/pack-metadata.example.yaml`](schema/pack-metadata.example.yaml)
- Registry of tracked packs: [`tracked-packs.yaml`](tracked-packs.yaml)
