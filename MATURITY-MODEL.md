# Nebari pack maturity model

This document defines the four active maturity levels a Nebari pack can declare in its `pack-metadata.yaml`, plus the `deprecated` status. The dashboard reads the declared level and uses it to drive a few automated flags - but the **declared level is trusted**. The dashboard does not verify your pack actually meets the criteria below; that's on you and your reviewers.

> If a pack's declared level looks wrong to pre-sales, the fix is a conversation with the pack owner, not a dashboard change.

## At a glance

| Level | Stability | Audience | Breaking changes | Owner requirement | Dashboard flags |
|---|---|---|---|---|---|
| **Experimental** | None | Pack author, contributors | Expected, unannounced | `owner` only | none specific |
| **Alpha** | Low | Internal teams, design partners with hand-holding | Expected, ideally noted in CHANGELOG | `owner` only | none specific |
| **Beta** | Medium | Pre-sales demos, early-adopter customers | Possible but unusual; announce in release notes | `owner` only | none specific |
| **GA** | High | Production customers | None within a major version | `owner` AND `product_owner` (non-null) | `no-product-owner` if `product_owner` is null |

All non-deprecated levels share two flags:
- `stale` - default branch has had no commits in 90 days
- `metadata-missing` / `metadata-invalid` - the pack-metadata.yaml file is absent or doesn't pass schema validation

## Experimental

**Intent:** A spike. A proof of concept. The "I'm exploring whether this idea has legs" stage.

**Use it when:**
- The pack might be deleted next week with no announcement.
- You haven't decided what the interface looks like.
- You're not yet confident the underlying upstream chart is stable enough to wrap.

**Don't use it for:**
- Anything pre-sales should show a customer.
- Anything another team should build against.

**Exit criteria → Alpha:**
- The pack installs and reaches Ready in at least one happy-path scenario.
- The README explains what the pack does and who it's for, even at a sketch level.
- You're committed to keeping the pack alive for at least the next two months.

## Alpha

**Intent:** Working software that we're willing to show internally, with caveats.

**Use it when:**
- The pack installs and runs but the surface area is still in flux.
- Pre-sales can demo it to design partners as long as the rough edges are pre-briefed.
- Customers should not yet deploy it themselves.

**Exit criteria → Beta:**
- All checkboxes under "Documentation", "Examples and Values", and "Testing" in the [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md) are at least partially addressed (most boxes checked, gaps explicitly noted).
- The pack has a CHANGELOG.
- The chart is publishable to `nebari-dev.github.io/helm-repository` and has at least one pre-release tag.
- A standalone-install path exists (or is explicitly out of scope, set `scope.standalone-supported: no`).

## Beta

**Intent:** Feature-complete and stabilizing. Customers can deploy with a reasonable expectation of working, but the contract is "expect rough edges, file issues."

**Use it when:**
- The pack works end-to-end with a real Nebari deployment.
- Breaking changes still happen but are announced in release notes.
- Pre-sales can confidently demo it.
- Early-adopter customers can self-serve install with documentation.

**Exit criteria → GA:**
- Every checkbox in the [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md) is checked.
- A named product owner has signed off on the acceptance criteria.
- Chart version is `1.0.0`.
- Set `product_owner:` in pack-metadata.yaml (non-null) before promoting.

## GA

**Intent:** Production-ready. Customers deploy this without a hand-hold. Backwards compatibility within a major version.

**Use it when:**
- The full [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md) is signed off.
- There is a named `product_owner` (not just an `owner`).
- You're prepared to support customers running this in production and to maintain backwards compatibility through subsequent 1.x releases.

GA packs that lose their product owner should trip the dashboard's `no-product-owner` flag immediately, which is your cue to either name a new product owner or move the pack back to Beta.

## Deprecated (orthogonal status)

Deprecation is not a level - it's a flag (`deprecated: true`) that any pack at any level can have. A deprecated pack:

- Must have a `sunset_date` set in pack-metadata.yaml (ISO date).
- Is moved out of the main dashboard table into a separate "Deprecated packs" table at the bottom, so pre-sales doesn't accidentally pitch it.
- No longer trips the `stale` flag (we don't expect deprecated packs to ship commits).

**Use deprecation when:**
- The pack is being replaced by a different one.
- The underlying upstream project is dead and we're not wrapping a fork.
- The customer use case the pack served no longer exists.

**Don't use deprecation as a substitute for deletion.** If a pack was never used and never will be, just remove it from `tracked-packs.yaml` and archive the repo.

## Promoting (or demoting) a pack

1. Update `level:` in your pack's `pack-metadata.yaml`.
2. Optionally set `last_promoted_at:` (ISO date) and `last_promoted_pr:` (PR number) for audit trail.
3. If promoting to GA, set `product_owner:` to a non-null GitHub username.
4. Merge to your default branch.

The dashboard picks the change up on the next hourly refresh; no PR to the dashboard repo is needed.

Demotions work the same way. There's no shame in moving from Alpha back to Experimental if you realize you got ahead of yourself.
