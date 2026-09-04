from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from socialwarehouse.events.models import Event, EventLink, NarrativeEvent


def _mk_event(**kw):
    defaults = dict(event_type="narrative", event_date=date(2024, 5, 1))
    defaults.update(kw)
    return Event.objects.create(**defaults)


@pytest.mark.django_db
class TestEventLink(TestCase):
    def test_create_precedes_edge(self):
        source = _mk_event(event_date=date(2008, 1, 28))
        target = _mk_event(event_date=date(2008, 2, 5))
        link = EventLink.objects.create(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="Endorsement preceded a documented fundraising surge.",
        )
        assert link.edge_type == "precedes"
        assert link.source_event_id == source.id
        assert link.target_event_id == target.id

    def test_create_relates_to_edge(self):
        a = _mk_event()
        b = _mk_event()
        link = EventLink.objects.create(
            source_event=a,
            target_event=b,
            edge_type="relates_to",
            sourcing_note="Both events reference the same coalition of donors.",
        )
        assert link.edge_type == "relates_to"

    def test_self_loop_rejected_by_db_constraint(self):
        e = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventLink.objects.create(
                    source_event=e,
                    target_event=e,
                    edge_type="precedes",
                    sourcing_note="An event cannot precede itself.",
                )

    def test_empty_sourcing_note_rejected_by_db_constraint(self):
        source = _mk_event()
        target = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventLink.objects.create(
                    source_event=source,
                    target_event=target,
                    edge_type="precedes",
                    sourcing_note="",
                )

    def test_whitespace_only_sourcing_note_rejected_by_db_constraint(self):
        # The exact SW#369 lesson applied proactively: a literal
        # sourcing_note="" check alone would let "   " slip through.
        source = _mk_event()
        target = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventLink.objects.create(
                    source_event=source,
                    target_event=target,
                    edge_type="precedes",
                    sourcing_note="   ",
                )

    def test_undeclared_edge_type_rejected_by_db_constraint(self):
        source = _mk_event()
        target = _mk_event()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventLink.objects.create(
                    source_event=source,
                    target_event=target,
                    edge_type="not_a_real_edge_type",
                    sourcing_note="Some justification.",
                )

    def test_duplicate_edge_rejected_by_unique_constraint(self):
        source = _mk_event()
        target = _mk_event()
        EventLink.objects.create(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="First assertion of this claim.",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventLink.objects.create(
                    source_event=source,
                    target_event=target,
                    edge_type="precedes",
                    sourcing_note="A second, duplicate assertion of the same claim.",
                )

    def test_self_loop_via_update_rejected_by_db_constraint(self):
        # CheckConstraints are row-level and re-fire on UPDATE, not just
        # INSERT -- proving this holds, not just assuming it, since a
        # future refactor (e.g. moving self-loop enforcement into
        # save()-level Python) could silently regress this without an
        # INSERT-only test noticing.
        source = _mk_event()
        target = _mk_event()
        link = EventLink.objects.create(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="Valid at creation.",
        )
        link.target_event = source
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                link.save(update_fields=["target_event"])

    def test_many_to_one_multiple_sources_link_to_same_target(self):
        # One-to-many must hold in both directions: Dheeraj's worked
        # example (SW#370 comment) illustrates one source linking to many
        # targets; nothing should also prevent the reverse -- many
        # independent sources (e.g. three separate endorsements) all
        # relating to the same downstream target event.
        target = _mk_event()
        source_a = _mk_event()
        source_b = _mk_event()
        source_c = _mk_event()
        for source in (source_a, source_b, source_c):
            EventLink.objects.create(
                source_event=source,
                target_event=target,
                edge_type="relates_to",
                sourcing_note=f"Independent claim relating {source.id} to the target.",
            )
        assert target.incoming_links.count() == 3
        sources = set(target.incoming_links.values_list("source_event_id", flat=True))
        assert sources == {source_a.id, source_b.id, source_c.id}

    def test_same_pair_different_edge_types_both_allowed(self):
        source = _mk_event()
        target = _mk_event()
        EventLink.objects.create(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="Temporal claim: source happened first.",
        )
        EventLink.objects.create(
            source_event=source,
            target_event=target,
            edge_type="relates_to",
            sourcing_note="Separately, both events share a common donor network.",
        )
        assert EventLink.objects.filter(source_event=source, target_event=target).count() == 2

    def test_clean_rejects_self_loop(self):
        e = _mk_event()
        link = EventLink(
            source_event=e,
            target_event=e,
            edge_type="precedes",
            sourcing_note="An event cannot precede itself.",
        )
        with pytest.raises(ValidationError):
            link.clean()

    def test_clean_rejects_empty_sourcing_note(self):
        source = _mk_event()
        target = _mk_event()
        link = EventLink(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="",
        )
        with pytest.raises(ValidationError):
            link.clean()

    def test_clean_passes_for_well_formed_link(self):
        source = _mk_event()
        target = _mk_event()
        link = EventLink(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="A real justification.",
        )
        link.clean()  # should not raise

    def test_reverse_accessors(self):
        source = _mk_event()
        target = _mk_event()
        EventLink.objects.create(
            source_event=source,
            target_event=target,
            edge_type="precedes",
            sourcing_note="Justification.",
        )
        assert source.outgoing_links.count() == 1
        assert target.incoming_links.count() == 1
        assert source.outgoing_links.first().target_event_id == target.id
        assert target.incoming_links.first().source_event_id == source.id

    def test_one_to_many_kennedy_obama_worked_example(self):
        # Dheeraj's worked example (siege-analytics/socialwarehouse#370
        # comment, 2026-09-04): Ted Kennedy endorsing Barack Obama in the
        # 2008 primary plausibly links to *multiple* downstream events --
        # explicitly why the edge must support one-to-many, not just
        # one-to-one. A plain FK-pair row is one-to-many by construction;
        # this proves it against the concrete scenario named in the ticket.
        endorsement = NarrativeEvent.objects.create(
            event=_mk_event(event_date=date(2008, 1, 28)),
            narrative_event_type="endorsement",
            duration_mode="bounded",
            window_pre_days=0,
            window_post_days=180,
        ).event

        fundraising_email = _mk_event(event_type="transaction", event_date=date(2008, 1, 30))
        polling_shift = _mk_event(event_date=date(2008, 2, 1))
        second_endorsement = _mk_event(event_date=date(2008, 2, 3))

        EventLink.objects.create(
            source_event=endorsement,
            target_event=fundraising_email,
            edge_type="precedes",
            sourcing_note="Endorsement preceded a documented fundraising email blast.",
        )
        EventLink.objects.create(
            source_event=endorsement,
            target_event=polling_shift,
            edge_type="precedes",
            sourcing_note="Endorsement preceded a measurable polling shift.",
        )
        EventLink.objects.create(
            source_event=endorsement,
            target_event=second_endorsement,
            edge_type="relates_to",
            sourcing_note="Coverage of the endorsement is linked to a subsequent, separate endorsement.",
        )

        assert endorsement.outgoing_links.count() == 3
        targets = set(endorsement.outgoing_links.values_list("target_event_id", flat=True))
        assert targets == {fundraising_email.id, polling_shift.id, second_endorsement.id}
