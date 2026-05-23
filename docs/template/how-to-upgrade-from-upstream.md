# How to upgrade your instance project from upstream SocialWarehouse

Once you've forked SW and customized it, you'll want to periodically absorb upstream improvements — new asset factories, new boundary types, new dim/fact patterns, security fixes, dependency bumps — without losing your instance-specific changes. This guide covers the soft-fork upgrade workflow.

If your fork has zero upstream-tracking and you don't want to absorb upstream improvements, you can skip this — but expect to re-discover bugs SW fixes and to drift from the broader template's contract over time.

## Mental model

Your instance project relates to upstream SW in three ways:

| Category | Examples | Upgrade behavior |
|---|---|---|
| **Inherited verbatim** | `delta/config.py`, `orchestration/asset_factories.py`, `orchestration/resources.py`, `warehouse/models/dimensions.py` core dims | Pull from upstream periodically; rare conflicts |
| **Forked + diverged** | Boundary catalog (geography swap), Django app labels (rename), seed_demo command | Stable divergence; cherry-pick non-conflicting upstream changes |
| **Instance-owned** | Your new domains, your API endpoints, your settings, your asset modules | Never pulled from upstream |

The upgrade goal: pull the "inherited verbatim" set, evaluate the "forked + diverged" set per upstream change, leave "instance-owned" alone.

## Setup (once, after forking)

Add SW as an `upstream` remote in your instance project:

```bash
cd <your-warehouse>
git remote add upstream git@github.com:siege-analytics/socialwarehouse.git
git fetch upstream
```

Confirm both remotes:

```bash
git remote -v
# origin    git@github.com:<your-org>/<your-warehouse>.git (fetch + push)
# upstream  git@github.com:siege-analytics/socialwarehouse.git (fetch + push)
```

## The upgrade workflow

### Step 0 — Pre-author inventory

Before any upgrade, post a pre-author inventory to the instance project's tracker:

```markdown
## Pre-author inventory — upstream sync from SW <upstream-ref>

### Inputs read
- Upstream changelog / release notes: <link>
- Upstream commits between <last-sync-ref> and <upstream-ref>:
  `git log --oneline <last-sync-ref>..upstream/main`
- This guide

### Knowledge requirements
- Which upstream commits touch files in the "Inherited verbatim" set?
- Which touch files in the "Forked + diverged" set?
  (these require per-commit decision)
- Are any breaking changes flagged in upstream's release notes?
  (API changes to factories, resource fields, asset key formats)
- Does upstream introduce new template-readiness tracks (B/C/D/E/F/G+)
  that your instance project should adopt?

### Contact-point measurements
- Run upstream's tests against the upstream code (sanity check)
- Run YOUR test suite after each conflict resolution
- Run `dagster dev -m <your-warehouse>.orchestration` after the sync
  to verify asset graph loads

### Surface areas
- Migrations: any upstream Django migration that adds columns to
  shared models (DimGeography, Address, ABP) needs to flow into
  your instance project; conflicts likely if you've extended those
  models
- pyproject deps: upstream version bumps may collide with your
  pins; review the lockfile change
- Settings: any new env var upstream introduces needs to land in
  your `.env.example` + ops env

### Hypothesis
"After this sync, my instance project will be at upstream parity
on the {inherited_verbatim} set, will have resolved {N} conflicts in
the {forked_diverged} set, and will have absorbed {M} upstream commits.
My instance-owned code is unchanged."
```

### Step 1 — Choose the upstream reference to sync to

Don't sync to `upstream/main` blindly. Sync to a specific tag or commit so the upgrade is reproducible:

```bash
git fetch upstream --tags
git log --oneline upstream/main | head -20
# Pick a tag (e.g. v2.3.0) or a specific commit (e.g. 463d014)
```

For most cases: sync to the latest upstream release tag, not `main` (which may have unreleased work).

### Step 2 — Create a sync branch

```bash
git checkout main   # or develop, per your branch convention
git pull origin main
git checkout -b sync/upstream-<ref>
```

### Step 3 — Merge upstream

```bash
git merge upstream/<ref> --no-ff --no-commit
```

`--no-ff` to keep a merge commit (audit trail of the sync).
`--no-commit` to inspect conflicts before committing.

### Step 4 — Resolve conflicts by category

For each conflicted file:

#### Category A: Inherited verbatim — take upstream

```bash
git checkout --theirs <file>
git add <file>
```

