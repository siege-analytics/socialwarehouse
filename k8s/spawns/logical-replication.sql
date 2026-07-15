-- Logical replication publications for hub-to-downstream distribution.
--
-- Run on the PRIMARY PostGIS instance. Each publication defines a
-- filtered subset of hub tables that a downstream subscriber receives.
--
-- Prerequisites:
--   wal_level = logical  (set in postgresql.conf or CNPG cluster.yaml)
--   max_replication_slots >= number of subscribers + WAL archiving slots
--   max_wal_senders >= max_replication_slots

-- Publication: Django OLTP web app
-- All sw_dim_* and sw_geo_* tables (dimensions + geography).
-- Fact tables excluded by default — web app reads facts via API,
-- not direct DB queries. Add specific fact tables if your web app
-- needs them.
CREATE PUBLICATION sw_web_oltp FOR TABLE
    sw_dim_geography,
    sw_dim_person,
    sw_dim_redistricting_cycle,
    sw_dim_survey,
    sw_dim_census_variable,
    sw_dim_time
WITH (publish = 'insert, update, delete, truncate');

-- Publication: monitoring tables (for a dedicated observability DB)
CREATE PUBLICATION sw_monitoring FOR TABLE
    sw_monitoring_materialization,
    sw_monitoring_replication_lag,
    sw_monitoring_parity_check
WITH (publish = 'insert, update, delete, truncate');

-- Publication: full warehouse (all sw_* tables)
-- Use with caution — this replicates everything including fact tables.
-- Suitable for a full read replica, not for selective spawns.
CREATE PUBLICATION sw_full FOR ALL TABLES IN SCHEMA public;

-- Subscriber setup (run on the DOWNSTREAM instance):
--
-- CREATE SUBSCRIPTION sw_web_oltp_sub
--     CONNECTION 'host=primary-host port=5432 dbname=socialwarehouse user=replication_user password=...'
--     PUBLICATION sw_web_oltp
--     WITH (
--         copy_data = true,          -- initial data sync
--         create_slot = true,        -- auto-create replication slot
--         slot_name = 'sw_web_oltp'  -- named slot for monitoring
--     );
--
-- Verify replication status:
--   SELECT * FROM pg_stat_subscription;
--
-- Parity monitoring:
--   Compare row counts between hub and spawn using sw_monitoring_parity_check
--   (see docs/production-operations.md section 11).
