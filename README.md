# Evaluating Geocode Hygiene

This is a Siege Analytics tool to evaluate geocode quality from client supplied lists.
It is written in Python 3 and makes use of PostGIS for computations and storage.

The entire project is wrapped in Docker in order to be fully self-contained, and has a Makefile for use.

1. make build - this will create the necessary containers, recreating if necessary
2. make up - this will start the containers
3. make ensure-paths - this creates the paths necessary for the work to be done
4. make fetch-census-shapefiles - this will fetch the Census shapefiles
5. make fetch-census-acs - this will fetch ACS information
6. make load-census-shapefiles - this will put the census shapefiles into PostGIS
