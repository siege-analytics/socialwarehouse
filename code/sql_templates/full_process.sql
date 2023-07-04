-- /* STEP 1: Preparing the points table
--    SHORT NAME: Inserting_voters
--    a. Duplicate the points table into a table that you can edit so that you maintain original data
--    b. Create a geometry column for the voters (points) table
--    c. Populate the geometry column in the native projection
--    d. Reproject the points table into the blocks projection
--    e. Add a spatial index to the table
--
--  */
-- -- 1a
-- DROP TABLE IF EXISTS tx_voters;
--
-- -- 1b
-- CREATE TABLE tx_voters
-- AS (SELECT *
--     FROM nea_tx AS txv);
--
-- ALTER TABLE
--     tx_voters
--     ADD COLUMN IF NOT EXISTS geom                          GEOMETRY(Point, 4326),
--     ADD COLUMN IF NOT EXISTS two_letter_state_abbreviation VARCHAR DEFAULT 'TX'; -- This is the state two letter abbreviation
--
-- -- 1c
-- UPDATE
--     tx_voters AS pnts
-- SET geom=ST_SetSRID(ST_MakePoint(reglongitude::NUMERIC, reglatitude::NUMERIC ), 4326)
-- WHERE pnts.reglongitude IS NOT NULL
--   AND pnts.reglatitude IS NOT NULL;
--
-- -- 1d
--
-- ALTER TABLE tx_voters
--     ALTER COLUMN geom TYPE GEOMETRY(Point, 4269) USING ST_Transform(geom, 4269);
--
-- -- 1e
--
-- CREATE INDEX
--     tx_voters_sdx
--     ON
--         tx_voters
--             USING GIST (geom);
--
-- /* STEP 2: Check that geographic labels are correct.
--    SHORT NAME: Verifying_spatial_labels
--
--     a. Create master tables of all important geographies where they do not already exist
--        i.
--
--     b. Alter the voters table to add a column for whether spatially tested geographies match the labels for
--         i. State
--         ii. County
--         iii. CD
--         iv. SD (SLDU)
--         v. HD (SLDU)
--     c. Update the match columns with spatial queries
--         i. State
--         ii. County
--         iii. CD
--         iv. SD (SLDU)
--         v. HD (SLDL)
--  */
--
-- --2a - Alter the voters table to add a column for whether spatially tested geographies match the labels
--
-- ALTER TABLE tx_voters
--     DROP COLUMN IF EXISTS state_label_spatial_matches, -- i
--     DROP COLUMN IF EXISTS county_label_spatial_matches, -- ii
--     DROP COLUMN IF EXISTS cd_label_spatial_matches, -- iii
--     DROP COLUMN IF EXISTS sd_label_spatial_matches, -- iv
--     DROP COLUMN IF EXISTS hd_label_spatial_matches, -- v
--     ADD COLUMN state_label_spatial_matches  BOOLEAN DEFAULT TRUE, -- i
--     ADD COLUMN county_label_spatial_matches BOOLEAN DEFAULT TRUE, -- ii
--     ADD COLUMN sd_label_spatial_matches     BOOLEAN DEFAULT TRUE, -- iii
--     ADD COLUMN cd_label_spatial_matches     BOOLEAN DEFAULT TRUE, -- iv
--     ADD COLUMN hd_label_spatial_matches     BOOLEAN DEFAULT TRUE; -- v
--
-- -- 2b - Update the match columns with a spatial query
--
-- -- 2b i
-- UPDATE
--     tx_voters AS pnts
-- SET state_label_spatial_matches =
--     CASE
--         WHEN
--             pnts.geom IS NULL
--         THEN
--             FALSE
--         ELSE
--             ST_CONTAINS(bndry.geom, pnts.geom)
--     END
-- FROM
--         tl_2019_us_state AS bndry -- this is the state column
-- WHERE
--     TRIM(pnts.state) = TRIM(bndry.stusps);
--
--
--
-- -- 2b ii
-- UPDATE
--     tx_voters AS pnts
-- SET county_label_spatial_matches =
--     CASE
--         WHEN
--             pnts.geom IS NULL
--         THEN
--             FALSE
--         ELSE
--             ST_CONTAINS(bndry.geom, pnts.geom)
--     END
-- FROM tl_2019_us_county AS bndry -- this is the county column
-- WHERE pnts.countyfips::INTEGER = bndry.countyfp::INTEGER;

-- 2b iii
UPDATE
    tx_voters AS pnts
SET cd_label_spatial_matches =
    CASE
        WHEN
            pnts.geom IS NULL
        THEN
            FALSE
        ELSE
            ST_CONTAINS(bndry.geom, pnts.geom)
    END
FROM
    tl_2019_us_cd116 AS bndry -- this is the cd column
WHERE
    TRIM(pnts.congressionaldistrict) = TRIM(bndry.cd116fp);


