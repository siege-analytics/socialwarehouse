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
import bs4

logging.basicConfig(level=logging.INFO)


def download_census_shapefiles():
    for census_year in CENSUS_YEARS:

        for geography, parameters in CENSUS_GEOGRAPHIES_TO_DOWNLOAD.items():

            # 1 Create a directory for the target geography

            info_message = "Working on {year}:{geography}, which is {file_type}".format(**{'year': census_year,
                                                                                           'geography': geography,
                                                                                           'file_type': parameters[
                                                                                               'PATTERN']})

            logging.info(info_message)
            new_geography_directory = pathlib.Path(CENSUS_SUBDIRECTORY) / census_year / geography
            pathlib.Path(new_geography_directory).mkdir(parents=True, exist_ok=True)
            logging.info("Found or created a directory for: {path}".format(**{'path': str(new_geography_directory)}))

            try:

                if parameters["PATTERN"] == 'SINGLE':

                    remote_zipfile = parameters['URL'].format(**{'year': census_year})
                    local_zipfile_name = remote_zipfile.split('/')[-1]
                    local_zipfile_path = str(pathlib.Path(new_geography_directory) / local_zipfile_name)

                    info_message = "Remote = {remote_zipfile} \n File Name To Save = {local_zipfile_name} \n Local Path = {local_zipfile_path}".format(
                        **{'remote_zipfile': remote_zipfile,
                           'local_zipfile_name': local_zipfile_name,
                           'local_zipfile_path': local_zipfile_path}
                    )

                    logging.info(info_message)

                    download_file(remote_zipfile, local_zipfile_path)

                # The geography will have multiple files to be downloaded based on statefips
                elif parameters["PATTERN"] == 'STATE_BY_STATE':

                    for statefips in FIPS_STATES_TO_DOWNLOAD:
                        statefips = "{:02d}".format(statefips)
                        remote_zipfile = parameters['URL'].format(**{'year': census_year, 'statefips': statefips})
                        local_zipfile_name = remote_zipfile.split('/')[-1]
                        local_zipfile_path = str(pathlib.Path(new_geography_directory) / local_zipfile_name)

                        info_message = "Remote = {remote_zipfile} \n File Name To Save = {local_zipfile_name} \n Local Path = {local_zipfile_path}".format(
                            **{'remote_zipfile': remote_zipfile,
                               'local_zipfile_name': local_zipfile_name,
                               'local_zipfile_path': local_zipfile_path}
                        )

                        logging.info(info_message)

                        download_file(remote_zipfile, local_zipfile_path)

                # Some geographies have multiple files associated with one state, we use BS4 to get them
                # adapting code from https://bitbucket.org/dchand/census_fetcher/src/master/fetch.py
                elif parameters["PATTERN"] == 'BEAUTIFUL_SOUP_STATE_BY_STATE':
                    logging.info("Beautiful soup!")

                    census_tiger_url = parameters['URL'].format(**{'year': census_year})

                    downloaded_page_from_census = requests.get(census_tiger_url)

                    census_page_bs4_haystack = bs4.BeautifulSoup(downloaded_page_from_census.text, 'html.parser')

                    all_links_on_census_page = census_page_bs4_haystack.find_all("a")

                    links_to_geography_files_on_census_page = [link for link in all_links_on_census_page if '.zip' in link.contents[0]]

                    # loop through all statefips that we will need
                    for statefips in FIPS_STATES_TO_DOWNLOAD:
                        statefips = "{:02d}".format(statefips)

                        # check if the statefips we want is in the right position for the remote link
                        for geography_file_link in links_to_geography_files_on_census_page:

                            link_href = geography_file_link.get('href')
                            link_elements = link_href.split('_')
                            link_statefips = link_elements[2][0:2]

                            if statefips == link_statefips:

                                remote_zipfile = census_tiger_url + link_href
                                local_zipfile_name = remote_zipfile.split('/')[-1]
                                local_zipfile_path = str(pathlib.Path(new_geography_directory) / local_zipfile_name)

                                info_message = "Remote = {remote_zipfile} \n File Name To Save = {local_zipfile_name} \n Local Path = {local_zipfile_path}".format(
                                    **{'remote_zipfile': remote_zipfile,
                                       'local_zipfile_name': local_zipfile_name,
                                       'local_zipfile_path': local_zipfile_path}
                                )

                                logging.info(info_message)

                                download_file(remote_zipfile, local_zipfile_path)


                else:
                    error_message = "Invalid pattern: {pattern}".format(**{'patern': parameters['PATTERN']})
                    logging.error(error_message)
                    continue
            except Exception as e:

                error_message = ("There was an error: {e}".format(**{'e': e}))
                logging.error(error_message)
                sys.exit()


if __name__ == "__main__":
    logging.info("Step 2 fetch the Census TIGER shapefiles")
    download_census_shapefiles()
