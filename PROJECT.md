# socialwarehouse

Data warehouse and data lake system for social, civic and social analysis.

## branch_integrity

Consumed by the develop-first promotion parity guard (branch-topology-check).
Model classification from the repo census (2026-09-29): develop is the
integration branch, main is production; promotion flows develop -> main.

```yaml
branch_integrity:
  model: develop-first
  integration: develop
  production: main
  staging: null
  promotion_order: [integration, staging, production]
```

Invariant: production is always an ancestor of integration (`main` subseteq
`develop`, i.e. `main..develop` behind_by == 0). Unpromoted forward work on
develop (ahead_by > 0) is normal; production carrying commits develop lacks is
the divergence the guard blocks.
