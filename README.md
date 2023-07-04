# socialwarehouse

This is a data warehouse and data lake system for social, civic and social analysis from [Siege Analytics](https://www.siegeanalytics.com).

Built with:

    * Kubernetes

Runs:  

    PostgreSQL + PostGIS
    Python
    R
    Geoserver
    Notebook server

Data warehouse is built to enable longitudinal analysis from [Census](https://www.census.gov) and [Bureau of Labour Statistics](https://www.bls.gov).

## Makefile commands

The entire project is wrapped in Docker in order to be fully self-contained, and has a Makefile for use.

1. make build - this will create the necessary containers, recreating if necessary
2. make up - this will start the containers
3. make ensure-paths - this creates the paths necessary for the work to be done
4. make fetch-census-shapefiles - this will fetch the Census shapefiles
5. make fetch-census-acs - this will fetch ACS information
6. make load-census-shapefiles - this will put the census shapefiles into PostGIS
