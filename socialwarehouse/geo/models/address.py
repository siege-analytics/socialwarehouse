"""
Address model — the central record in socialwarehouse.

Stores a US address with geocoding metadata, Census unit linkages (GEOIDs),
and optional ForeignKeys to siege_utilities boundary models for rich
hierarchical queries.

Design:
    GEOIDs are primary (string-indexed, fast lookups, year-flexible).
    ForeignKeys are optional (for ORM traversal: address.siege_vtd.county.state.name).
    Both approaches coexist — GEOIDs for bulk operations, FKs for Django admin and
    rich queries.
"""

from collections import namedtuple

from django.contrib.gis.db import models
from django.utils import timezone


# Default census vintage used when an Address is created without an
# explicit `census_year`. Bumped manually each decade as the canonical
# TIGER vintage shifts (next bump: 2030 vintage's general-availability
# date — TBD, currently expected ~2030-2032).
#
# This is INTENTIONALLY a module-level int constant, not a callable
# default reading CensusVintageConfig — that path tangles with F11
# (#100 — Address.census_year vs CensusVintageConfig dual source of
# truth) and is being deferred until the dual-source-of-truth question
# is settled. Tracked: F6 / SW#95.
DEFAULT_CENSUS_YEAR = 2020


# Canonical geocode source values, lowercase. Matches how SW's own
# writers populate the field (see geocode_addresses.py: `addr.geocode_source
# = "census"` / "nominatim"). The vendor GST submodule's tasks.py writes
# Mixed Case ("Census") — that's a separate inconsistency to be cleaned up
# vendor-side; out of scope for F7/SW#96.
#
# Reading rows with values outside this set (legacy, vendor-written, or
# any future addition) is not blocked — only future admin-form writes are
# constrained. Add a new value here when a new geocoder ships and update
# the canonical-set comment.
GEOCODE_SOURCE_CHOICES = [
    ("census", "Census Geocoder (US)"),
    ("nominatim", "Nominatim (OpenStreetMap)"),
    ("google", "Google Geocoding API"),
    ("smartystreets", "SmartyStreets"),
]


# F11 / SW#100: one entry in an address's temporal-boundary timeline.
# Returned by Address.boundary_timeline(). Named-tuple so callers can
# unpack positionally or dot-access; `abp` carries the raw
# AddressBoundaryPeriod row for fields beyond the four headline ones
# (assignment_method, congressional_term, plan_district_*, ...).
BoundaryTimelineEntry = namedtuple(
    "BoundaryTimelineEntry",
    ["geoid", "effective_from", "effective_to", "plan_name", "abp"],
)


def _safe_plan_name(plan_id):
    """Return a RedistrictingPlan's plan_name without triggering the SU#527 columns.

    Calling ``abp.redistricting_plan`` triggers a SELECT that includes
    ``effective_from`` / ``effective_to``, columns the siege_utilities
    migrations don't create (SU#527). Using
    ``RedistrictingPlan.objects.filter(...).values_list("plan_name", flat=True)``
    restricts the SELECT to only the columns we need, dodging the
    missing-column crash.

    Returns ``None`` for null ``plan_id``, for orphan FKs (non-existent
    plan), or if any error occurs during the lookup.
    """
    if plan_id is None:
        return None
    try:
        from siege_utilities.geo.django.models import RedistrictingPlan

        return (
            RedistrictingPlan.objects
            .filter(pk=plan_id)
            .values_list("plan_name", flat=True)
            .first()
        )
    except Exception:
        return None


