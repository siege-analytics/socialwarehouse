import pathlib
import logging
# import gdaltools
import os
import psycopg2

# System-wide settings

logging.basicConfig(level=logging.INFO)

# Filesystem settings

HOME_DIRECTORY = list(pathlib.Path(__file__).parents)
DATA_DIRECTORY = pathlib.Path('data')
OUTPUT_SUBDIRECTORY = pathlib.Path(DATA_DIRECTORY) / 'outputs'
INPUT_SUBDIRECTORY = pathlib.Path(DATA_DIRECTORY) / 'inputs'
VOTERS_SUBDIRECTORY = pathlib.Path(INPUT_SUBDIRECTORY) / 'voters'
VOTERS_TO_DO_SUBDIRECTORY = pathlib.Path(VOTERS_SUBDIRECTORY) / 'to_do'
VOTERS_COMPLETED_SUBDIRECTORY = pathlib.Path(VOTERS_SUBDIRECTORY) / 'completed'
VOTERS_IN_PROCESS_SUBDIRECTORY = pathlib.Path(VOTERS_SUBDIRECTORY) / 'in_process'
CENSUS_SUBDIRECTORY = pathlib.Path(INPUT_SUBDIRECTORY) / 'census'
SHAPES_SUBDIRECTORY = pathlib.Path(OUTPUT_SUBDIRECTORY) / 'shapes'
ACS_SUBDIRECTORY = pathlib.Path(CENSUS_SUBDIRECTORY) / 'acs'
NCES_SUBDIRECTORY = pathlib.Path(INPUT_SUBDIRECTORY) / 'nces'


REPORTS_SUBDIRECTORY = pathlib.Path(OUTPUT_SUBDIRECTORY) / 'reports'
SQL_TEMPLATES_DIRECTORY = pathlib.Path('sql_templates')

REQUIRED_PATHS = [
    VOTERS_SUBDIRECTORY,
    VOTERS_TO_DO_SUBDIRECTORY,
    VOTERS_IN_PROCESS_SUBDIRECTORY,
    VOTERS_COMPLETED_SUBDIRECTORY,
    CENSUS_SUBDIRECTORY,
    NCES_SUBDIRECTORY,
    ACS_SUBDIRECTORY,
    SHAPES_SUBDIRECTORY,
    REPORTS_SUBDIRECTORY,
    SQL_TEMPLATES_DIRECTORY
]

#  Geography Settings

BASE_POLYGON_CRS = 4269
INDIVIDUAL_POINTS_CRS = 4326
CENSUS_YEARS = ['2020']
NCES_YEARS = ['2020']
CENSUS_GEOGRAPHIES_TO_DOWNLOAD = {
    'BG': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/BG/tl_{year}_{statefips}_bg.zip",
           'PATTERN': "STATE_BY_STATE"},
    'COUNTY': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/COUNTY/tl_{year}_us_county.zip",
               'PATTERN': 'SINGLE'},
    'CD': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/CD/tl_{year}_us_cd116.zip",
           'PATTERN': 'SINGLE'},
    'SLDL': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/SLDL/tl_{year}_{statefips}_sldl.zip",
             'PATTERN': "STATE_BY_STATE"},
    'SLDU': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/SLDU/tl_{year}_{statefips}_sldu.zip",
             'PATTERN': "STATE_BY_STATE"},
    'STATE': {'URL': 'https://www2.census.gov/geo/tiger/TIGER{year}/STATE/tl_{year}_us_state.zip',
              'PATTERN': 'SINGLE'},
    'TABBLOCK':
        {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/TABBLOCK/tl_{year}_{statefips}_tabblock10.zip",
         'PATTERN': 'STATE_BY_STATE'},
    'TRACT': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/TRACT/tl_{year}_{statefips}_tract.zip",
              'PATTERN': "STATE_BY_STATE"},
    'ROADS': {'URL': "https://www2.census.gov/geo/tiger/TIGER{year}/ROADS/",
              'PATTERN': 'BEAUTIFUL_SOUP_STATE_BY_STATE'}
}

NCES_GEOGRAPHIES_TO_DOWNLOAD = {

    'URBANICITY' : {

        'URL' : "https://nces.ed.gov/programs/edge/data/EDGE_locale20_STATES/edge_locale20_nces_{state_abbreviation}.zip",
            'PATTERN': "STATE_BY_STATE"
    }
}


DOWNLOAD_SINGLE = False
DOWNLOAD_STATE_BY_STATE = True
ACS_YEARS = ["2019"]
CENSUS_ACS_FILES_TO_DOWNLOAD = {
    'CVAP_2019_ETHNICITY': {
        'URL': "https://www2.census.gov/programs-surveys/decennial/rdo/datasets/{year}/{year}-cvap/CVAP_{old_year}-{year}_ACS_csv_files.zip",
        'PATTERN': "SINGLE"}
}

FIPS_STATES_TO_DOWNLOAD = range(0, 79)  # range(1,2)
ABBREVIATION_STATES_TO_DOWNLOAD = ['AK', 'TX']  # ['ALL'] OR ['AK','TX']


# PSQL & GDAL

POSTGRES_ENVIRONMENTAL_VARIABLES = {

    'PGHOST': os.environ.get('POSTGRES_HOST', 'localhost'),
    'PGPORT': '5432',
    'PGUSER': os.environ.get('POSTGRES_USER', 'dheerajchand'),
    'PGPASSWORD': os.environ.get('POSTGRES_PASSWORD', 'dessert'),
    'PGDATABASE': os.environ.get('POSTGRES_DB', 'gis'),
    'PGSCHEMA': 'public',
}

