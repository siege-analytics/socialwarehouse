DROP FUNCTION IF EXISTS roads(text);

CREATE OR REPLACE FUNCTION roads(my_table text)
	RETURNS TABLE (
		-- make sure these match the query below
		table_name TEXT,
		linearid NUMERIC,
		fullname text,
		rttyp text,
		mtfcc text,
		geom geometry)
LANGUAGE plpgsql AS $$
BEGIN
	RETURN QUERY EXECUTE format('SELECT ''%s''::text, linearid::numeric, fullname::text, rttyp::text, mtfcc::text, geom FROM %s', my_table, my_table);
END;
$$;

SELECT (roads(table_name)).* FROM
	(SELECT table_name
 	 FROM information_schema.tables
	WHERE
	 table_schema = 'public'
	 AND table_name LIKE '%roads%' -- this can probably be done with a regex, but we'll worry about that later
	 AND substr(table_name, 4, 4)= '2020'
	 AND substr(table_name, 9, 2) = '46'
	 ORDER BY substr(table_name, 9, 2)::int DESC
) my_tables;


---


-- 1 Is there a way to generalise this to work with different table structures?
-- 2 How would I verify and troubleshoot results?

DROP FUNCTION IF EXISTS sldl(text);

CREATE OR REPLACE FUNCTION sldl(my_table text):
    RETURNS TABLE (
        -- make sure these match the query below
        table_name  TEXT,
        gid


    )