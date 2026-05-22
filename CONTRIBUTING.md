# Contributing to socialwarehouse

## CI baseline

See [`docs/ci-baseline.md`](docs/ci-baseline.md) for the current definition of "green CI." Summary:

- **345 passed, 8 skipped (formally accepted), 0 failed** is the current baseline (as of v2.0.0).
- A PR is green when the `Test suite` job returns success AND skipped count is unchanged AND no test went missing.
- A PR is red when any test fails OR an unannotated new skip appears OR a test count drops.

Any new failure on a PR is a real regression and must be investigated before merge. The 8 skipped tests in the baseline are all gated by an explicit `_REQUIRES_SU527` pytest marker and will un-skip when the SU dependency pin is bumped past SU#527.

## Branch model

- `main` is the curated stable history. Tagged releases live here.
- `develop` is the integration branch. PRs target `develop`; `develop` promotes to `main` periodically (see merge-commit history for cadence).
- Feature branches name pattern: `feature/<concise-slug>`, `task/<NNN>-<slug>`, `chore/<slug>`, `release/<version>`, `ci/<slug>`.

## Pull requests

- Title: imperative mood, ≤ 70 chars.
- Body: what + why, with a `Refs:` trailer naming the issue or initiative.
- Sub-PRs of an umbrella: include the umbrella issue number in the body's "Refs:" trailer.
- Link to the design doc in `docs/designs/` when relevant.

## Release process

- Version declared in `pyproject.toml` AND `socialwarehouse/__init__.py` (keep in sync).
- Cut a release by: bumping both version strings (drop `-dev` suffix), merging the bump PR, tagging the resulting commit, pushing the tag, creating a GitHub release with notes. Then follow up with a `-dev`-suffix bump to the next version on `main`.
- See the v2.0.0 release (`cd0d609`) as the canonical example.

## Architectural principles

[`docs/architecture.md`](docs/architecture.md) captures the project-level architectural rules every design respects. The foundational one — **warehouse first, web app last** — fixes design order (Delta → PostGIS star schema → Django ORM) and sub-issue sequencing. Read it before designing anything that touches data.

## Skill / discipline references

This repo participates in the workspace's always-on rule discipline. Relevant rules:

- `writing-rules:6` — After a failure contradicts a documented Assumption, the originating ticket gets a Post-error revision block before the fix lands.
- `writing-rules:7` — Rules apply at session-scale, not just per-action. `Pairs with` relationships are dependencies, not hints.
- `writing-claims:1` — Grep before declaring a fix complete.

See `claude-configs-public/skills/` for the canonical rule files.

## Attribution

No AI / agent attribution in commits, PRs, or release notes. Per `_writing-prose-rules.md` and the repo's no-attribution policy.
