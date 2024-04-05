import org.apache.sedona.spark.SedonaContext
import org.apache.sedona.core.formatMapper.shapefileParser.ShapefileReader
import org.apache.sedona.sql.utils.Adapter

val config = SedonaContext.builder()
  .appName("readTestScala") // Change this to a proper name
  .getOrCreate()

val sedona = SedonaContext.create(config)

val shapefilesInputLocation="./data/"

val cb_2022_us_cd118_rdd = ShapefileReader.readToGeometryRDD(sedona.sparkContext, shapefilesInputLocation+"cb_2022_us_all_500k/cb_2022_us_cd118_500k")

var cb_2022_us_cd118_gdf = Adapter.toDf(cb_2022_us_cd118_rdd, sedona)

cb_2022_us_cd118_gdf.registerTempTable("cb_2022_us_cd118_gdf")

val cb_2022_us_cd118_centroids_gdf = spark.sql("""
  SELECT

  s.nameslsad,
  s.geoid,
  s.CENTROID AS geometry,
  ST_GeometryType(s.CENTROID) as geom_type_centroid_column
  FROM

  (SELECT NAMELSAD as nameslsad,
         GEOID as geoid,
         ST_PointOnSurface(geometry) AS CENTROID,
         ST_Area(geometry) AS AREA
  FROM cb_2022_us_cd118_gdf) AS s
  """)

cb_2022_us_cd118_centroids_gdf.registerTempTable("cb_2022_us_cd118_centroids_gdf")

val cb_2022_us_county_rdd = ShapefileReader.readToGeometryRDD(sedona.sparkContext, shapefilesInputLocation+"cb_2022_us_all_500k/cb_2022_us_county_500k")

var cb_2022_us_county_gdf = Adapter.toDf(cb_2022_us_county_rdd, sedona)

cb_2022_us_county_gdf.registerTempTable("cb_2022_us_county_gdf")

val cd_centroids_county_polygons_intersect_gdf = spark.sql("""
 SELECT
 pnts.*,
 plgn.NAMELSAD
 FROM cb_2022_us_cd118_centroids_gdf AS pnts, cb_2022_us_county_gdf AS plgn
 WHERE ST_Contains(plgn.geometry, pnts.geometry)
""")

cd_centroids_county_polygons_intersect_gdf.show(100)
