#!/usr/bin/env python3

__author__ = 'Dheeraj Chand'
__copyright__ = 'Copyright 2020, Clarity and Rigour, LLC'
__credits__ = ['Dheeraj Chand']
__version__ = '0.1.2'
__maintainer__ = 'Dheeraj Chand'
__email__ = 'dheeraj@siegeanalytics.com'
__status__ = 'Dev'

from utilities import *
import logging
import pathlib
import sys

logging.basicConfig(level=logging.INFO)


def download_nces_shapefiles():
    for census_year in CENSUS_YEARS:

        for geography, parameters in NCES_GEOGRAPHIES_TO_DOWNLOAD.items():
            # 1 Create a directory for the target geography

            info_message = "Working on {year}:{geography}, which is {file_type}".format(**{'year': census_year,
                                                                                           'geography': geography,
                                                                                           'file_type': parameters[
                                                                                               'PATTERN']})

            logging.info(info_message)
            new_geography_directory = pathlib.Path(NCES_SUBDIRECTORY) / census_year / geography
            pathlib.Path(new_geography_directory).mkdir(parents=True, exist_ok=True)
            logging.info("Found or created a directory for: {path}".format(**{'path': str(new_geography_directory)}))

        # The geography will have multiple files to be downloaded based on state abbreviations
        try:

            for state in STATE_NAME_ABBREVIATION_FIPS_CODE:

                state_abbreviation = str(state[1])
                # get all states
                if ABBREVIATION_STATES_TO_DOWNLOAD[0].upper().strip() == 'ALL':
                    info_message = 'We are downloading all states.'
                    logging.info(info_message)
                    info_message = "{state_abbreviation} is in the list to download: \n {download_list} \n Working on it.".format(
                        **{'state_abbreviation': state_abbreviation,
                           'download_list': str(ABBREVIATION_STATES_TO_DOWNLOAD)})
                    logging.info(info_message)
                    remote_zipfile = parameters['URL'].format(**{'state_abbreviation': state_abbreviation})
                    local_zipfile_name = remote_zipfile.split('/')[-1]
                    local_zipfile_path = str(pathlib.Path(new_geography_directory) / local_zipfile_name)

                    info_message = "Remote = {remote_zipfile} \n File Name To Save = {local_zipfile_name} \n Local Path = {local_zipfile_path}".format(
                        **{'remote_zipfile': remote_zipfile,
                           'local_zipfile_name': local_zipfile_name,
                           'local_zipfile_path': local_zipfile_path}
                    )

                    logging.info(info_message)

                    download_file(remote_zipfile, local_zipfile_path)
                # get some states
                else:
                    info_message = "We are working on a finite list of states {download_list}".format(**{'download_list': ABBREVIATION_STATES_TO_DOWNLOAD})
                    logging.info(info_message)
                    # current state is desired
                    if state_abbreviation.upper().strip() in ABBREVIATION_STATES_TO_DOWNLOAD:
                        info_message = "{state_abbreviation} is in the list to download: \n {download_list} \n Working on it.".format(
                            **{'state_abbreviation': state_abbreviation,
                               'download_list': str(ABBREVIATION_STATES_TO_DOWNLOAD)})
                        logging.info(info_message)
                        remote_zipfile = parameters['URL'].format(**{'state_abbreviation': state_abbreviation})
                        local_zipfile_name = remote_zipfile.split('/')[-1]
                        local_zipfile_path = str(pathlib.Path(new_geography_directory) / local_zipfile_name)

                        info_message = "Remote = {remote_zipfile} \n File Name To Save = {local_zipfile_name} \n Local Path = {local_zipfile_path}".format(
                            **{'remote_zipfile': remote_zipfile,
                               'local_zipfile_name': local_zipfile_name,
                               'local_zipfile_path': local_zipfile_path}
                        )

                        logging.info(info_message)

                        download_file(remote_zipfile, local_zipfile_path)



                    # current state is not desired
                    else:
                        info_message = "Working on {current_state}, which is not in the list.".format(
                            **{'current_state': state_abbreviation})
                        logging.info(info_message)
                        continue



        except Exception as e:

            error_message = ("There was an error: {e}".format(**{'e': e}))
            logging.error(error_message)
            continue


if __name__ == "__main__":
    logging.info("Step 6 fetch the NCES shapefiles")
    download_nces_shapefiles()
