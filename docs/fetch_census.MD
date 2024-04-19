# Fetch shapefiles from Census

1. Determine years

```
# decide what years you care about for analysis.  
export YEARS=2020,2021,2022
```

2. Determine desired geographies
 
```
export geographies=("CD" "TABBLOCK" "COUNTY" "SLDL" "SLDU" "STATE" "TRACT" "TTRACT" "ZCTA5" "BG" "ROADS")
```

3. Execute fetch_census.sh
 
      ./fetch_census.sh

This puts the files into the working directory

Check that they are there

      du -h -n 2 .

should look like:

      ...
