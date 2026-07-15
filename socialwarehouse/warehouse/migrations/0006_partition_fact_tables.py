"""Declarative range partitioning for high-volume fact tables (#328).

Partitions three tables:
- sw_fact_redistricting_plan: by cycle_id (FK to DimRedistrictingCycle)
- sw_fact_vote_history: by election_date (per year)
- sw_fact_person_score: by scored_at (per year)

Forward-only: creates partitioned tables, migrates data from
originals, drops originals, renames partitioned tables into place.
Each table gets a default partition as a safety net for data outside
defined ranges.

pg_partman for automatic forward partition creation is a production
add-on documented in docs/production-operations.md section 4.
"""

from django.db import migrations


PARTITION_REDISTRICTING_PLAN = """
-- Step 1: Rename original table
ALTER TABLE sw_fact_redistricting_plan RENAME TO sw_fact_redistricting_plan_old;

-- Step 2: Create partitioned table with same schema
CREATE TABLE sw_fact_redistricting_plan (
    id bigserial,
    geography_id bigint NOT NULL REFERENCES sw_warehouse_dimgeography(id) ON DELETE CASCADE,
    cycle_id bigint NOT NULL REFERENCES sw_warehouse_dimredistrictingcycle(id) ON DELETE CASCADE,
    chamber varchar(16) NOT NULL,
    plan_type varchar(32) NOT NULL,
    district_number varchar(8) NOT NULL,
    total_population bigint,
    vap bigint,
    cvap bigint,
    deviation_pct double precision,
    polsby_popper double precision,
    reock double precision,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, cycle_id),
    UNIQUE (geography_id, cycle_id, chamber, plan_type, district_number)
) PARTITION BY RANGE (cycle_id);

-- Step 3: Default partition (catches anything outside defined ranges)
CREATE TABLE sw_fact_redistricting_plan_default
    PARTITION OF sw_fact_redistricting_plan DEFAULT;

-- Step 4: Migrate data
INSERT INTO sw_fact_redistricting_plan
    (id, geography_id, cycle_id, chamber, plan_type, district_number,
     total_population, vap, cvap, deviation_pct, polsby_popper, reock, created_at)
SELECT id, geography_id, cycle_id, chamber, plan_type, district_number,
       total_population, vap, cvap, deviation_pct, polsby_popper, reock, created_at
FROM sw_fact_redistricting_plan_old;

-- Step 5: Update sequence
SELECT setval(
    pg_get_serial_sequence('sw_fact_redistricting_plan', 'id'),
    COALESCE((SELECT MAX(id) FROM sw_fact_redistricting_plan), 0) + 1,
    false
);

-- Step 6: Drop old table
DROP TABLE sw_fact_redistricting_plan_old;
"""

PARTITION_VOTE_HISTORY = """
ALTER TABLE sw_fact_vote_history RENAME TO sw_fact_vote_history_old;

CREATE TABLE sw_fact_vote_history (
    id bigserial,
    person_id bigint NOT NULL REFERENCES sw_warehouse_dimperson(id) ON DELETE CASCADE,
    election_date date NOT NULL,
    election_type varchar(16) NOT NULL,
    voted_method varchar(16) NOT NULL DEFAULT 'unknown',
    source_vendor varchar(16) NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, election_date),
    UNIQUE (person_id, election_date, election_type, source_vendor)
) PARTITION BY RANGE (election_date);

CREATE TABLE sw_fact_vote_history_default
    PARTITION OF sw_fact_vote_history DEFAULT;

-- Initial partitions: 2016-2026 (two full cycles)
CREATE TABLE sw_fact_vote_history_2016
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2016-01-01') TO ('2017-01-01');
CREATE TABLE sw_fact_vote_history_2017
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2017-01-01') TO ('2018-01-01');
CREATE TABLE sw_fact_vote_history_2018
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2018-01-01') TO ('2019-01-01');
CREATE TABLE sw_fact_vote_history_2019
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2019-01-01') TO ('2020-01-01');
CREATE TABLE sw_fact_vote_history_2020
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE sw_fact_vote_history_2021
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE sw_fact_vote_history_2022
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE sw_fact_vote_history_2023
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE sw_fact_vote_history_2024
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE sw_fact_vote_history_2025
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE sw_fact_vote_history_2026
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

INSERT INTO sw_fact_vote_history
    (id, person_id, election_date, election_type, voted_method, source_vendor, loaded_at)
SELECT id, person_id, election_date, election_type, voted_method, source_vendor, loaded_at
FROM sw_fact_vote_history_old;

SELECT setval(
    pg_get_serial_sequence('sw_fact_vote_history', 'id'),
    COALESCE((SELECT MAX(id) FROM sw_fact_vote_history), 0) + 1,
    false
);

DROP TABLE sw_fact_vote_history_old;
"""

