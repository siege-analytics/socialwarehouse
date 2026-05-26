from django.db import models

from socialwarehouse.core.mixins import (
    IdentifiableModel,
    SourceAwareModel,
    generate_entity_uuid4,
)


CHAMBER_CHOICES = [
    ("senate", "Senate"),
    ("house", "House"),
    ("upper", "Upper Chamber (state)"),
    ("lower", "Lower Chamber (state)"),
    ("at_large", "At-Large"),
    ("executive", "Executive"),
]

ELECTION_TYPE_CHOICES = [
    ("general", "General"),
    ("primary", "Primary"),
    ("special", "Special"),
    ("runoff", "Runoff"),
]

TERM_TYPE_CHOICES = [
    ("elected", "Elected"),
    ("appointed", "Appointed"),
    ("special_election", "Special Election"),
    ("acting", "Acting / Interim"),
]


class Office(SourceAwareModel, IdentifiableModel):
    """Persistent identity for a political office.

    An Office is "US House TX-07" — it persists across redistricting.
    The plan-specific geographic realization is a Seat.

    Uses SourceAwareModel's jurisdiction_level/jurisdiction_state for
    jurisdiction scoping. Merge key: (jurisdiction_level, jurisdiction_state,
    chamber, district_number).
    """

    name = models.CharField(max_length=255)
    chamber = models.CharField(
        max_length=20,
        choices=CHAMBER_CHOICES,
        blank=True,
        default="",
        db_index=True,
    )
    district_number = models.CharField(
        max_length=10,
        blank=True,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Office"
        verbose_name_plural = "Offices"
        db_table = "sw_office"
        unique_together = [
            ("jurisdiction_level", "jurisdiction_state", "chamber", "district_number"),
        ]
        indexes = [
            models.Index(
                fields=["jurisdiction_level", "jurisdiction_state"],
                name="idx_office_jurisdiction",
            ),
            models.Index(
                fields=["chamber", "district_number"],
                name="idx_office_chamber_district",
            ),
        ]

    def __str__(self):
        parts = [self.name]
        if self.district_number:
            parts.append(f"District {self.district_number}")
        return " — ".join(parts)


class Seat(models.Model):
    """Plan-specific geographic realization of an Office.

    When redistricting changes boundaries, a new Seat row is created
    for the same Office. The Office persists; the Seat is temporal.
    """

    seat_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.CASCADE,
        related_name="seats",
    )
    redistricting_plan_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Identifier for the redistricting plan (e.g., '2020_enacted')",
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    boundary_geoid = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="GEOID of the geographic boundary for this seat",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Seat"
        verbose_name_plural = "Seats"
        db_table = "sw_seat"
        unique_together = [("office", "redistricting_plan_id")]
        indexes = [
            models.Index(
                fields=["effective_from", "effective_to"],
                name="idx_seat_temporal",
            ),
            models.Index(
                fields=["boundary_geoid"],
                name="idx_seat_geoid",
            ),
        ]

    @property
    def is_current(self):
        return self.effective_to is None

    def __str__(self):
        plan = f" ({self.redistricting_plan_id})" if self.redistricting_plan_id else ""
        return f"{self.office}{plan}"


class Election(SourceAwareModel):
    """An election event: date, jurisdiction, type."""

    election_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    election_date = models.DateField(db_index=True)
    election_type = models.CharField(
        max_length=20,
        choices=ELECTION_TYPE_CHOICES,
        db_index=True,
    )
    year = models.PositiveSmallIntegerField(
        db_index=True,
        help_text="Election year, derived from election_date",
    )

    class Meta:
        verbose_name = "Election"
        verbose_name_plural = "Elections"
        db_table = "sw_election"
        unique_together = [
            ("election_date", "jurisdiction_state", "election_type"),
        ]
        indexes = [
            models.Index(
                fields=["year", "jurisdiction_state"],
                name="idx_election_year_state",
            ),
            models.Index(
                fields=["election_date", "election_type"],
                name="idx_election_date_type",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.election_date:
            self.year = self.election_date.year
        super().save(*args, **kwargs)

    def __str__(self):
        state = f" {self.jurisdiction_state}" if self.jurisdiction_state else ""
        return f"{self.election_date} {self.election_type}{state}"


class ElectoralContest(models.Model):
    """What is being contested in a specific election.

    Links an Office/Seat to an Election. Candidates are Persons with
    Role "candidate" pointing at this contest's office.
    """

    contest_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="contests",
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.CASCADE,
        related_name="contests",
    )
    seat = models.ForeignKey(
        Seat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contests",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Electoral Contest"
        verbose_name_plural = "Electoral Contests"
        db_table = "sw_electoral_contest"
        unique_together = [("election", "office")]
        indexes = [
            models.Index(
                fields=["election", "office"],
                name="idx_contest_election_office",
            ),
        ]

    def __str__(self):
        return f"{self.office} in {self.election}"


class OfficeTerm(models.Model):
    """Who holds an office and when.

    Generic: handles regular terms, special election remainder terms,
    and appointments. CongressionalTerm fields (congress_number) are
    nullable columns on this single table rather than a separate
    model — keeps queries simple for the common case.
    """

    term_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    person_uuid = models.UUIDField(
        db_index=True,
        help_text="entity_uuid of the Person holding this office",
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    term_type = models.CharField(
        max_length=20,
        choices=TERM_TYPE_CHOICES,
        default="elected",
        db_index=True,
    )
    congress_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Congress number (e.g., 118 for 118th Congress). Federal only.",
    )
    data_source = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Office Term"
        verbose_name_plural = "Office Terms"
        db_table = "sw_office_term"
        indexes = [
            models.Index(
                fields=["office", "person_uuid"],
                name="idx_term_office_person",
            ),
            models.Index(
                fields=["start_date", "end_date"],
                name="idx_term_temporal",
            ),
            models.Index(
                fields=["congress_number"],
                name="idx_term_congress",
            ),
        ]

    @property
    def is_current(self):
        return self.end_date is None

    def __str__(self):
        end = self.end_date or "present"
        return f"{self.office}: {self.person_uuid} ({self.start_date} to {end})"
