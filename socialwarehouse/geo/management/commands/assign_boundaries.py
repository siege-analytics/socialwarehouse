"""
Assign geographic boundaries to geocoded addresses via PostGIS spatial joins
using siege_utilities boundary models. Supports plan-aware assignment for
court-ordered mid-cycle redistricting.

Usage:
    # Legacy mode (Census vintage only)
    python manage.py assign_boundaries --year 2020 --state TX

    # Plan-aware mode (resolves active redistricting plan for a date)
    python manage.py assign_boundaries --date 2023-08-15 --state AL

    # By congressional term
    python manage.py assign_boundaries --congressional-term 118 --state AL

    # Dry run
    python manage.py assign_boundaries --date 2023-08-15 --dry-run
"""

import logging
from datetime import date as date_type

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("socialwarehouse.geo")


class Command(BaseCommand):
    help = (
        "Assign census geographic boundaries to geocoded addresses. "
        "Supports plan-aware assignment for court-ordered redistricting."
    )

    def add_arguments(self, parser):
        # Temporal context (mutually exclusive)
        temporal = parser.add_mutually_exclusive_group()
        temporal.add_argument(
            "--date", type=str, default=None,
            help="Date for plan-aware assignment (YYYY-MM-DD). Derives vintage and finds active plan.",
        )
        temporal.add_argument(
            "--congressional-term", type=int, default=None,
            help="Congress number (e.g., 118). Uses term start date for plan resolution.",
        )
        temporal.add_argument(
            "--year", type=int, default=None,
            help="Census vintage year (legacy mode, no plan awareness). Default: 2020.",
        )

        # Filters
        parser.add_argument(
            "--state", type=str, default=None,
            help="Filter by state abbreviation (e.g., TX, AL)",
        )
        parser.add_argument(
            "--source", type=str, default=None,
            choices=["census", "nominatim", "smartystreets"],
            help="Filter by geocode source",
        )

        # Processing
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--limit", type=int, default=0, help="0 = all")
        parser.add_argument("--force", action="store_true", help="Re-assign even if already assigned")
        parser.add_argument("--populate-fks", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        context_date_str = options["date"]
        congressional_term = options["congressional_term"]
        year = options["year"]
        state = options["state"]
        source = options["source"]
        batch_size = options["batch_size"]
        limit = options["limit"]
        force = options["force"]
        populate_fks = options["populate_fks"]
        dry_run = options["dry_run"]

        # Resolve temporal context
        context_date = None
        plan_aware = False
        active_plans = {}  # (state_fips, chamber) → RedistrictingPlan

        if context_date_str:
            context_date = date_type.fromisoformat(context_date_str)
            plan_aware = True
            year = self._resolve_vintage(context_date.year)
            self.stdout.write(f"Plan-aware mode: date={context_date}, vintage={year}")
        elif congressional_term:
            context_date = self._resolve_term_date(congressional_term)
            plan_aware = True
            year = self._resolve_vintage(context_date.year)
            self.stdout.write(f"Plan-aware mode: term={congressional_term}, date={context_date}, vintage={year}")
        else:
            year = year or 2020
            self.stdout.write(f"Legacy mode: vintage={year} (no plan awareness)")

        # If plan-aware, pre-fetch active plans
        if plan_aware:
            active_plans = self._fetch_active_plans(context_date, state)
            if active_plans:
                for key, plan in active_plans.items():
                    self.stdout.write(f"  Active plan: {plan.plan_name} ({key[0]} {key[1]})")
            else:
                self.stdout.write("  No active redistricting plans found — using Census defaults")

        # Build queryset
        from socialwarehouse.geo.models import Address

        qs = Address.objects.filter(geocoded=True, geom__isnull=False)
        if not force:
            qs = qs.filter(census_units_assigned_at__isnull=True)
        if state:
            qs = qs.filter(state_abbreviation=state.upper())
        if source:
            qs = qs.filter(geocode_source=source)

        total = qs.count()
        process_count = min(limit, total) if limit else total

        self.stdout.write(
            f"Found {total} addresses"
            f"{f' in {state.upper()}' if state else ''}"
            f", will process {process_count}"
        )

        if dry_run:
            from django.db.models import Count
            state_counts = (
                qs.values("state_abbreviation")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )
            if state_counts:
                self.stdout.write("Top states:")
                for row in state_counts:
                    self.stdout.write(f"  {row['state_abbreviation']}: {row['count']}")
            self.stdout.write(self.style.SUCCESS("[DRY RUN] No changes made."))
            return

        if process_count == 0:
            self.stdout.write("Nothing to assign.")
            return

        # Run assignment
        assigned, failed = self._assign_batch(
            qs, year, batch_size, limit, populate_fks,
            plan_aware, context_date, active_plans,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Done: {assigned}/{process_count} assigned, {failed} failed "
            f"(vintage={year}{f', date={context_date}' if context_date else ''})"
        ))

    def _resolve_vintage(self, calendar_year: int) -> int:
        """Map a calendar year to a Census vintage year."""
        from socialwarehouse.geo.models import CensusVintageConfig
        config = CensusVintageConfig.for_year(calendar_year)
        if config:
            return config.decade
        # Fallback: round down to nearest decade
        return (calendar_year // 10) * 10

    def _resolve_term_date(self, congress_number: int) -> date_type:
        """Get the start date of a Congressional term."""
        from siege_utilities.geo.django.models import CongressionalTerm
        term = CongressionalTerm.objects.filter(congress_number=congress_number).first()
        if term and term.start_date:
            return term.start_date
        # Fallback: approximate
        start_year = 1789 + (congress_number - 1) * 2
        return date_type(start_year, 1, 3)

    def _fetch_active_plans(self, context_date, state_filter=None):
        """Pre-fetch active redistricting plans for the given date."""
        from siege_utilities.geo.django.models import RedistrictingPlan

        plans = {}
        for chamber in ["congress", "state_senate", "state_house"]:
            if state_filter:
                # Look up state FIPS from abbreviation
                from siege_utilities.geo.django.models import State
                st = State.objects.filter(
                    name__iexact=state_filter
                ).first() or State.objects.filter(
                    geoid=state_filter
                ).first()
                if st:
                    plan = RedistrictingPlan.objects.for_date(st.state_fips, chamber, context_date)
                    if plan:
                        plans[(st.state_fips, chamber)] = plan
            else:
                # Check all states (expensive but thorough)
                active = RedistrictingPlan.objects.filter(
                    effective_from__lte=context_date,
                ).filter(
                    models.Q(effective_to__gte=context_date) | models.Q(effective_to__isnull=True)
                )
                for plan in active:
                    plans[(plan.state_fips, plan.chamber)] = plan

        return plans

    def _assign_batch(self, qs, year, batch_size, limit, populate_fks,
                      plan_aware, context_date, active_plans):
        """Assign boundaries in batches."""
        from siege_utilities.geo.django.models import (
            State, County, Tract, BlockGroup,
            CongressionalDistrict, VTD,
            StateLegislativeLower, StateLegislativeUpper,
            PlanDistrict,
        )
        from socialwarehouse.geo.models import Address, AddressBoundaryPeriod, CensusVintageConfig

        vintage_config = CensusVintageConfig.for_year(year) if plan_aware else (
            CensusVintageConfig.objects.filter(decade=year).first()
        )

        addr_ids = list(
            qs.values_list("pk", flat=True)[:limit] if limit
            else qs.values_list("pk", flat=True)
        )

        assigned = 0
        failed = 0

        for i in range(0, len(addr_ids), batch_size):
            batch_ids = addr_ids[i:i + batch_size]
            batch_num = i // batch_size + 1
            batch_addrs = Address.objects.filter(pk__in=batch_ids)

            self.stdout.write(f"Batch {batch_num}: processing {len(batch_ids)} addresses...")

            for addr in batch_addrs:
                try:
                    if not addr.geom:
                        failed += 1
                        continue

                    query_point = addr.geom.clone()
                    query_point.transform(4269)

                    # --- Static boundaries (same regardless of plan) ---
                    s = State.objects.filter(geom__contains=query_point, vintage_year=year).first()
                    if not s:
                        failed += 1
                        continue

                    state_geoid = s.geoid
                    county_geoid = tract_geoid = bg_geoid = vtd_geoid = None

                    c = County.objects.filter(geom__contains=query_point, vintage_year=year).first()
                    if c:
                        county_geoid = c.geoid
                        t = Tract.objects.filter(geom__contains=query_point, vintage_year=year).first()
                        if t:
                            tract_geoid = t.geoid
                            bg = BlockGroup.objects.filter(geom__contains=query_point, vintage_year=year).first()
                            if bg:
                                bg_geoid = bg.geoid
                        vtd = VTD.objects.filter(geom__contains=query_point, vintage_year=year).first()
                        if vtd:
                            vtd_geoid = vtd.geoid

                    # --- Political boundaries (plan-dependent) ---
                    cd_geoid = sldl_geoid = sldu_geoid = None
                    plan_cd = plan_sldl = plan_sldu = None
                    active_plan = None
                    method = "SPATIAL_JOIN"

                    if plan_aware and s.state_fips:
                        # Check for active congressional plan
                        congress_plan = active_plans.get((s.state_fips, "congress"))
                        if congress_plan:
                            active_plan = congress_plan
                            pd = PlanDistrict.objects.filter(
                                plan=congress_plan, geom__contains=query_point
                            ).first()
                            if pd:
                                cd_geoid = pd.geoid or pd.district_number
                                plan_cd = pd
                                method = "PLAN_SPATIAL_JOIN"

                        # Check for active state senate plan
                        senate_plan = active_plans.get((s.state_fips, "state_senate"))
                        if senate_plan:
                            pd = PlanDistrict.objects.filter(
                                plan=senate_plan, geom__contains=query_point
                            ).first()
                            if pd:
                                sldu_geoid = pd.geoid or pd.district_number
                                plan_sldu = pd

                        # Check for active state house plan
                        house_plan = active_plans.get((s.state_fips, "state_house"))
                        if house_plan:
                            pd = PlanDistrict.objects.filter(
                                plan=house_plan, geom__contains=query_point
                            ).first()
                            if pd:
                                sldl_geoid = pd.geoid or pd.district_number
                                plan_sldl = pd

                    # Fall back to Census boundaries for any political level not resolved by plan
                    if not cd_geoid:
                        cd = CongressionalDistrict.objects.filter(
                            geom__contains=query_point, vintage_year=year
                        ).first()
                        if cd:
                            cd_geoid = cd.geoid

                    if not sldl_geoid:
                        sldl = StateLegislativeLower.objects.filter(
                            geom__contains=query_point, vintage_year=year
                        ).first()
                        if sldl:
                            sldl_geoid = sldl.geoid

                    if not sldu_geoid:
                        sldu = StateLegislativeUpper.objects.filter(
                            geom__contains=query_point, vintage_year=year
                        ).first()
                        if sldu:
                            sldu_geoid = sldu.geoid

                    # --- Store on Address (backward compat) ---
                    addr.state_geoid = state_geoid
                    addr.county_geoid = county_geoid
                    addr.tract_geoid = tract_geoid
                    addr.block_group_geoid = bg_geoid
                    addr.vtd_geoid = vtd_geoid
                    addr.cd_geoid = cd_geoid
                    addr.sldl_geoid = sldl_geoid
                    addr.sldu_geoid = sldu_geoid
                    addr.census_year = year
                    addr.census_units_assigned_at = timezone.now()
                    addr.save()

                    # --- Create/update AddressBoundaryPeriod ---
                    if vintage_config:
                        period, _ = AddressBoundaryPeriod.objects.update_or_create(
                            address=addr,
                            vintage=vintage_config,
                            redistricting_plan=active_plan,
                            defaults={
                                "context_date": context_date,
                                "congressional_term_id": None,  # TODO: resolve from context_date
                                "state_geoid": state_geoid,
                                "county_geoid": county_geoid,
                                "tract_geoid": tract_geoid,
                                "block_group_geoid": bg_geoid,
                                "vtd_geoid": vtd_geoid,
                                "cd_geoid": cd_geoid,
                                "sldl_geoid": sldl_geoid,
                                "sldu_geoid": sldu_geoid,
                                "plan_district_cd": plan_cd,
                                "plan_district_sldl": plan_sldl,
                                "plan_district_sldu": plan_sldu,
                                "assignment_method": method,
                            },
                        )

                    if populate_fks:
                        addr.populate_foreign_keys()

                    assigned += 1

                except Exception as e:
                    logger.error("Failed to assign boundaries for %s: %s", addr.pk, e)
                    failed += 1

            self.stdout.write(f"  Batch {batch_num} done: {assigned} assigned, {failed} failed")

        return assigned, failed
