CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
-- Persist ag_catalog on the search_path so AGE functions work in all connections,
-- not just the init session where LOAD 'age' is in effect.
ALTER DATABASE :DBNAME SET search_path = ag_catalog, "$user", public;
