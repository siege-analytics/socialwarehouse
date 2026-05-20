# Template-readiness G / SW#195 — Quickstart + template-init (design)

**Status:** Design v1. Awaiting maintainer answers on four open questions.

**Parent:** SW#189 (template-readiness initiative).
**Blocked by:** all of A, B, C, D, E, F.

## Goal

Turn SocialWarehouse from "the repo a particular team works on" into "a template another team can adopt." That requires three things:

1. **Quickstart doc** — a new contributor goes from `git clone` to a working dev instance with seeded RI data in under 30 minutes.
2. **`seed_demo` command** — loads one state's data across the four domains (boundaries + ACS + QCEW + NCES) so the dev instance is immediately useful.
3. **Template-init mechanism** — a clone-and-rename step that produces a jurisdiction-specific instance without forking core code.

## Three deliverables

### G.1 — Quickstart doc (`docs/quickstart.md`)

Documents the path from `git clone` to running dev server with RI data loaded. Sections:

- **Prereqs:** PostgreSQL + PostGIS, Python 3.11+, optional Redis (Celery). Concrete install commands per OS (macOS Homebrew, Ubuntu apt, Windows WSL).
- **Setup:** clone, create venv, `pip install -e .`, `cp .env.example .env`, edit DB credentials, `python manage.py migrate`, `python manage.py createsuperuser`.
- **Seed:** `python manage.py seed_demo --state RI`. (G.2 delivers this command.)
- **Verify:** `python manage.py runserver`, hit `/api/geo/boundary?type=cd&geoid=4400` and confirm RI's at-large CD comes back.
- **Common problems:** PostGIS extension not enabled, Census API key not set for ACS reload, etc.

Target: a contributor following the doc gets a working dev instance in under 30 minutes (informally measured by asking a few new-to-SW people).

### G.2 — `seed_demo` management command

Wraps the per-domain seed commands in a single one-state load:

```bash
python manage.py seed_demo --state RI [--vintage 2020] [--skip=econ,civic]
```

For the named state, runs:
- `assign_boundaries --state RI --year 2020` (per-state subset)
- `load_acs --state RI --vintage 2019-2023 --tables B01001,B19013,B25001,B17001` (small variable subset)
- `load_qcew --state RI --vintage 2024Q3 --naics-depth=2`
- `load_nces --state RI --vintage 2023-24`

Idempotent; safe to re-run. Uses `--skip` for partial loads when a domain isn't wanted (e.g., for a fast "just boundaries + ACS" dev setup).

State choice for default: **Rhode Island.** Smallest state by area, only 2 CDs, one MSA, ~25 school districts, ~250 census tracts. Loads in minutes; demos every feature.

### G.3 — Template-init mechanism

Three candidate shapes (Q1 below picks one):

- (a) **Cookiecutter template.** `cookiecutter gh:siege-analytics/socialwarehouse` produces a renamed jurisdiction-specific instance. Standard Python pattern.
- (b) **`python manage.py template_init` command.** Interactive prompt asks for project name, target state(s), domain subset, then runs migrations + seed_demo.
- (c) **Plain `make init` Makefile target.** Shell-script-level; simpler than cookiecutter; less guidance.

Each produces:
- A renamed Django project + app (e.g., `myorg-warehouse` instead of `socialwarehouse`).
- A populated `.env` with the chosen state(s) + DB connection.
- A first seed run.

## Four open questions for the maintainer

### Q1. Template-init shape — (a), (b), or (c)?

- (a) Cookiecutter — most discoverable; requires the user to install cookiecutter; produces a separate repo on first use.
- (b) `manage.py template_init` — keeps the template living in this repo; works without separate tooling install; less polished for the "first-time user" case.
- (c) Makefile — simplest; least guidance; assumes Unix-y dev env.

**Recommendation: (b).** It keeps the template in-repo (easy to iterate on the template itself) and doesn't require cookiecutter as a dep. The first-time-user UX is slightly worse than (a), but the cost of (a) is maintaining a separate cookiecutter repo + keeping it in sync.

### Q2. Default seed state — RI, DC, or HI?

- **RI** — 2 CDs, ~1.1M population, ~250 tracts, single MSA, ~38 cities/towns. Fast to load; demos every feature.
- **DC** — Compact; weird because no state representation; ~700K population.
- **HI** — Two CDs but archipelago geography stress-tests projections (relevant after M5 #185 follow-up).

**Recommendation: RI.** Simplest geometry; cleanest set of every feature. DC's "no state rep" makes it a poor demo for political features. HI is good for projection-stress later but not for the quickstart.

### Q3. Quickstart target time — 30 minutes or 1 hour?

30 minutes is aspirational; 1 hour is comfortable. Sets the bar for how much polish the prereqs section needs.

**Recommendation: 1 hour.** 30 minutes is unrealistic on a cold dev machine (PostGIS install alone takes 15-20 minutes on macOS with Homebrew). 1 hour with the explicit understanding that PostGIS install is the long pole is more honest.

### Q4. Multi-state seed packs — ship any?

- (a) **RI only.** Template ships with RI seed; users add other states themselves.
- (b) **RI + one large state (CA or TX).** Demos at scale.
- (c) **Configurable state pack via `seed_demo --states RI,CA,TX`.** Lets the user pick.

**Recommendation: (c).** The command already needs to accept a state arg; allowing multiple is one-line code change. Default to RI; users opt into multi-state via flag.

## Out of scope

- Production deployment guides (Heroku / Render / AWS specifics).
- Hosted demo at `template-demo.siege-analytics.com` or similar.
- A "template gallery" showing what others have built.
- CI hardening beyond what already exists in SW.

## Sequencing

- This PR (design v1) → maintainer Q1-Q4.
- Implementation gated on A through F all landing (quickstart that initializes a half-finished template is worse than no quickstart).
- Implementation PR ships all three deliverables (G.1 + G.2 + G.3) together — they only make sense as a set.

## References

- Parent: SW#189
- Each of A, B, C, D, E, F's seed conventions feeds into G.2's `seed_demo` command.
- Cookiecutter: cookiecutter.readthedocs.io (if Q1 picks (a))
