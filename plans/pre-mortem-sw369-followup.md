---
ticket_refs:
  - siege-analytics/socialwarehouse#369: schema ticket, PR #371 open
propagation-deferred: findings will be posted as a PR #371 comment once the fix is pushed
---

# Pre-mortem: PR #371 CodeRabbit-triggered follow-up fix (siege-analytics/socialwarehouse#369)

Risks considered before applying the CodeRabbit-driven fix to already-merged-pending PR #371.

- **Tiger 1: fixing the exposure_class enum gap could reject legitimate existing rows on migration apply**
  **Severity:** MEDIUM
  **Mitigation:** the new `ck_evpart_exposure_class_valid` CheckConstraint only rejects rows whose `exposure_class` is NOT one of the two declared choices. Since the field's `default="public_actor"` has been in force since this PR's first migration (no prior release shipped without it), and the CharField's own `choices=` already prevented the ORM/admin from ever writing an undeclared value through normal paths, no legitimate existing row is expected to violate the new constraint. This is a net-new PR (not yet merged to develop), so there is no production data to migrate against yet -- the risk is theoretical for this PR specifically, real for any future PR that reuses this pattern without re-checking.

- **Tiger 2: scope creep -- fixing CodeRabbit's finding #2 (event_type/subtype matching) would touch all 4 event subtypes, not just this PR's ticket**
  **Severity:** LOW (risk of NOT doing something, not of doing it)
  **Mitigation:** explicitly NOT fixing finding #2 in this PR. It is the same pre-existing, pattern-wide gap my own hostile review already identified and deferred as a follow-up ticket candidate (see `.hostile-review-sw369-narrative-event-exposure-class.md` MINOR finding "No enforcement that Event.event_type matches the attached subtype"). CodeRabbit's independent discovery of the same gap validates the finding rather than requiring a new fix; will reply to CodeRabbit's PR comment with this reasoning and file the follow-up ticket as promised in the original PR body.

- **Tiger 3: the attribution-wording fix in `.self-review-*.md` could be read as retroactively hiding review provenance**
  **Severity:** LOW
  **Mitigation:** rewording the Role declarations section's vendor-model self-identification to role-neutral phrasing (e.g. "Author role: implementer", "Reviewer role: self-review pass", "Hostile reviewer role: independent adversarial pass") preserves the same structural meaning (who did what, in what capacity) without the prohibited wording, consistent with this workspace's `_output-rules.md` Attribution policy for committed artifacts. Not deleting or obscuring the review's substance, only its self-referential phrasing.

- **Tiger 4: re-verifying against a torn-down or drifted local Postgres**
  **Severity:** MEDIUM
  **Mitigation:** the isolated `sw369-testpg` Docker container from the original implementation is still running (never torn down this session); will re-migrate from a clean `test_socialwarehouse` DB state and use `pytest --create-db` (not `--reuse-db`) for the final verification run, per the Tiger 5 lesson already learned earlier in this same ticket's original pre-mortem.