-- 2b iv

UPDATE
    tx_voters AS pnts
SET sd_label_spatial_matches =
    CASE
        WHEN
            pnts.geom IS NULL
        THEN
            FALSE
        ELSE
            ST_CONTAINS(bndry.geom, pnts.geom)
    END
FROM
     tl_2019_48_sldu AS bndry -- this is the sd column
WHERE
      TRIM(pnts.statesenatedistrict) = TRIM(bndry.sldust);

-- 2b v

UPDATE
    tx_voters AS pnts
SET hd_label_spatial_matches =
    CASE
        WHEN
            pnts.geom IS NULL
        THEN
            FALSE
        ELSE
            ST_CONTAINS(bndry.geom, pnts.geom)
    END
FROM tl_2019_48_sldl AS bndry -- this is the hd column
WHERE
      (pnts.statehousedistrict) = (bndry.sldlst);

/* STEP 3: Create the roads segment union table
   SHORT NAME: Aggregating_roads_tables

   a. Create a roads table by selecting all rows from the many roads table associated with the state
        i. year
        ii. state_fips

   b. Alter the roads table to add a column for spatially tested containing geographies
        i. State
        ii. County
        iii. CD
        iv. SD (SLDU)
        v. HD (SLDU)
    c. Update the containing columns with spatial queries
        i. State
        ii. County
        iii. CD
        iv. SD (SLDU)
        v. HD (SLDL)

 */

-- 3 a
-- There are hundreds of tables per state for street segments, we need to
-- easily get all of them into one SELECT
-- for now, though, we'll just use one
-- We'll do the same for all the polygonal geographies we're testing, actually, aggregate
-- For, we'll just use the TX ones in singular to illustrate the point

DROP TABLE IF EXISTS
    tx_roads_aggregate;

CREATE TABLE
    tx_roads_aggregate AS
    (
        SELECT
               r.*
        FROM
            tl_2020_48001_roads AS r

    );

-- 3b

ALTER TABLE tx_roads_aggregate
    DROP COLUMN IF EXISTS state_label_spatial_contains, -- i
    DROP COLUMN IF EXISTS county_label_spatial_contains, -- ii
    DROP COLUMN IF EXISTS cd_label_spatial_contains, -- iii
    DROP COLUMN IF EXISTS sd_label_spatial_contains, -- iv
    DROP COLUMN IF EXISTS hd_label_spatial_contains, -- v
    ADD COLUMN state_label_spatial_contains  VARCHAR DEFAULT NULL, -- i
    ADD COLUMN county_label_spatial_contains VARCHAR DEFAULT NULL, -- ii
    ADD COLUMN sd_label_spatial_contains     VARCHAR DEFAULT NULL, -- iii
    ADD COLUMN cd_label_spatial_contains     VARCHAR DEFAULT NULL, -- iv
    ADD COLUMN hd_label_spatial_contains     VARCHAR DEFAULT NULL; -- v

-- 3c

UPDATE
    tx_roads_aggregate AS pnts

SET
    state_label_spatial_contains =
    CASE
        WHEN
            ST_CONTAINS(state.geom, pnts.geom)
        THEN
            state.stusps
        ELSE
            NULL
    END

FROM
    tl_2019_us_state                AS state,
    tl_2019_us_county               AS county,
    tl_2019_us_cd116                AS cd,
    tl_2019_48_sldu                 AS sd,
    tl_2019_48_sldl                 AS hd
;

/* STEP 4: Update the points table with nearest segment and try it out
   SHORT NAME: Nearest_street_segment

   a. Create a column for the street idea on the voters table
        1. Intersecting street
        2. Nearest street
        3. Distance from nearest street

   b. If the the address intersects a street, update that column
   c. If the address does not intersect a street
        1. Find the nearest one
        2. Update the address table with the nearest street
        3. Update the address table with the distance from the nearest street segment (Separate query)

 */

 -- 4a

ALTER TABLE tx_voters
    DROP COLUMN IF EXISTS intersecting_street,                          -- 1
    DROP COLUMN IF EXISTS nearest_street,                               -- 2
    DROP COLUMN IF EXISTS distance_from_nearest_street,                 -- 3
    ADD COLUMN intersecting_street          VARCHAR DEFAULT NULL,       -- 1
    ADD COLUMN nearest_street               VARCHAR DEFAULT NULL,       -- 2
    ADD COLUMN distance_from_nearest_street     VARCHAR DEFAULT NULL   -- 3
;

--4b

UPDATE tx_voters AS pnts
SET intersecting_street = streets.linearid
FROM tx_roads_aggregate AS streets
WHERE pnts.geom IS NOT NULL
  AND ST_INTERSECTS(pnts.geom, streets.geom);

--4c
-- https://gis.stackexchange.com/questions/136403/postgis-nearest-points-with-st-distance-knn
