# The Social Warehouse

This is a data warehouse and data lake system for social, civic and social analysis from [Siege Analytics](1).

Built with:

- [Kubernetes](4)
- [MinIO](13)

Runs:  

- [PostgreSQL](5) + [PostGIS](6)
- [Python](7)
- [R](8) (NOT YET)
- [Geoserver](9) (NOT YET)
- [Zeppelin Notebook](10) 
- [GeoTrellis](11) (NOT YET)
- [Ubuntu](12)
- [dbt](14)
- [Spark](15) (FIXING)

Data warehouse is built to enable longitudinal analysis from [Census](2) and [Bureau of Labour Statistics](3).
Intended growth: 
- FEC information
- Election results
- Media markets
- Officials and jurisdictions

## References

- [How to make sdkman run in Dockerfile](16)
- [GDAL Fix for Ubuntu](17)
- [JAVA_HOME Variable for sdkman in Dockerfile](18)
- [Adding sdkman into Dockerfile](19)

[1]: http://www.siegeanalytics.com
[2]: http://www.census.gov
[3]: http://www.bls.gov
[4]: https://kubernetes.io
[5]: https://www.postgresql.org
[6]: https://www.postgis.net
[7]: https://www.python.org
[8]: https://www.r-project.org
[9]: https://www.geoserver.org
[10]: https://zeppelin.apache.org
[11]: https://geotrellis.readthedocs.io/en/latest/
[12]: https://www.ubuntu.org
[13]: https://www.min.io
[14]: https://medium.com/israeli-tech-radar/first-steps-with-dbt-over-postgres-db-f6b350bf4526
[15]: https://medium.com/@MarinAgli1/setting-up-a-spark-standalone-cluster-on-docker-in-layman-terms-8cbdc9fdd14b
[16]: https://stackoverflow.com/questions/62188599/cannot-build-dockerfile-with-sdkman
[17]: https://gis.stackexchange.com/questions/28966/python-gdal-package-missing-header-file-when-installing-via-pip
[18]: https://github.com/sdkman/sdkman-cli/issues/431
[19]: https://stackoverflow.com/questions/53656537/install-sdkman-in-docker-image
