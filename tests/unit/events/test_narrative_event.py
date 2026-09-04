from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from socialwarehouse.events.models import Event, NarrativeEvent


def _mk_event(**kw):
    defaults = dict(event_type="narrative", event_date=date(2024, 5, 1))
    defaults.update(kw)
    return Event.objects.create(**defaults)


@pytest.mark.django_db
class TestNarrativeEvent(TestCase):
    def test_create_bounded_narrative_event(self):
        e = _mk_event()
        ne = NarrativeEvent.objects.create(
            event=e,
            narrative_event_type="pledge_letter",
            duration_mode="bounded",
            window_pre_days=0,
            window_post_days=180,
        )
        assert ne.narrative_event_type == "pledge_letter"
        assert ne.duration_mode == "bounded"
        assert ne.window_pre_days == 0
        assert ne.window_post_days == 180
        assert ne.effective_to is None

    def test_create_structural_narrative_event_open_ended(self):
        e = _mk_event()
        ne = NarrativeEvent.objects.create(
            event=e,
            narrative_event_type="scandal",
            duration_mode="structural",
        )
        assert ne.duration_mode == "structural"
        assert ne.effective_to is None
        assert ne.window_pre_days is None
        assert ne.window_post_days is None

    def test_create_structural_narrative_event_closed(self):
        e = _mk_event()
        ne = NarrativeEvent.objects.create(
            event=e,
            narrative_event_type="resignation",
            duration_mode="structural",
            effective_to=date(2024, 8, 1),
        )
        assert ne.effective_to == date(2024, 8, 1)

    def test_bounded_mode_with_effective_to_rejected_by_db_constraint(self):
        e = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                NarrativeEvent.objects.create(
                    event=e,
                    narrative_event_type="speech",
                    duration_mode="bounded",
                    effective_to=date(2024, 8, 1),
                )

    def test_structural_mode_with_window_fields_rejected_by_db_constraint(self):
        e = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                NarrativeEvent.objects.create(
                    event=e,
                    narrative_event_type="endorsement",
                    duration_mode="structural",
                    window_pre_days=0,
                )

    def test_bounded_mode_with_no_window_fields_rejected_by_db_constraint(self):
        # A "bounded" event with neither window bound set is operationally
        # meaningless -- must be rejected, not silently accepted.
        e = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                NarrativeEvent.objects.create(
                    event=e,
                    narrative_event_type="pac_formation",
                    duration_mode="bounded",
                )

    def test_bounded_mode_with_only_post_window_set_succeeds(self):
        # window_pre_days/window_post_days are independently settable per
        # the ticket -- only one needs to be non-null.
        e = _mk_event()
        ne = NarrativeEvent.objects.create(
            event=e,
            narrative_event_type="pledge_letter",
            duration_mode="bounded",
            window_post_days=180,
        )
        assert ne.window_pre_days is None
        assert ne.window_post_days == 180

    def test_clean_rejects_bounded_with_no_window_fields(self):
        e = _mk_event()
        ne = NarrativeEvent(
            event=e,
            narrative_event_type="pac_formation",
            duration_mode="bounded",
        )
        with pytest.raises(ValidationError):
            ne.clean()

    def test_clean_rejects_bounded_with_effective_to(self):
        e = _mk_event()
        ne = NarrativeEvent(
            event=e,
            narrative_event_type="speech",
            duration_mode="bounded",
            effective_to=date(2024, 8, 1),
        )
        with pytest.raises(ValidationError):
            ne.clean()

    def test_clean_rejects_structural_with_window_fields(self):
        e = _mk_event()
        ne = NarrativeEvent(
            event=e,
            narrative_event_type="endorsement",
            duration_mode="structural",
            window_post_days=90,
        )
        with pytest.raises(ValidationError):
            ne.clean()

    def test_clean_passes_for_well_formed_bounded_event(self):
        e = _mk_event()
        ne = NarrativeEvent(
            event=e,
            narrative_event_type="indictment",
            duration_mode="bounded",
            window_pre_days=0,
            window_post_days=30,
        )
        ne.clean()  # should not raise

    def test_access_via_event(self):
        e = _mk_event()
        NarrativeEvent.objects.create(
            event=e,
            narrative_event_type="pac_formation",
            duration_mode="bounded",
            window_post_days=180,
        )
        assert e.narrative_detail.narrative_event_type == "pac_formation"

    def test_str(self):
        e = _mk_event()
        ne = NarrativeEvent(event=e, narrative_event_type="scandal")
        assert "scandal" in str(ne)
        assert "2024-05-01" in str(ne)