class Address(models.Model):
    """
    A geocoded US address with Census boundary assignments.

    Fields are based on the SmartyStreets/USPS address component model,
    extended with geocoding metadata and Census unit linkages.
    """

    # ── Address components ───────────────────────────────────────────────
    # F3/SW#92: CharFields use blank=True, default="" (Django convention).
    # null=True was the pre-F3 shape; the data-backfill in migration 0003
    # converts existing NULL rows to "" before the NOT NULL constraint.
    primary_number = models.CharField(max_length=250, blank=True, default="")
    street_name = models.CharField(max_length=250, blank=True, default="")
    street_suffix = models.CharField(max_length=250, blank=True, default="")
    city_name = models.CharField(max_length=250, blank=True, default="")
    default_city_name = models.CharField(max_length=250, blank=True, default="")
    state_abbreviation = models.CharField(max_length=2, blank=True, default="")
    zip5 = models.CharField(max_length=5, blank=True, default="")
    delivery_point = models.CharField(max_length=99, blank=True, default="")
    delivery_point_check_digit = models.CharField(max_length=99, blank=True, default="")

    # ── USPS & RDI classification ────────────────────────────────────────
    record_type = models.CharField(max_length=250, blank=True, default="")
    zip_type = models.CharField(max_length=250, blank=True, default="")
    county_fips = models.CharField(max_length=250, blank=True, default="")
    county_name = models.CharField(max_length=250, blank=True, default="")
    carrier_route = models.CharField(max_length=250, blank=True, default="")
    congressional_district = models.CharField(max_length=250, blank=True, default="")
    rdi = models.CharField(max_length=250, blank=True, default="")
    elot_sequence = models.CharField(max_length=250, blank=True, default="")
    elot_sort = models.CharField(max_length=250, blank=True, default="")

    # ── Coordinates ──────────────────────────────────────────────────────
    # latitude/longitude/geom stay null=True — numeric NULL is the canonical
    # "unknown" for numerics/geometries (F3 is CharField-scope only).
    latitude = models.DecimalField(max_digits=22, decimal_places=16, null=True, blank=True, default=None)
    longitude = models.DecimalField(max_digits=22, decimal_places=16, null=True, blank=True, default=None)
    coordinate_license = models.CharField(max_length=250, blank=True, default="")
    precision = models.CharField(max_length=250, blank=True, default="")
    time_zone = models.CharField(max_length=250, blank=True, default="")
    utc_offset = models.CharField(max_length=250, blank=True, default="")

    # ── GeoDjango geometry ───────────────────────────────────────────────
    geom = models.PointField(srid=4326, null=True, blank=True, default=None)

    # ── Geocoding metadata ───────────────────────────────────────────────
    geocoded = models.BooleanField(default=False, help_text="Whether address has been geocoded")
    geocode_quality = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Quality: Rooftop, Interpolated, Approximate, Zip",
    )
    geocode_source = models.CharField(
        max_length=50, blank=True, default="",
        choices=GEOCODE_SOURCE_CHOICES,
        help_text=(
            "Source geocoder. Canonical values lowercase per "
            "GEOCODE_SOURCE_CHOICES (F7 / SW#96). Existing rows with "
            "non-canonical values (e.g. vendor-written 'Census') are "
            "preserved; only new admin-form writes are constrained."
        ),
    )
    geocoded_at = models.DateTimeField(null=True, blank=True)

    # ── Census year context ──────────────────────────────────────────────
    # Default sourced from DEFAULT_CENSUS_YEAR module constant so the
    # "bumped manually each decade" rule has a single edit site.
    census_year = models.IntegerField(
        default=DEFAULT_CENSUS_YEAR,
        help_text="Census year for boundary assignment (2010, 2020)",
    )

    # ── Census unit GEOIDs (primary, string-indexed) ─────────────────────
    # F3/SW#92: "" means "not yet assigned" (Django convention). Callers
    # that need "has an assignment" should use exclude(field="") rather
    # than filter(field__isnull=False) — the latter becomes always-true
    # against a NOT NULL column.
    state_geoid = models.CharField(max_length=2, blank=True, default="")
    county_geoid = models.CharField(max_length=5, blank=True, default="")
    tract_geoid = models.CharField(max_length=11, blank=True, default="")
    block_group_geoid = models.CharField(max_length=12, blank=True, default="")
    block_geoid = models.CharField(max_length=15, blank=True, default="")
    vtd_geoid = models.CharField(max_length=11, blank=True, default="")
    cd_geoid = models.CharField(max_length=4, blank=True, default="")
    sldl_geoid = models.CharField(
        max_length=5, blank=True, default="",
        help_text="State Legislative District Lower GEOID (state FIPS + district)",
    )
    sldu_geoid = models.CharField(
        max_length=5, blank=True, default="",
        help_text="State Legislative District Upper GEOID (state FIPS + district)",
    )
    census_units_assigned_at = models.DateTimeField(null=True, blank=True)

    # ── Address construction timeline (TIGER ADDRFEAT) ──────────────────
    tiger_first_seen_year = models.PositiveSmallIntegerField(
        null=True, blank=True, db_index=True,
        help_text=(
            "Earliest TIGER/Line ADDRFEAT vintage in which this address range "
            "appears. Approximates when the address was built. Populated by "
            "cross-referencing address against multiple TIGER vintage years."
        ),
    )
    tiger_last_seen_year = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "Most recent TIGER/Line ADDRFEAT vintage containing this address. "
            "If absent from the latest vintage, the address may have been demolished."
        ),
    )
    first_seen_in_data = models.DateField(
        null=True, blank=True, db_index=True,
        help_text=(
            "Earliest date this address appeared in any data source (FEC filings, "
            "voter files, Census). Cross-validates tiger_first_seen_year."
        ),
    )

    # ── siege_geo ForeignKeys (canonical) ────────────────────────────────
    siege_state = models.ForeignKey(
        "siege_geo.State", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_county = models.ForeignKey(
        "siege_geo.County", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_tract = models.ForeignKey(
        "siege_geo.Tract", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_block_group = models.ForeignKey(
        "siege_geo.BlockGroup", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_cd = models.ForeignKey(
        "siege_geo.CongressionalDistrict", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_vtd = models.ForeignKey(
        "siege_geo.VTD", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_sldl = models.ForeignKey(
        "siege_geo.StateLegislativeLower", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_sldu = models.ForeignKey(
        "siege_geo.StateLegislativeUpper", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )

    class Meta:
        db_table = "sw_geo_address"
        indexes = [
            models.Index(fields=["state_abbreviation", "city_name"]),
            models.Index(fields=["county_fips"]),
            models.Index(fields=["congressional_district"]),
            models.Index(fields=["census_year"]),
            models.Index(fields=["geocoded"]),
            models.Index(fields=["state_geoid", "county_geoid"]),
            models.Index(fields=["cd_geoid", "census_year"]),
            models.Index(fields=["vtd_geoid", "census_year"]),
            models.Index(fields=["sldl_geoid", "census_year"]),
            models.Index(fields=["sldu_geoid", "census_year"]),
        ]

    def __str__(self):
        return f"{self.primary_number} {self.street_name} {self.street_suffix}"

    def assign_census_units_from_fips(self, state_fips, county_fips, tract, block):
        """
        Construct GEOIDs from Census API FIPS codes (no spatial join needed).

        Use when the Census Geocoder returns FIPS codes directly.
        """
        if state_fips:
            self.state_geoid = state_fips
        if state_fips and county_fips:
            self.county_geoid = f"{state_fips}{county_fips}"
        if state_fips and county_fips and tract:
            self.tract_geoid = f"{state_fips}{county_fips}{tract}"
            if block and len(block) >= 1:
                self.block_group_geoid = f"{state_fips}{county_fips}{tract}{block[0]}"
            else:
                self.block_group_geoid = f"{state_fips}{county_fips}{tract}"
        if state_fips and county_fips and tract and block:
            self.block_geoid = f"{state_fips}{county_fips}{tract}{block}"

    def populate_foreign_keys(self):
        """
        Populate siege_geo FK references from GEOIDs.

        Call after census unit assignment to enable rich hierarchical queries
        like ``address.siege_vtd.county.state.name``.

        **Does not persist.** This method mutates the instance in memory and
        returns ``self``; the caller is responsible for calling ``.save()``
        (or batching via ``bulk_update``) when ready. This matches the
        :meth:`assign_census_units_from_fips` convention and the broader
        Django ORM convention that instance-mutating methods do not save.
        (F4 + F5 / SW#93 + SW#94 — pre-fix this method called ``self.save()``
        as a hidden side effect; ``assign_census_units_from_fips`` did not.
        The asymmetry surprised callers and the bulk-update integration was
        suboptimal because every populated address triggered an individual
        UPDATE.)
        """
        from siege_utilities.geo.django.models import (
            State, County, Tract, BlockGroup,
            CongressionalDistrict, VTD,
            StateLegislativeLower, StateLegislativeUpper,
        )

        fk_map = [
            ("state_geoid", "siege_state", State),
            ("county_geoid", "siege_county", County),
            ("tract_geoid", "siege_tract", Tract),
            ("block_group_geoid", "siege_block_group", BlockGroup),
            ("cd_geoid", "siege_cd", CongressionalDistrict),
            ("vtd_geoid", "siege_vtd", VTD),
            ("sldl_geoid", "siege_sldl", StateLegislativeLower),
            ("sldu_geoid", "siege_sldu", StateLegislativeUpper),
        ]

        for geoid_field, fk_field, model_cls in fk_map:
            geoid = getattr(self, geoid_field)
            if geoid:
                obj = model_cls.objects.filter(
                    geoid=geoid, vintage_year=self.census_year
                ).first()
                setattr(self, fk_field, obj)

        return self

    # F11 / SW#100 step-2 + step-2b helpers: temporal boundary history.
    #
    # The Address-level GEOID fields (cd_geoid, sldl_geoid, ...) are a
    # cache of the *current* boundary assignment. The authoritative
    # source for "which boundaries did this address belong to on date X"
    # and "every boundary this address has ever been in" is the
    # AddressBoundaryPeriod table, accessed through these helpers.
    #
    # The cache is kept in lockstep with ABP writes by the signal in
    # socialwarehouse/geo/signals.py (F11 step 2b). For new code:
    #   - reading the *current* assignment, use addr.{type}_geoid
    #     directly (fast-path; backed by the cache).
    #   - reading as-of-date or full history, use boundary_on,
    #     boundary_history, boundary_timeline, etc.
    # Both paths return the same answer for the current case.
    _BOUNDARY_TYPES = (
        "state", "county", "tract", "block_group", "block",
        "vtd", "cd", "sldl", "sldu",
    )

    def boundary_history(self, boundary_type=None):
        """Every recorded boundary assignment for this address.

        ``boundary_type``, if given, filters to ABP rows that carry a
        non-empty geoid for that type. Valid values: ``state``,
        ``county``, ``tract``, ``block_group``, ``block``, ``vtd``,
        ``cd``, ``sldl``, ``sldu``.

        Returns a queryset of :class:`AddressBoundaryPeriod` ordered
        most-recent-first by ``context_date`` then ``assigned_at``.
        Includes the linked ``vintage`` and ``redistricting_plan`` via
        ``select_related`` so callers can read the plan / vintage
        metadata without N+1 lookups.

        Notes:
          - Unfiltered (``boundary_type=None``) returns rows with
            sparse geoid fills: plan-bound CD rows have null sldl /
            sldu, plan-bound SLDL rows have null cd, etc. Each row
            carries the geoids for the boundary types its plan covers.
            Filter by ``boundary_type`` for the all-rows-have-this-geoid
            shape.
          - Rows with NULL ``context_date`` sort last under DESC
            (Postgres default for NULLS LAST). For most-recent-first
            timelines this is the expected behavior.
        """
        # NOTE: select_related on `redistricting_plan` triggers a SELECT
        # that includes `effective_from` / `effective_to` columns the
        # current siege_utilities migrations don't create (SU#527).
        # Loading the plan lazily via id-based lookup avoids that crash.
        # Restore once SU#527 lands and SW's SU pin is bumped.
        qs = self.boundary_periods.select_related("vintage")
        if boundary_type:
            if boundary_type not in self._BOUNDARY_TYPES:
                raise ValueError(
                    f"Unknown boundary_type {boundary_type!r}; "
                    f"expected one of {self._BOUNDARY_TYPES}"
                )
            field = f"{boundary_type}_geoid"
            qs = qs.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""})
        return qs.order_by("-context_date", "-assigned_at")

    def boundaries_on(self, on_date):
        """Boundaries this address was in on ``on_date``.

        For each boundary type, returns the ABP row whose ``context_date``
        is the most recent on-or-before ``on_date`` (with rows whose
        ``context_date`` is NULL treated as fallback / always-applicable).

        Returns a dict ``{boundary_type: AddressBoundaryPeriod}``.
        Missing keys mean no ABP row covers ``on_date`` for that type.

        NOTE: An earlier version of this helper resolved plan-bound rows
        by reading ``redistricting_plan.effective_from`` /
        ``effective_to``. Those columns are declared on the SU model but
        the SU migrations don't create them (SU#527). Until that lands,
        we use ``context_date`` as the temporal indicator — which
        ``assign_boundaries`` already sets to "the date this assignment
        is valid for" — and skip the plan-effective-range path entirely.
        Restore the richer resolution once SU#527 ships and SW's SU pin
        bumps.
        """
        from socialwarehouse.geo.models import CensusVintageConfig

        vintage = CensusVintageConfig.for_year(on_date.year)
        if not vintage:
            return {}

        periods = list(
            self.boundary_periods
            .filter(vintage=vintage)
            .filter(
                models.Q(context_date__lte=on_date)
                | models.Q(context_date__isnull=True)
            )
            .order_by(models.F("context_date").desc(nulls_last=True))
        )

        result = {}
        for btype in self._BOUNDARY_TYPES:
            field = f"{btype}_geoid"
            chosen = next(
                (p for p in periods if getattr(p, field, None)),
                None,
            )
            if chosen:
                result[btype] = chosen

        return result

    def current_boundaries(self):
        """Sugar for :meth:`boundaries_on(today)`.

        With the F11 step-2b signal-driven cache refresh in place,
        ``current_boundaries()[btype].{btype}_geoid`` returns the same
        value as ``self.{btype}_geoid`` for every type. The fast path
        is reading the cached field directly; this method exists for
        callers that want the ABP row's metadata (effective range, plan,
        assignment_method) alongside the geoid.

        "Today" is ``django.utils.timezone.localdate()`` — the date
        in the active timezone (or settings.TIME_ZONE). At midnight
        boundaries, two callers in different timezones may see
        different answers for an address whose temporal record changes
        on that day.
        """
        from django.utils import timezone

        return self.boundaries_on(timezone.localdate())

    def boundary_on(self, boundary_type, on_date):
        """The ABP row for one boundary type, as of ``on_date``.

        Sugar for ``self.boundaries_on(on_date).get(boundary_type)``.
        Returns the ABP row, or ``None`` if no row covers ``on_date``
        for that type. Validates ``boundary_type`` against the known
        set up-front so a typo doesn't silently return ``None``.
        """
        if boundary_type not in self._BOUNDARY_TYPES:
            raise ValueError(
                f"Unknown boundary_type {boundary_type!r}; "
                f"expected one of {self._BOUNDARY_TYPES}"
            )
        return self.boundaries_on(on_date).get(boundary_type)

    def boundary_at(self, boundary_type, position):
        """The ABP row at ``position`` in reverse-chron history for ``boundary_type``.

        ``position`` is 0-indexed (Python convention; the audience is
        data analysts, not domain users, so SQL/Python's 0-based
        indexing matches the caller reflex). ``position=0`` is the
        most recent ABP row for the given boundary type; ``position=4``
        is the fifth most recent.

        Returns ``None`` for out-of-range positions rather than
        raising; callers asking for "the 50th most recent CD" on an
        address with two CD periods get a clean ``None`` rather than
        an IndexError.

        For a slice (e.g. the 3rd through 8th most recent), use the
        underlying queryset directly:
            ``addr.boundary_history(boundary_type="cd")[2:8]``
        """
        if position < 0:
            raise ValueError(f"position must be non-negative, got {position}")
        qs = self.boundary_history(boundary_type=boundary_type)
        return qs[position:position + 1].first()

    def boundary_timeline(self, boundary_type):
        """Chronological timeline of one boundary type for this address.

        Returns a list of :class:`BoundaryTimelineEntry` namedtuples
        sorted oldest-first. Each entry exposes:

          - ``geoid`` — the boundary GEOID for that period.
          - ``effective_from`` — :class:`datetime.date` the period began,
            taken from the ABP row's ``context_date`` (or the linked
            vintage's start year when ``context_date`` is NULL).
          - ``effective_to`` — :class:`datetime.date` it ended, derived
            as the day before the next entry's ``effective_from``;
            ``None`` for the most recent entry ("still active").
          - ``plan_name`` — the redistricting plan name that established
            the assignment, or ``None`` for the Census-default (no plan)
            and for orphan FKs (non-existent plan id).
          - ``abp`` — the raw :class:`AddressBoundaryPeriod` row, for
            callers wanting fields beyond the four headline ones.

        Effective range derivation:
          We use ``context_date`` (set by ``assign_boundaries`` to
          "the date this assignment is valid for") to thread the
          timeline. ``effective_to`` is derived from the next entry's
          start. The first entry's ``effective_from`` falls back to
          the vintage's effective start year when its ``context_date``
          is NULL.

          An earlier version of this helper read ``effective_from`` /
          ``effective_to`` from the linked ``RedistrictingPlan`` row,
          but those columns are declared on the SU model without a
          matching migration (SU#527). Once that lands and SW's SU pin
          bumps, this method should be revised to prefer plan-side
          dates when available.

        Adjacent same-geoid rows are NOT collapsed. Callers wanting
        collapse-by-geoid can use :func:`itertools.groupby` on the
        result.
        """
        from datetime import date, timedelta

        if boundary_type not in self._BOUNDARY_TYPES:
            raise ValueError(
                f"Unknown boundary_type {boundary_type!r}; "
                f"expected one of {self._BOUNDARY_TYPES}"
            )

        # boundary_history returns newest-first; reverse to walk oldest-first.
        rows = list(reversed(list(self.boundary_history(boundary_type=boundary_type))))
        entries = []
        field = f"{boundary_type}_geoid"

        for i, abp in enumerate(rows):
            geoid = getattr(abp, field, None)
            if not geoid:
                continue

            eff_from = abp.context_date
            if eff_from is None and abp.vintage_id is not None:
                eff_from = date(abp.vintage.effective_start, 1, 1)

            eff_to = None
            if i + 1 < len(rows):
                next_abp = rows[i + 1]
                next_start = next_abp.context_date
                if next_start is None and next_abp.vintage_id is not None:
                    next_start = date(next_abp.vintage.effective_start, 1, 1)
                if next_start is not None:
                    eff_to = next_start - timedelta(days=1)

            plan_name = _safe_plan_name(abp.redistricting_plan_id)

            entries.append(BoundaryTimelineEntry(
                geoid=geoid,
                effective_from=eff_from,
                effective_to=eff_to,
                plan_name=plan_name,
                abp=abp,
            ))

        return entries

    def geoid_on(self, boundary_type, on_date):
        """The GEOID string for one boundary type as of ``on_date``, or None.

        Sugar for ``self.boundary_on(boundary_type, on_date).{boundary_type}_geoid``
        with None-safety: returns ``None`` if no ABP row covers
        ``on_date`` for that type, rather than raising AttributeError.
        """
        row = self.boundary_on(boundary_type, on_date)
        if row is None:
            return None
        return getattr(row, f"{boundary_type}_geoid", None) or None

    def current_geoid(self, boundary_type):
        """The GEOID string for one boundary type as of today, or None.

        Sugar for :meth:`geoid_on(boundary_type, today)`. With the
        F11 step-2b signal-driven cache refresh in place, returns the
        same value as ``self.{boundary_type}_geoid`` directly.

        "Today" is ``django.utils.timezone.localdate()``; see the note
        on :meth:`current_boundaries` for the midnight-boundary caveat.
        """
        from django.utils import timezone

        return self.geoid_on(boundary_type, timezone.localdate())


# Backwards-compatible alias
United_States_Address = Address
