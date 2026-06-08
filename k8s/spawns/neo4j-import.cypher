// Neo4j graph import template for SocialWarehouse.
//
// Imports person-geography-vote relationships from PostGIS hub
// into a Neo4j graph database for relationship queries.
//
// Prerequisites:
//   - Neo4j APOC plugin installed
//   - JDBC driver for PostgreSQL available to Neo4j
//   - Network access from Neo4j to PostGIS hub (direct connection)
//
// Usage:
//   neo4j-admin database import cypher --from=neo4j-import.cypher
//   OR run queries individually via Neo4j Browser / cypher-shell.
//
// Refresh cadence: nightly or on-demand after materialization.

// --- Constraints (run once) ---

CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (p:Person) REQUIRE p.person_id IS UNIQUE;

CREATE CONSTRAINT geography_geoid IF NOT EXISTS
FOR (g:Geography) REQUIRE g.geoid IS UNIQUE;

CREATE CONSTRAINT cycle_id IF NOT EXISTS
FOR (c:RedistrictingCycle) REQUIRE c.cycle_id IS UNIQUE;

// --- Node import: Persons ---
// Uses APOC JDBC to stream from PostGIS.
// Replace jdbc-url with your PostGIS direct connection.

CALL apoc.load.jdbc(
  'jdbc:postgresql://primary-host:5432/socialwarehouse?user=socialwarehouse&password=...',
  'SELECT id, first_name, last_name, state_voter_id, registration_status FROM sw_dim_person'
) YIELD row
MERGE (p:Person {person_id: row.id})
SET p.first_name = row.first_name,
    p.last_name = row.last_name,
    p.state_voter_id = row.state_voter_id,
    p.registration_status = row.registration_status;

// --- Node import: Geographies ---

CALL apoc.load.jdbc(
  'jdbc:postgresql://primary-host:5432/socialwarehouse?user=socialwarehouse&password=...',
  'SELECT id, geoid, name, geo_level FROM sw_dim_geography'
) YIELD row
MERGE (g:Geography {geoid: row.geoid})
SET g.geography_id = row.id,
    g.name = row.name,
    g.geo_level = row.geo_level;

// --- Node import: Redistricting Cycles ---

CALL apoc.load.jdbc(
  'jdbc:postgresql://primary-host:5432/socialwarehouse?user=socialwarehouse&password=...',
  'SELECT id, cycle_year FROM sw_dim_redistricting_cycle'
) YIELD row
MERGE (c:RedistrictingCycle {cycle_id: row.id})
SET c.cycle_year = row.cycle_year;

// --- Relationship import: VOTED_IN ---

CALL apoc.load.jdbc(
  'jdbc:postgresql://primary-host:5432/socialwarehouse?user=socialwarehouse&password=...',
  'SELECT person_id, election_date, election_type, voted_method FROM sw_fact_vote_history'
) YIELD row
MATCH (p:Person {person_id: row.person_id})
MERGE (p)-[:VOTED_IN {
  election_date: row.election_date,
  election_type: row.election_type,
  voted_method: row.voted_method
}]->(e:Election {date: row.election_date, type: row.election_type})
ON CREATE SET e.election_date = row.election_date,
              e.election_type = row.election_type;

// --- Parity verification ---
// After import, compare counts:
//
//   MATCH (p:Person) RETURN count(p) AS neo4j_person_count;
//   -- Compare with: SELECT count(*) FROM sw_dim_person;
//
//   MATCH ()-[v:VOTED_IN]->() RETURN count(v) AS neo4j_vote_count;
//   -- Compare with: SELECT count(*) FROM sw_fact_vote_history;