# ogr = gdaltools.ogr2ogr()
# gdal_conn = gdaltools.PgConnectionString(
#     host=POSTGRES_ENVIRONMENTAL_VARIABLES['PGHOST'],
#     port=POSTGRES_ENVIRONMENTAL_VARIABLES['PGPORT'],
#     dbname=POSTGRES_ENVIRONMENTAL_VARIABLES['PGDATABASE'],
#     schema=POSTGRES_ENVIRONMENTAL_VARIABLES['PGSCHEMA'],
#     user=POSTGRES_ENVIRONMENTAL_VARIABLES['PGUSER'],
#     password=POSTGRES_ENVIRONMENTAL_VARIABLES['PGPASSWORD']
# )

psycopg2_connection_string = "host={host} user={user} password={password} dbname={database}".format(
    **{'host': POSTGRES_ENVIRONMENTAL_VARIABLES['PGHOST'],
       'user': POSTGRES_ENVIRONMENTAL_VARIABLES['PGUSER'],
       'password': POSTGRES_ENVIRONMENTAL_VARIABLES['PGPASSWORD'],
       'database': POSTGRES_ENVIRONMENTAL_VARIABLES['PGDATABASE']
       })

# Voterfile parameters

ACS_FILE_DELIMITER = '\t'
ACS_FILE_SUFFIX = 'csv'
ACS_FILE_BATCH_SIZE = 10000

# Database Tables, Indices, Etc.

STATE_RUN_SETTINGS_FILE = pathlib.Path('state_run_settings.json')

# Unwieldy data structures
STATE_NAME_ABBREVIATION_FIPS_CODE = [
    # ["Alabama", "AL", "01"],  # 0
    # ["Alaska", "AK", "02"],
    # ["Arizona", "AZ", "04"],
    # ["Arkansas", "AR", "05"],
    # ["California", "CA", "06"],
    # ["Colorado", "CO", "08"],  # 5
    # ["Connecticut", "CT", "09"],
    # ["Delaware", "DE", "10"],
    # ["District of Columbia", "DC", "11"],
    # ["Florida", "FL", "12"],
    # ["Georgia", "GA", "13"],
    # ["Hawaii", "HI", "15"],  # 10
    # ["Idaho", "ID", "16"],
    # ["Illinois", "IL", "17"],
    # ["Indiana", "IN", "18"],
    # ["Iowa", "IA", "19"],
    # ["Kansas", "KS", "20"],  # 15
    # ["Kentucky", "KY", "21"],
    # ["Louisiana", "LA", "22"],
    # ["Maine", "ME", "23"],
    # ["Maryland", "MD", "24"],
    # ["Massachusetts", "MA", "25"],  # 20
    # ["Michigan", "MI", "26"],
    # ["Minnesota", "MN", "27"],
    # ["Mississippi", "MS", "28"],
    # ["Missouri", "MO", "29"],
    # ["Montana", "MT", "30"],  # 25
    # ["Nebraska", "NE", "31"],
    # ["Nevada", "NV", "32"],
    # ["New Hampshire", "NH", "33"],
    # ["New Jersey", "NJ", "34"],
    # ["New Mexico", "NM", "35"],  # 30
    # ["New York", "NY", "36"],
    # ["North Carolina", "NC", "37"],
    # ["North Dakota", "ND", "38"],
    # ["Ohio", "OH", "39"],
    # ["Oklahoma", "OK", "40"],  # 35
    # ["Oregon", "OR", "41"],
    # ["Pennsylvania", "PA", "42"],
    # ["Rhode Island", "RI", "44"],
    # ["South Carolina", "SC", "45"],
    # ["South Dakota", "SD", "46"],  # 40
    # ["Tennessee", "TN", "47"],
    ["Texas", "TX", "48"],
    # ["Utah", "UT", "49"],
    # ["Vermont", "VT", "50"],
    # ["Virginia", "VA", "51"],  # 45
    # ["Washington", "WA", "53"],
    # ["West Virginia", "WV", "54"],
    # ["Wisconsin", "WI", "55"],
    # ["Wyoming", "WY", "56"],
    # ["American Samoa", "AS", "60"],  # 50
    # ["Guam", "GU", "66"],
    # ["Northern Mariana Islands", "MP", "69"],
    # ["Puerto Rico", "PR", "72"],
    # ["Virgin Islands", "VI", "78"],
]

VOTER_FILE_ENVIRONMENTAL_VARIABLES = {
    'VOTER_FILE' : "cleaned_jamaa_with_precincts_{state_abbreviation}.{suffix}",
    'VOTER_FILE_DELIMITER': '\t',
    'VOTER_FILE_SUFFIX': 'txt',
    'VOTER_FILE_BATCH_SIZE': '10000',
    'VOTER_FILE_STARTING_RECORD_NUMBER': '0',
    'VOTER_FILE_COL_PRIMARY_KEY': 'voter_file_vanid',
    'VOTER_FILE_COL_X': 'longitude',
    'VOTER_FILE_COL_Y': 'latitude',
    'VOTER_FILE_COL_GEOCODE_PRECISION': 'None',
    'VOTER_FILE_COL_DESIRED_GEOM': 'precinctname_',
    'VOTER_FILE_COL_HD': 'hd',
    'VOTER_FILE_COL_SD': 'sd',
    'VOTER_FILE_COL_CD': 'cd',
    'VOTER_FILE_COL_COUNTY_NAME': 'city',
    'VOTER_FILE_COL_COUNTY_FIPS': 'None',
    'VOTER_FILE_MINIMUM_NUMBER_OF_RECORDS_FOR_POLYGONIZATION': '0',
    'VOTER_FILE_PERCENTAGE_OF_VOTERS_TO_BE_COUNTED': '0',
    'VOTER_FILE_ENCODING': 'latin1'
}

# Database Tables, Indices, Etc.

STATE_RUN_SETTINGS_FILE = 'state_run_settings_{state_abbreviation}.json'
