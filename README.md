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

## Using

Ideally, you will be able to do everything from the `makefile` because the `docker-compose`
 will have accounted for what you need to do. Here are some of the important `make` commands:

- `down` - this will terminate the containers, volumes, networks and remove them. It's a last resort command.
- `stop` - this will terminate the containers, volumes, networks, bringing them to a rest.
- `up` - this will start containers, networks, volumes from rest and run them in detached mode.
- `build` - this will build the containers, networks and volumes.
- `rebuild` - this will build the containers, networks, volumes from nothing, not relying on cached resources.
- `clean` - this will terminate the containers, volumes and networks, and remove them.
- `pg_shell` - this will create an `ssh` connection to the `PostgreSQL` server container.
- `python_term` - this will create an `ssh` connection to the `Python` container
- `fetch_jars` - this uses `maven` to get `jar` files that are used by `Spark` to operate. It will save them in the default location copy them to the `jars` directory in the project.
  
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