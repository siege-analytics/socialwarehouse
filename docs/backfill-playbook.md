# Historical Backfill Playbook

This playbook covers the procedure for backfilling multiple historical cycles (redistricting cycles, election years, Census vintages) into a SocialWarehouse deployment. It assumes partitioning (#328) and tiering (#329) are in place.

## When to backfill

- Initial deployment with historical data (most common)
- Adding a new data source that has historical coverage
- Recovering from data loss (complement to PITR — see `docs/production-operations.md` §2)
- Expanding the hot window to include more historical data

## Core principles

1. **Newest-first**: backfill the most recent cycle first so current-cycle queries are never blocked by historical work
2. **Dependency-ordered within cycle**: dimension tables before fact tables, parent facts before child facts
3. **Direct-to-tier**: historical cycles write directly to their target tier (warm or cold), skipping the hot tier
4. **Bounded parallelism**: maximum 2 backfill jobs in flight to avoid overwhelming the database
5. **Parity gate**: each cycle is not complete until parity checks pass between source and target

## Cycle sequencing

```
Current cycle (hot)  ← backfill first (already served by normal materialization)
N-1 cycle (hot)      ← backfill second
N-2 cycle (warm)     ← backfill third, write to warm tablespace
N-3 cycle (warm)     ← backfill fourth
...
N-5+ cycle (cold)    ← backfill last, write to cold tablespace
```

Why newest-first: if the backfill is interrupted or takes longer than expected, the most-queried data is already available. Users querying current-cycle data are never blocked.

## Source sequencing within a cycle

Within each cycle, load data in dependency order:

```
1. Dimension tables (no dependencies):
   - DimGeography
   - DimSurvey, DimCensusVariable
   - DimRedistrictingCycle
   - DimTime

2. Person dimension:
   - DimPerson (depends on DimGeography for FK)

3. Fact tables (depend on dimensions):
   - FactACSEstimate (depends on DimGeography, DimSurvey, DimCensusVariable)
   - FactDecennialCount (depends on DimGeography, DimSurvey, DimCensusVariable)
   - FactUrbanicity (depends on DimGeography)
   - FactElectionResult (depends on DimGeography)
   - FactPrecinctResult (depends on DimGeography)
   - FactRedistrictingPlan (depends on DimGeography, DimRedistrictingCycle)

4. Person-linked facts (depend on DimPerson):
   - FactVoteHistory (depends on DimPerson)
   - FactPersonScore (depends on DimPerson)
```

## Direct-to-tier writes

For cycles that belong in the warm or cold tier, create the partition in the target tablespace:

```sql
-- Create a warm partition directly in warm tablespace
CREATE TABLE sw_fact_vote_history_2019
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2019-01-01') TO ('2020-01-01')
    TABLESPACE warm_ts;

-- Create a cold partition directly in cold tablespace
CREATE TABLE sw_fact_vote_history_2016
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2016-01-01') TO ('2017-01-01')
    TABLESPACE cold_ts;
```

This avoids the write-then-move pattern, which doubles I/O for historical data.

## Bounded parallelism

Configure Dagster to run at most 2 backfill jobs concurrently:

```python
from dagster import define_asset_job

backfill_job = define_asset_job(
    name="historical_backfill",
    tags={"dagster/max_concurrent": "2"},
)
```

For manual backfill via `swh` CLI or SQL scripts, use a semaphore or job queue to enforce the limit. Two concurrent jobs balance throughput against database load — more than 2 causes WAL write contention and checkpoint pressure.

## Per-cycle parity gate

After backfilling each cycle, verify parity before proceeding to the next:

```sql
-- Count rows in the source (Delta Lake via Spark)
-- Compare with PostGIS partition
SELECT count(*) FROM sw_fact_vote_history_2020;

-- Record in parity check table
INSERT INTO sw_monitoring_parity_check
    (source_tier, target_tier, table_name, source_count, target_count, is_match)
VALUES
    ('delta', 'postgis', 'sw_fact_vote_history_2020', 15234567, 15234567, true);
```

Use `swh reconcile` to verify schema alignment before and after backfill.

**Parity gate rule**: do NOT start the next cycle's backfill until the current cycle's parity checks pass for all tables. A failed parity check means data was lost or corrupted during load — investigate before proceeding.

## Worked example: backfilling 3 historical cycles

**Scenario**: New SW deployment for Texas. Current cycle is 2020 redistricting. Need to backfill 2010 redistricting cycle plus election years 2016-2019.

**Step 1**: Verify infrastructure

```bash
swh doctor              # all checks pass
swh tier-status         # partitions exist, tiers configured
swh reconcile           # no schema drift
```

**Step 2**: Create partitions in target tablespaces

```sql
-- 2019 data → warm tier
CREATE TABLE sw_fact_vote_history_2019
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2019-01-01') TO ('2020-01-01')
    TABLESPACE warm_ts;

-- 2018 data → warm tier
CREATE TABLE sw_fact_vote_history_2018
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2018-01-01') TO ('2019-01-01')
    TABLESPACE warm_ts;

-- 2016-2017 data → cold tier
CREATE TABLE sw_fact_vote_history_2016
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2016-01-01') TO ('2017-01-01')
    TABLESPACE cold_ts;

CREATE TABLE sw_fact_vote_history_2017
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2017-01-01') TO ('2018-01-01')
    TABLESPACE cold_ts;
```

**Step 3**: Backfill newest-first

```bash
# Cycle 1: 2019 (warm) — 2 jobs max
swh materialize-electoral persons --vintage 2019
swh materialize-electoral scores --vintage 2019
# Verify parity
swh reconcile

# Cycle 2: 2018 (warm)
swh materialize-electoral persons --vintage 2018
swh materialize-electoral scores --vintage 2018
swh reconcile

# Cycle 3: 2016-2017 (cold)
swh materialize-electoral persons --vintage 2016
swh materialize-electoral persons --vintage 2017
swh reconcile
```

**Step 4**: Verify final state

```bash
swh tier-status          # all partitions in correct tier
swh audit-indexes        # no bloated indexes from bulk load
swh reconcile            # no schema drift
```

**Step 5**: Reduce indexes on warm/cold partitions

```sql
-- Drop non-essential indexes on cold partitions
-- (keep PK and unique constraints only)
-- Use swh audit-indexes to identify candidates
```

## Monitoring during backfill

- Watch `sw_monitoring_materialization` for parity failures
- Watch PostgreSQL WAL generation rate (`pg_stat_wal` or CNPG metrics)
- Watch disk space on target tablespaces
- If WAL generation exceeds 1 GB/hour sustained, reduce parallelism to 1

## Recovery from failed backfill

If a backfill job fails mid-cycle:

1. Check `sw_monitoring_materialization` for the last successful asset
2. Truncate the partially-loaded partition: `TRUNCATE sw_fact_vote_history_2019;`
3. Re-run the backfill for that cycle from the beginning
4. Re-verify parity

Do NOT attempt to resume a partial load — truncate and restart. Partial data is worse than no data.
