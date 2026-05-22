# CI baseline

This file defines what "green CI" means for socialwarehouse at the current baseline, so a PR's CI status answers "did I break something new?" without the reviewer needing tribal knowledge.

**Last updated:** 2026-05-22 (post-v2.0.0 release commit `cd0d609`)

## Current baseline state

| | |
|---|---|
| Total tests | 353 |
| Passed | 345 |
| Skipped | 8 (all formally accepted — see below) |
| Failed | **0** |
| Warnings | 1 (non-blocking) |
| Wall time | ~18s (Test suite job) |
| Source | GitHub Actions run [26261203775](https://github.com/siege-analytics/socialwarehouse/actions/runs/26261203775) on commit `cd0d609` |

**Baseline mode: (a) clean + (b) formally-accepted skips.** Every test in the suite either passes or skips with a documented, ticketed reason. No real-bug failures live in the baseline. Any new failure on a PR is a real regression and must be investigated before merge.

## Formally accepted skips

All 8 skipped tests share a single root cause and are gated by an explicit pytest marker:

| Test | File | Skip marker | Reason |
|---|---|---|---|
| `TestNoCurrentPlanNotStale::test_only_future_plan` | `tests/unit/geo/test_paranoid_staleness.py` | `_REQUIRES_SU527` | SU#527 columns (`effective_from` / `effective_to`) not present in pinned SU version |
| `TestNoABPNotStale::test_no_abp` | (same file) | `_REQUIRES_SU527` | (same) |
| `TestStaleWhenPlanMismatches::test_abp_under_older_plan_is_stale` | (same file) | `_REQUIRES_SU527` | (same) |
| `TestStaleWhenPlanMismatches::test_abp_with_null_plan_and_current_plan_exists_is_stale` | (same file) | `_REQUIRES_SU527` | (same) |
| `TestNotStaleWhenPlansMatch::test_abp_under_current_plan_not_stale` | (same file) | `_REQUIRES_SU527` | (same) |
| `TestStateSenateAndHouseChambers::test_sldl_uses_state_house_chamber` | (same file) | `_REQUIRES_SU527` | (same) |
| `TestStateSenateAndHouseChambers::test_sldu_uses_state_senate_chamber` | (same file) | `_REQUIRES_SU527` | (same) |
| (one additional test in same file, same marker) | (same file) | `_REQUIRES_SU527` | (same) |

These will un-skip automatically when the SU pin is bumped past SU#527's migration.

## What "green" means

A PR is green and ready for merge when:

1. The `Test suite` job returns success.
2. The pytest summary line is `345+N passed, 8 skipped, 0 failed` (N ≥ 0; new tests are welcome and expected).
3. The `Docker build (core)` job either passes or is intentionally skipped per the workflow's filter conditions.
4. CodeRabbit and GitGuardian both return success.

A PR is red and **must not merge** when:

- Any test count in the "failed" column.
- The skipped count rises above 8 without a paired update to this doc explaining the new skip's ticket reference.
- The total pass count drops below `345 + (any merged-since baseline-update count)` — that means an existing test stopped running, not just stopped passing. Investigate the missing test.

## Re-snapshot cadence

This baseline should be re-snapshotted:

- After any change to the test runner, parallelism, or CI workflow.
- After the SU pin bump unlocks the 8 SU#527-gated tests.
- After any merged PR that adds ≥10 new tests (so the next reviewer has the updated `345 + N` floor).
- Quarterly as a no-trigger checkpoint to catch slow drift.

To re-snapshot: pick the latest successful CI run on `main`, copy its pytest summary line into the "Current baseline state" table above, update the date and commit SHA, audit the skip list if the count changed.

## Why this matters

Per #196: when CI noise grows (skips that don't have reasons; failures that everyone has learned to ignore), CI stops being a real "did I break something" signal. The leak-detection that surfaced SU#527 in PR #187 only worked because the surrounding baseline was disciplined enough to make the new red stand out. This doc keeps the discipline visible so future PRs can rely on the same signal quality.

## Cross-references

- Issue: [SW#196](https://github.com/siege-analytics/socialwarehouse/issues/196)
- Parent initiative: [SW#189](https://github.com/siege-analytics/socialwarehouse/issues/189) (template-readiness; closed v2.0.0)
- Originating-incident example: SU#527 (RedistrictingPlan migration drift surfaced via PR #187's `select_related` addition)
- The skip marker definition: `tests/unit/geo/test_paranoid_staleness.py:42` (`_REQUIRES_SU527`)
