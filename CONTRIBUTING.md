# Contributing to the Nebari pack dashboard

This repo generates `README.md` from a registry of tracked packs plus each pack's `pack-metadata.yaml`. There are two ways to contribute.

## Add your pack to the dashboard

1. In your pack's repository, add a `pack-metadata.yaml` at the repo root on the default branch. Use the schema at [`schema/pack-metadata.schema.json`](schema/pack-metadata.schema.json). The required fields are `name`, `display_name`, `description`, `level`, `owner`, `deprecated`. Validate locally with:

   ```bash
   pip install check-jsonschema
   check-jsonschema --schemafile schema/pack-metadata.schema.json pack-metadata.yaml
   ```

2. Open a PR to this repo adding one line to `tracked-packs.yaml`:

   ```yaml
   packs:
     - repo: nebari-dev/your-pack-repo
   ```

That's it. The next cron run (or a manual `workflow_dispatch`) will pick up your pack and render it on the dashboard.

## Update your pack's status

To change your pack's level, owner, demo notes, or any other field shown on the dashboard, edit `pack-metadata.yaml` in your pack's repo. No PR to this repo needed; the regenerator picks up changes on the next cron.

## Change the generator or the schema

For changes to `generate.py`, the schema, or the rendered output:

1. Make the change locally.
2. Run the tests: `python -m pytest tests/`.
3. Smoke-test the generator: `GITHUB_TOKEN=$(gh auth token) python generate.py --dry-run`.
4. Open a PR. CI runs the tests and a dry-run.

## Maturity levels

Levels (`experimental`, `alpha`, `beta`, `ga`) are defined in the [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md). The dashboard does not verify that a pack's declared level matches checklist state; trust the declared level and rely on pre-sales review to catch drift.
