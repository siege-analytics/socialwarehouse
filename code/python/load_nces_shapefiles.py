#!/usr/bin/env python3

from utilities import *
import os
import gdaltools

def load_all_shapefiles_from_directory(target_directory=NCES_SUBDIRECTORY):
    try:
        for zipped_shapefile in target_directory.glob('**/*.zip'):
            logging.info("Working on {file}".format(**{'file': zipped_shapefile}))
            name_of_new_dir_for_unzip = zipped_shapefile.stem
            path_for_new_dir = zipped_shapefile.parent
            table_name = name_of_new_dir_for_unzip

            # ensure that the file extracted correctly
            new_path = unzip_file_to_its_own_directory(zipped_shapefile)
            if new_path:
                full_path_to_shapefile = new_path / "{shapefile_name}.shp".format(
                    **{'shapefile_name': name_of_new_dir_for_unzip})
                logging.info(full_path_to_shapefile)

                logging.info("Working on {current_shapefile}".format(**{'current_shapefile': full_path_to_shapefile}))
                try:
                    command = [
                        "shp2pgsql",  # Command to load shapefile into PSQL
                        "-I",  # Parameter to create spatial index
                        "-d",  # Parameter to drop the existing table if it exists
                        "-s {base_polygons_crs}".format(**{'base_polygons_crs': BASE_POLYGON_CRS}),
                        # Parameter to determine CRS for polygons
                        "{full_path_to_shapefile}".format(**{'full_path_to_shapefile': full_path_to_shapefile}),
                        # Parameter to specify path of shapefile being loaded
                        "{pgschema}.{table_name}".format(**{'pgschema': os.getenv('PGSCHEMA'),
                                                            'table_name': table_name}),
                        # Parameter to define target schema and table
                        "|",  # Pipe to pass command and parameters to next command
                        "psql"  # Execute the shp2pgsql output as PSQL using environment variables
                    ]

                    run_subprocess(" ".join(command))

                    logging.info("Successfully imported: {full_path_to_shapefile}".format(
                        **{'full_path_to_shapefile': full_path_to_shapefile}))
                except gdaltools.basetypes.GdalToolsError:
                    logging.info("Skipping this file...")

    except Exception as e:
        error_message = "There was an error: {e}".format(**{'e': e})
        logging.info(error_message)
        return False

def do_all_the_nces_loading():
    set_psql_environment_variables()
    check_psql_environmental_variables()
    for year in NCES_YEARS:
        nces_dir = NCES_SUBDIRECTORY / year
    load_all_shapefiles_from_directory(target_directory=nces_dir)

if __name__ == "__main__":
    logging.info("Step 3 unzip and load them to database via shp2pgsql")
    do_all_the_nces_loading()
