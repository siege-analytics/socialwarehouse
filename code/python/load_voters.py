from settings import *
from utilities import *
import csv
import sys
import os
import json



def load_all_voterfiles_from_directory(target_directory):

    # loop through all states

    for COMPLETE_STATE in STATE_NAME_ABBREVIATION_FIPS_CODE:

        # set variables from the string

        STATE_NAME = COMPLETE_STATE[0]
        STATE_ABBREVIATION = COMPLETE_STATE[1]
        STATE_FIPS = COMPLETE_STATE[2]

        # look for a file that matches the known pattern

        target_file_string = VOTER_FILE_ENVIRONMENTAL_VARIABLES['VOTER_FILE'].format(
            **{'state_abbreviation': STATE_ABBREVIATION, 'suffix': VOTER_FILE_ENVIRONMENTAL_VARIABLES['VOTER_FILE_SUFFIX']})

        target_file = target_directory / target_file_string

        if target_file.is_file():
            logging.info("Found file: {target_file} \n".format(target_file=target_file))
            voter_import_table_name = str(target_file.stem.lower())

            # now set environmental variables for the voter file terms
            try:
                set_environment_variables_from_dict(dict_to_set=VOTER_FILE_ENVIRONMENTAL_VARIABLES)
                check_environment_variables_from_dict(dict_to_check=VOTER_FILE_ENVIRONMENTAL_VARIABLES)

            except Exception as e:

                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                logging.error(exc_type, fname, exc_tb.tb_lineno)
                return False

            settings_file = pathlib.Path(STATE_RUN_SETTINGS_FILE.format(**{'state_abbreviation' : STATE_ABBREVIATION}))
            state_run_settings = {
                'STATE_NAME' : STATE_NAME,
                'STATE_ABBREVIATION' : STATE_ABBREVIATION,
                'STATE_FIPS' : STATE_FIPS,
                'VOTER_IMPORT_TABLE': voter_import_table_name,
                'IMPORT_FILE': str(target_file),
                'VOTER_FILE_DELIMITER' : os.environ.get('VOTER_FILE_DELIMITER'),

            }

            write_settings_to_file_and_read_them(intended_settings=state_run_settings, settings_file=settings_file)

            # https://medium.com/@apoor/quickly-load-csvs-into-postgresql-using-python-and-pandas-9101c274a92f
            try:
                # set up a SQLAlchemy engine that ma
                engine = create_sqlalchemy_connection()
                connection = engine.raw_connection()
                cursor = connection.cursor()
                cursor.execute
                row_number = 0
                for df in pd.read_csv(target_file, chunksize=10000, sep=VOTER_FILE_DELIMITER, dtype='str'):
                    logging.info("starting on row_num {row_number}".format(row_number=row_number))
                    df.to_sql(
                        voter_import_table_name,
                        engine,
                        index=False,
                        if_exists='append'  # if the table already exists, append this data
                    )
                    row_number += 10000


            except Exception as e:
                logging.error(e)
        else:
            continue
    return True


def do_all_the_voter_file_loading():
    load_all_voterfiles_from_directory(target_directory=VOTERS_TO_DO_SUBDIRECTORY)


if __name__ == "__main__":
    logging.info("Step 4 load all voter_files to the database")
    do_all_the_voter_file_loading()