PARTITION_PERSON_SCORE = """
ALTER TABLE sw_fact_person_score RENAME TO sw_fact_person_score_old;

CREATE TABLE sw_fact_person_score (
    id bigserial,
    person_id bigint NOT NULL REFERENCES sw_warehouse_dimperson(id) ON DELETE CASCADE,
    score_type varchar(128) NOT NULL,
    value double precision NOT NULL,
    source_vendor varchar(16) NOT NULL,
    methodology_version varchar(64) NOT NULL DEFAULT '',
    scored_at timestamptz NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, scored_at),
    -- scored_at is required in the UNIQUE: Postgres mandates the partition
    -- key in every unique constraint on a partitioned table. The model's
    -- unique_together (person, score_type, source_vendor, methodology_version)
    -- is widened by scored_at here so DB-level uniqueness survives partitioning.
    UNIQUE (person_id, score_type, source_vendor, methodology_version, scored_at)
) PARTITION BY RANGE (scored_at);

CREATE TABLE sw_fact_person_score_default
    PARTITION OF sw_fact_person_score DEFAULT;

-- Initial partitions: 2020-2027
CREATE TABLE sw_fact_person_score_2020
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE sw_fact_person_score_2021
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE sw_fact_person_score_2022
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE sw_fact_person_score_2023
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE sw_fact_person_score_2024
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE sw_fact_person_score_2025
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE sw_fact_person_score_2026
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE sw_fact_person_score_2027
    PARTITION OF sw_fact_person_score
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

INSERT INTO sw_fact_person_score
    (id, person_id, score_type, value, source_vendor, methodology_version, scored_at, loaded_at)
SELECT id, person_id, score_type, value, source_vendor, methodology_version, scored_at, loaded_at
FROM sw_fact_person_score_old;

SELECT setval(
    pg_get_serial_sequence('sw_fact_person_score', 'id'),
    COALESCE((SELECT MAX(id) FROM sw_fact_person_score), 0) + 1,
    false
);

DROP TABLE sw_fact_person_score_old;
"""

# Reverse: recreate non-partitioned tables from partitioned ones
REVERSE_REDISTRICTING = """
CREATE TABLE sw_fact_redistricting_plan_flat AS
    SELECT * FROM sw_fact_redistricting_plan;
DROP TABLE sw_fact_redistricting_plan CASCADE;
ALTER TABLE sw_fact_redistricting_plan_flat RENAME TO sw_fact_redistricting_plan;
ALTER TABLE sw_fact_redistricting_plan ADD PRIMARY KEY (id);
"""

REVERSE_VOTE_HISTORY = """
CREATE TABLE sw_fact_vote_history_flat AS
    SELECT * FROM sw_fact_vote_history;
DROP TABLE sw_fact_vote_history CASCADE;
ALTER TABLE sw_fact_vote_history_flat RENAME TO sw_fact_vote_history;
ALTER TABLE sw_fact_vote_history ADD PRIMARY KEY (id);
"""

REVERSE_PERSON_SCORE = """
CREATE TABLE sw_fact_person_score_flat AS
    SELECT * FROM sw_fact_person_score;
DROP TABLE sw_fact_person_score CASCADE;
ALTER TABLE sw_fact_person_score_flat RENAME TO sw_fact_person_score;
ALTER TABLE sw_fact_person_score ADD PRIMARY KEY (id);
"""


class Migration(migrations.Migration):

    dependencies = [
        ("sw_warehouse", "0005_fact_electoral_contest_fk"),
    ]

    operations = [
        migrations.RunSQL(
            sql=PARTITION_REDISTRICTING_PLAN,
            reverse_sql=REVERSE_REDISTRICTING,
        ),
        migrations.RunSQL(
            sql=PARTITION_VOTE_HISTORY,
            reverse_sql=REVERSE_VOTE_HISTORY,
        ),
        migrations.RunSQL(
            sql=PARTITION_PERSON_SCORE,
            reverse_sql=REVERSE_PERSON_SCORE,
        ),
    ]
