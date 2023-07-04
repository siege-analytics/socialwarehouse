# --at command line
# wget https://s3.amazonaws.com/census-backup/acs/2018/acs2018_5yr/acs2018_5yr_backup.sql.gz
# -- in db
# CREATE SCHEMA acs2018_5yr;
# ALTER SCHEMA acs2018_5yr OWNER TO census;
# -- at command line
# zcat acs2018_5yr_backup.sql.gz | psql -q -U census <db name> -h <host name>