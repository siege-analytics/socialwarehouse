"""Regression test for W4 (SW#108): CV reliability thresholds are
hoisted to module-scope constants and the RELIABILITY_CHOICES strings
mirror the constant values.

Behavior tests: instantiate FactACSEstimate with CVs around the
thresholds and assert compute_reliability returns the documented band.
"""

from django.test import SimpleTestCase

from socialwarehouse.warehouse.models.facts import (
    CV_HIGH_THRESHOLD,
    CV_MEDIUM_THRESHOLD,
    FactACSEstimate,
)


class TestCVThresholds(SimpleTestCase):

    def test_module_constants_match_census_published_bands(self):
        # Census Bureau guidance: high reliability < 12%, medium 12-40%,
        # low > 40%. If these constants change, downstream analytics
        # using the same bands must be aware.
        assert CV_HIGH_THRESHOLD == 12
        assert CV_MEDIUM_THRESHOLD == 40

    def test_choices_strings_mirror_constants(self):
        # The display strings are derived from the constants, so a
        # change to the constants flows through to the admin labels.
        choices_dict = dict(FactACSEstimate.RELIABILITY_CHOICES)
        assert f"< {CV_HIGH_THRESHOLD}%" in choices_dict["high"]
        assert f"{CV_HIGH_THRESHOLD}-{CV_MEDIUM_THRESHOLD}%" in choices_dict["medium"]
        assert f"> {CV_MEDIUM_THRESHOLD}%" in choices_dict["low"]

    def test_compute_reliability_below_high_threshold(self):
        f = FactACSEstimate(estimate=100, coefficient_of_variation=CV_HIGH_THRESHOLD - 1)
        assert f.compute_reliability() == "high"

    def test_compute_reliability_at_high_threshold_is_medium(self):
        # Threshold semantics: < CV_HIGH_THRESHOLD is high; == is medium.
        f = FactACSEstimate(estimate=100, coefficient_of_variation=CV_HIGH_THRESHOLD)
        assert f.compute_reliability() == "medium"

    def test_compute_reliability_between_thresholds_is_medium(self):
        f = FactACSEstimate(estimate=100, coefficient_of_variation=25)
        assert f.compute_reliability() == "medium"

    def test_compute_reliability_at_medium_threshold_is_low(self):
        f = FactACSEstimate(estimate=100, coefficient_of_variation=CV_MEDIUM_THRESHOLD)
        assert f.compute_reliability() == "low"

    def test_compute_reliability_suppressed_when_cv_none(self):
        f = FactACSEstimate(estimate=100, coefficient_of_variation=None)
        assert f.compute_reliability() == "suppressed"

    def test_compute_reliability_uses_absolute_value(self):
        # Negative CV is degenerate but defensible — treat magnitude as
        # the bin selector.
        f = FactACSEstimate(estimate=100, coefficient_of_variation=-5)
        assert f.compute_reliability() == "high"