Examples: `socialwarehouse/delta/config.py` (if you didn't customize it), `socialwarehouse/orchestration/asset_factories.py`, `pyproject.toml` (resolve carefully — see Step 5).

#### Category B: Forked + diverged — manual merge

Open the file in your editor; resolve conflicts per-hunk. Keep your divergence (e.g. your boundary catalog in `Address._BOUNDARY_TYPES`); take upstream's new methods if they don't conflict with your overrides.

```bash
# After manual edit
git add <file>
```

#### Category C: Instance-owned — should not conflict

If a conflict appears in instance-owned files (your new domains, your settings overrides), something is wrong. Either:

- Upstream added a file with the same path (rare; investigate)
- You renamed an upstream file but forgot to remove the upstream version (your initial fork+rename was incomplete; re-check Step 2 of `how-to-fork-and-rename.md`)

### Step 5 — Carefully resolve `pyproject.toml`

This always conflicts because both you and upstream version-bump it. Resolution pattern:

```toml
# Take upstream's:
# - version (their canonical version)
# - dependencies that you didn't override
# - new optional-extras they added

# Keep your:
# - [project] name (your instance name, NOT 'socialwarehouse')
# - [tool.setuptools.packages.find] include (your renamed package)
# - any dep version overrides you set deliberately
```

Test the resolved pyproject:

```bash
pip install -e ".[full]" --upgrade
```

### Step 6 — Run migrations

Upstream Django migrations need to apply on your instance project's DB. If upstream added a column to `DimGeography` and you've extended `DimGeography` in your instance:

```bash
python manage.py makemigrations --dry-run
# Should show no new migrations needed if upstream's migration was absorbed cleanly

python manage.py migrate
# Should apply the upstream migrations on top of your divergent ones
```

If `makemigrations` shows pending migrations, you may need a manual data migration to reconcile your local schema with upstream's.

### Step 7 — Run your test suite

```bash
pytest

# Plus orchestration:
pytest tests/orchestration/

# Plus a Dagster smoke test:
dagster dev -m <your-warehouse>.orchestration
# Verify asset graph renders + a representative asset materializes
```

If tests fail: the upstream change broke a contract your instance relies on. Either:

- File an issue upstream (if the change is unintentional or under-documented)
- Pin to the previous upstream version (`git reset --hard <last-known-good>`) and skip this sync cycle
- Adapt your instance code to the new upstream contract (most common; check upstream's release notes for migration guidance)

### Step 8 — Commit + PR

```bash
git commit -m "chore: sync upstream SocialWarehouse @ <ref>

Absorbs upstream commits <range>. Resolved conflicts:
- pyproject.toml (took upstream version, kept instance name)
- Address.py (kept instance boundary catalog, took new F11 method)
- ...

Tests pass. Dagster asset graph loads.
"

git push -u origin sync/upstream-<ref>
gh pr create --base main ...
```

The PR is for your instance project's review process; reviewers should focus on the conflict resolutions (Category A is mechanical; Category B is where bugs land).

## How often to sync

Recommended cadence:

- **At every upstream release tag** — if upstream releases monthly, sync monthly. Smaller per-sync diffs = easier review.
- **Always at major version bumps** — `v2.x` → `v3.x` likely has breaking changes; don't skip.
- **Within 1 week of security fixes** — upstream tags security-relevant releases; treat as urgent.

Don't let your fork drift more than 6 months from upstream. Beyond that, the conflict-resolution cost compounds and the upgrade becomes its own initiative.

## When NOT to sync

- **Upstream is in active flux** (e.g. mid-template-readiness work that hasn't stabilized) — wait for the dust to settle
- **You're in the middle of your own major refactor** — don't compound merge complexity
- **The upstream change is irrelevant to your instance** (e.g. US-Census-specific work and you're a UK instance) — skip with a note in your sync log

## What about upstream PRs that affect "forked + diverged" files heavily

If upstream lands a big change to a Category B file (e.g. they re-architect `Address` significantly), you have three options:

1. **Adopt the upstream architecture in full** — undo your divergence, re-apply your geography customization on top of upstream's new shape. Cleanest long-term; expensive short-term.
2. **Skip the upstream change** — pin to the pre-change upstream ref; absorb everything else. Works once or twice; long-term you drift unsustainably.
3. **Engage upstream** — open an issue / discussion explaining your instance's constraint; ask if there's a path to make the upstream change instance-friendly (extension point, hook, config). Often the right move for instance-shape concerns the upstream maintainer didn't consider.

## Sync log

Maintain a `docs/sync-log.md` in your instance project tracking sync history:

```markdown
# Upstream sync log

## 2026-09-15 — synced to upstream v2.5.0 (commit abc1234)
- Took upstream's new postgis_materialization_asset COPY threshold (SW#280)
- Kept instance UK boundary catalog
- Pyproject: bumped dagster pin to match upstream; kept instance celery override
- Tests pass; dagster smoke passes
- PR #42 in instance repo
```

The sync log is the audit trail when a regression appears 6 months later and you need to identify which sync introduced it.

## See also

- [README.md](README.md) — template overview
- [how-to-fork-and-rename.md](how-to-fork-and-rename.md) — prerequisite (sets up `upstream` remote)
- [how-to-swap-geography.md](how-to-swap-geography.md) + [how-to-add-a-new-domain.md](how-to-add-a-new-domain.md) — produce the divergence you'll be resolving against
- SW release tags: https://github.com/siege-analytics/socialwarehouse/releases
- SW changelog: [`CHANGELOG.md`](../../CHANGELOG.md) (when it exists; see SW#xxx)
