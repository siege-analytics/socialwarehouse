from settings import *

import sys
import subprocess
import zipfile
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
import requests
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)

def run_subprocess(command_list):
    # Not sure if this is handling failures properly...
    p = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        print("SUBPROCESS FAILED!")
        raise Exception("Subprocess failed with error: {}".format(stderr))

def download_file(url, local_filename):

    with requests.get(url, stream=True, allow_redirects=True) as r:

        if r.ok:
            logging.info(r.ok)
            total_size = int(r.headers.get('content-length',0))

            initial_pos = 0
            with open(local_filename, 'ab') as f:
                with tqdm(total=total_size, unit_scale=True, desc=local_filename, initial=initial_pos,
                          ascii=True) as pbar:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                            pbar.update(len(chunk))
            return local_filename
        else:
            return False

def unzip_file_to_its_own_directory(path_to_zipfile, new_dir_name=None, new_dir_parent=None):
    try:
        frtz = zipfile.ZipFile(path_to_zipfile)
        if new_dir_name is None:
            new_dir_name = path_to_zipfile.stem
        if new_dir_parent is None:
            new_dir_parent = path_to_zipfile.parent

        # ensure that a directory exists for the new files to go in
        target_dir_for_unzipped_files = new_dir_parent / new_dir_name
        pathlib.Path(target_dir_for_unzipped_files).mkdir(parents=True, exist_ok=True)

        frtz.extractall(path=target_dir_for_unzipped_files)
        info_message = "Just unzipped: \n {path_to_zipfile} \n To: {target_dir}".format(
            **{'path_to_zipfile': path_to_zipfile,
               'target_dir': target_dir_for_unzipped_files})
        logging.info(info_message)
        return target_dir_for_unzipped_files

    except Exception as e:

        error_message = "There was an error {e}".format(**{'e': e})
        logging.error(error_message)
        return False

def set_psql_environment_variables():
    for variable, setting in POSTGRES_ENVIRONMENTAL_VARIABLES.items():
        os.environ[variable] = setting

def check_psql_environmental_variables():
    logging.info("These are the PSQL environmental variables")
    for variable in POSTGRES_ENVIRONMENTAL_VARIABLES.keys():
        print(variable, '->', os.environ.get(variable))

def create_psycopg2_connection():
    try:
        psycopg2_connection_string = "host={host} user={user} password={password} dbname={database}".format(
            **{'host': POSTGRES_ENVIRONMENTAL_VARIABLES['PGHOST'],
               'user': POSTGRES_ENVIRONMENTAL_VARIABLES['PGUSER'],
               'password': POSTGRES_ENVIRONMENTAL_VARIABLES['PGPASSWORD'],
               'database': POSTGRES_ENVIRONMENTAL_VARIABLES['PGDATABASE']
               })

        psycopg2_conn = psycopg2.connect(psycopg2_connection_string)
        info_message = "Succesfully created a psycopg2 connection"
        logging.info(info_message)
        return psycopg2_conn
    except Exception as e:
        error_message = "Error: {e}".format(**{'e': e})
        logging.error(error_message)
        return False

def create_sqlalchemy_connection():
    """
    Performs database connection using database settings from settings.py.
    Returns sqlalchemy engine instance
    """

    DATABASE = {
        'drivername': 'postgres',
        'host': POSTGRES_ENVIRONMENTAL_VARIABLES['PGHOST'],
        'port': POSTGRES_ENVIRONMENTAL_VARIABLES['PGPORT'],
        'username': POSTGRES_ENVIRONMENTAL_VARIABLES['PGUSER'],
        'password': POSTGRES_ENVIRONMENTAL_VARIABLES['PGPASSWORD'],
        'database': POSTGRES_ENVIRONMENTAL_VARIABLES['PGDATABASE']
    }

    try:
        engine = create_engine(URL(**DATABASE))
        logging.info("Successfully created SQLALCHEMY engine.")
        return engine
    except Exception as e:
        print(e)
        return False

def write_state_run_settings_to_file(intended_settings):
    # output the intended_settings
    logging.info("Values to be added are: {intended_settings}".format(**{'intended_settings': intended_settings}))

    # ensure that a file exists

    if STATE_RUN_SETTINGS_FILE.is_file():
        logging.info("A JSON file for the settings exists")
    else:
        STATE_RUN_SETTINGS_FILE.touch()
        logging.info("Created state_run_settings_file")

    # read the contents of the file, allow for empty

    try:
        with open(STATE_RUN_SETTINGS_FILE, 'r') as existing_settings_file:
            existing_settings = json.load(existing_settings_file)
            if existing_settings is None:
                existing_settings = {}
                logging.info("There are no existing settings. Creating a new dictionary: {existing_settings}".format(
                    **{'existing_settings': existing_settings}))

            logging.info(
                "The existing settings are {existing_settings}".format(**{'existing_settings': existing_settings}))

            new_run_settings = existing_settings
            new_run_settings.update(intended_settings)
            logging.info(
                "The new settings to be written are {new_run_settings}".format(**{'new_run_settings': new_run_settings}))

        with open(STATE_RUN_SETTINGS_FILE, 'w') as to_write_settings_file:
            json.dump(new_run_settings, to_write_settings_file)
            logging.info("Just wrote the new settings to the settings file. {new_run_settings}".format(
                **{'new_run_settings': new_run_settings}))

        return new_run_settings

    except Exception as e:
        logging.error(e)
        existing_settings = {}
        new_run_settings = existing_settings
        new_run_settings.update(intended_settings)
        with open(STATE_RUN_SETTINGS_FILE, 'w') as to_write_settings_file:
            json.dump(new_run_settings, to_write_settings_file)
            logging.info("Just wrote the new settings to the settings file. {new_run_settings}".format(
                **{'new_run_settings': new_run_settings}))

        return new_run_settings
