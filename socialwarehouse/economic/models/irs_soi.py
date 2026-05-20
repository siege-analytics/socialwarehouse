"""IRS SOI ZIP-code-level tax statistics.

Per E Phase 3 / E Q2 = (b) new `irs-soi` Vintage kind, Q3 = (a)
versionable income-bucket model.

IRS publishes ZIP-code-level aggregates each year for individual
income tax returns, broken out by ~6 AGI buckets (e.g.,
$0-$25K, $25-$50K, ..., $200K+). The bucket boundaries are
occasionally re-cut, so a per-vintage `IRSSOIIncomeBucket` keeps
historic data interpretable.

Keyed long-format consistent with D and E Phase 1:
(vintage, boundary_type='zcta', geoid, agi_bin) → value columns.
"""

from django.db import models


class IRSSOIIncomeBucket(models.Model):
    """AGI bucket definition for a given SOI vintage.

    Per Q3, buckets are vintage-scoped so historic shifts in bin
    boundaries don't corrupt cross-year reads.
    """

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="irs_soi_buckets",
        limit_choices_to={"kind": "irs-soi"},
    )
    bucket_code = models.PositiveSmallIntegerField(
        help_text="IRS SOI `agi_stub` code, typically 1-6.",
    )
    label = models.CharField(
        max_length=80,
        help_text="Human label, e.g. '$25,000 under $50,000'.",
    )
    lower_bound = models.BigIntegerField(
        null=True, blank=True,
        help_text="Inclusive lower bound in whole dollars; NULL = open-ended low.",
    )
    upper_bound = models.BigIntegerField(
        null=True, blank=True,
        help_text="Exclusive upper bound in whole dollars; NULL = open-ended high.",
    )

    class Meta:
        db_table = "sw_economic_irs_soi_bucket"
        verbose_name = "IRS SOI Income Bucket"
        unique_together = [["vintage", "bucket_code"]]
        ordering = ["vintage", "bucket_code"]

    def __str__(self):
        return f"{self.vintage.name} bucket {self.bucket_code}: {self.label}"


class IRSSOIAggregate(models.Model):
    """One row per (vintage, ZCTA, AGI bucket).

    Boundary is always zcta in Phase 3 (SOI ZIP-code release). Future
    phases may add county / state rollups using the same model.
    """

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="irs_soi_aggregates",
        limit_choices_to={"kind": "irs-soi"},
    )
    boundary_type = models.CharField(
        max_length=30, db_index=True, default="zcta",
    )
    geoid = models.CharField(
        max_length=20, db_index=True,
        help_text="5-digit ZCTA for zcta rows.",
    )
    agi_bin = models.ForeignKey(
        "sw_economic.IRSSOIIncomeBucket",
        on_delete=models.CASCADE,
        related_name="aggregates",
    )

    return_count = models.BigIntegerField(
        null=True, blank=True,
        help_text="Number of returns (IRS `N1`).",
    )
    exemption_count = models.BigIntegerField(
        null=True, blank=True,
        help_text="Number of exemptions (IRS `NUMDEP` + filers).",
    )
    agi_total = models.BigIntegerField(
        null=True, blank=True,
        help_text="Total adjusted gross income, whole dollars (IRS `A00100`).",
    )
    taxable_income_total = models.BigIntegerField(
        null=True, blank=True,
        help_text="Total taxable income, whole dollars (IRS `A04800`).",
    )
    total_tax_total = models.BigIntegerField(
        null=True, blank=True,
        help_text="Total tax liability, whole dollars (IRS `A06500`).",
    )

    class Meta:
        db_table = "sw_economic_irs_soi_aggregate"
        verbose_name = "IRS SOI Aggregate"
        unique_together = [["vintage", "boundary_type", "geoid", "agi_bin"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["vintage", "agi_bin"]),
        ]

    def __str__(self):
        return (
            f"{self.vintage.name} {self.boundary_type}:{self.geoid} "
            f"bucket={self.agi_bin.bucket_code}"
        )
