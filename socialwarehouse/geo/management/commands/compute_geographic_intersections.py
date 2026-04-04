"""
Compute Geographic Intersections

Pre-computes spatial intersections between census units using siege_geo
boundary models and stores results for fast attribution queries.

Run once per census year. Updates only when boundaries change.

Usage:
    python manage.py compute_geographic_intersections --year 2020
    python manage.py compute_geographic_intersections --year 2020 --state 06
    python manage.py compute_geographic_intersections --year 2020 --type county-cd
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("socialwarehouse.geo")


class Command(BaseCommand):
    help = "Pre-compute geographic intersections (County-CD, VTD-CD)"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, required=True, help="Census vintage year")
        parser.add_argument(
            "--type", choices=["county-cd", "vtd-cd", "all"], default="all",
            help="Intersection type to compute",
        )
        parser.add_argument("--state", type=str, help="State FIPS code (e.g., 06 for CA)")
        parser.add_argument(
            "--min-overlap", type=float, default=1.0,
            help="Minimum overlap percentage to store (default: 1.0%%)",
        )

    def handle(self, *args, **options):
        year = options["year"]
        intersection_type = options["type"]
        state_fips = options.get("state")
        min_overlap = options["min_overlap"]

        self.stdout.write(f"Computing intersections for year {year}")
        if state_fips:
            self.stdout.write(f"  State: {state_fips}")

        if intersection_type in ["county-cd", "all"]:
            self._compute_county_cd(year, state_fips, min_overlap)
        if intersection_type in ["vtd-cd", "all"]:
            self._compute_vtd_cd(year, state_fips, min_overlap)

    def _compute_county_cd(self, year, state_fips=None, min_overlap=1.0):
        from siege_utilities.geo.django.models import County, CongressionalDistrict
        from socialwarehouse.geo.models import CountyCongressionalDistrictIntersection

        self.stdout.write(f"\n{'=' * 70}")
        self.stdout.write(f"Computing County-CD Intersections (year={year})")
        self.stdout.write(f"{'=' * 70}\n")

        counties = County.objects.filter(vintage_year=year)
        if state_fips:
            counties = counties.filter(geoid__startswith=state_fips)

        total = counties.count()
        created = 0

        self.stdout.write(f"Processing {total} counties...")

        for i, county in enumerate(counties, 1):
            cds = CongressionalDistrict.objects.filter(
                vintage_year=year,
                geom__intersects=county.geom,
            )

            for cd in cds:
                try:
                    intersection_geom = county.geom.intersection(cd.geom)
                    if intersection_geom.empty:
                        continue

                    intersection_area = intersection_geom.area
                    county_area = county.geom.area
                    cd_area = cd.geom.area

                    pct_county = (intersection_area / county_area * 100) if county_area > 0 else 0
                    pct_cd = (intersection_area / cd_area * 100) if cd_area > 0 else 0

                    if pct_county < min_overlap and pct_cd < min_overlap:
                        continue

                    if pct_county >= 99.9:
                        relationship = "CD_IN_COUNTY"
                    elif pct_cd >= 99.9:
                        relationship = "COUNTY_IN_CD"
                    else:
                        relationship = "SPLIT"

                    CountyCongressionalDistrictIntersection.objects.update_or_create(
                        siege_county=county, siege_cd=cd, year=year,
                        defaults={
                            "intersection_geom": intersection_geom,
                            "intersection_area_sqm": int(intersection_area),
                            "pct_of_county": round(pct_county, 2),
                            "pct_of_cd": round(pct_cd, 2),
                            "relationship": relationship,
                            "is_dominant": pct_county > 50.0,
                        },
                    )
                    created += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"  Error: {county.geoid} x {cd.geoid}: {e}"
                    ))

            if i % 10 == 0:
                self.stdout.write(f"  Progress: {i}/{total} ({i / total * 100:.1f}%)")

        self.stdout.write(self.style.SUCCESS(f"Created {created} County-CD intersections"))

    def _compute_vtd_cd(self, year, state_fips=None, min_overlap=1.0):
        from siege_utilities.geo.django.models import VTD, CongressionalDistrict
        from socialwarehouse.geo.models import VTDCongressionalDistrictIntersection

        self.stdout.write(f"\n{'=' * 70}")
        self.stdout.write(f"Computing VTD-CD Intersections (year={year})")
        self.stdout.write(f"{'=' * 70}\n")

        vtds = VTD.objects.filter(vintage_year=year)
        if state_fips:
            vtds = vtds.filter(geoid__startswith=state_fips)

        total = vtds.count()
        created = 0

        self.stdout.write(f"Processing {total} VTDs...")

        for i, vtd in enumerate(vtds, 1):
            cds = CongressionalDistrict.objects.filter(
                vintage_year=year,
                geom__intersects=vtd.geom,
            )

            for cd in cds:
                try:
                    intersection_geom = vtd.geom.intersection(cd.geom)
                    if intersection_geom.empty:
                        continue

                    intersection_area = intersection_geom.area
                    vtd_area = vtd.geom.area
                    cd_area = cd.geom.area

                    pct_vtd = (intersection_area / vtd_area * 100) if vtd_area > 0 else 0
                    pct_cd = (intersection_area / cd_area * 100) if cd_area > 0 else 0

                    if pct_vtd < min_overlap:
                        continue

                    VTDCongressionalDistrictIntersection.objects.update_or_create(
                        siege_vtd=vtd, siege_cd=cd, year=year,
                        defaults={
                            "intersection_geom": intersection_geom,
                            "intersection_area_sqm": int(intersection_area),
                            "pct_of_vtd": round(pct_vtd, 2),
                            "pct_of_cd": round(pct_cd, 2),
                            "is_dominant": pct_vtd > 50.0,
                        },
                    )
                    created += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"  Error: {vtd.geoid} x {cd.geoid}: {e}"
                    ))

            if i % 100 == 0:
                self.stdout.write(f"  Progress: {i}/{total} ({i / total * 100:.1f}%)")

        self.stdout.write(self.style.SUCCESS(f"Created {created} VTD-CD intersections"))
