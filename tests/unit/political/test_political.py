import uuid
from datetime import date

import pytest
from django.test import TestCase

from socialwarehouse.core.mixins import generate_entity_uuid5
from socialwarehouse.political.models import (
    Election,
    ElectoralContest,
    Office,
    OfficeTerm,
    Seat,
)


def _make_office(**kwargs):
    defaults = dict(
        entity_uuid=generate_entity_uuid5("federal", "TX", "house", "07"),
        name="US House TX-07",
        jurisdiction_level="federal",
        jurisdiction_state="TX",
        chamber="house",
        district_number="07",
        data_source="congress",
    )
    defaults.update(kwargs)
    return Office.objects.create(**defaults)


@pytest.mark.django_db
class TestOffice(TestCase):
    def test_create_office(self):
        office = _make_office()
        assert office.entity_uuid is not None
        assert office.name == "US House TX-07"
        assert office.chamber == "house"

    def test_office_persists_across_redistricting(self):
        office = _make_office()
        Seat.objects.create(
            office=office,
            redistricting_plan_id="2010_enacted",
            effective_from=date(2013, 1, 3),
            effective_to=date(2022, 12, 31),
        )
        Seat.objects.create(
            office=office,
            redistricting_plan_id="2020_enacted",
            effective_from=date(2023, 1, 3),
        )
        assert office.seats.count() == 2

    def test_natural_key_uniqueness(self):
        _make_office()
        with pytest.raises(Exception):
            Office.objects.create(
                entity_uuid=generate_entity_uuid5("federal", "TX", "house", "07-dup"),
                name="Duplicate Office",
                jurisdiction_level="federal",
                jurisdiction_state="TX",
                chamber="house",
                district_number="07",
            )

    def test_str(self):
        office = Office(
            name="US House TX-07",
            district_number="07",
        )
        s = str(office)
        assert "US House TX-07" in s
        assert "District 07" in s

    def test_str_without_district(self):
        office = Office(name="Governor of Texas")
        assert "Governor of Texas" in str(office)


@pytest.mark.django_db
class TestSeat(TestCase):
    def test_create_seat(self):
        office = _make_office()
        seat = Seat.objects.create(
            office=office,
            redistricting_plan_id="2020_enacted",
            effective_from=date(2023, 1, 3),
            boundary_geoid="4807",
        )
        assert seat.seat_uuid is not None
        assert seat.is_current is True

    def test_expired_seat(self):
        office = _make_office()
        seat = Seat.objects.create(
            office=office,
            redistricting_plan_id="2010_enacted",
            effective_from=date(2013, 1, 3),
            effective_to=date(2022, 12, 31),
        )
        assert seat.is_current is False

    def test_unique_office_plan(self):
        office = _make_office()
        Seat.objects.create(office=office, redistricting_plan_id="2020_enacted")
        with pytest.raises(Exception):
            Seat.objects.create(office=office, redistricting_plan_id="2020_enacted")


@pytest.mark.django_db
class TestElection(TestCase):
    def test_create_election(self):
        e = Election.objects.create(
            election_date=date(2024, 11, 5),
            election_type="general",
            jurisdiction_level="federal",
            jurisdiction_state="TX",
            data_source="rdh",
            year=2024,
        )
        assert e.election_uuid is not None
        assert e.year == 2024

    def test_year_auto_derived_on_save(self):
        e = Election(
            election_date=date(2026, 11, 3),
            election_type="general",
            jurisdiction_state="TX",
        )
        e.save()
        assert e.year == 2026

    def test_natural_key_uniqueness(self):
        Election.objects.create(
            election_date=date(2024, 11, 5),
            election_type="general",
            jurisdiction_state="TX",
            year=2024,
        )
        with pytest.raises(Exception):
            Election.objects.create(
                election_date=date(2024, 11, 5),
                election_type="general",
                jurisdiction_state="TX",
                year=2024,
            )

    def test_str(self):
        e = Election(
            election_date=date(2024, 11, 5),
            election_type="general",
            jurisdiction_state="TX",
        )
        s = str(e)
        assert "2024-11-05" in s
        assert "general" in s
        assert "TX" in s


@pytest.mark.django_db
class TestElectoralContest(TestCase):
    def setUp(self):
        self.office = _make_office()
        self.election = Election.objects.create(
            election_date=date(2024, 11, 5),
            election_type="general",
            jurisdiction_state="TX",
            year=2024,
        )

    def test_create_contest(self):
        contest = ElectoralContest.objects.create(
            election=self.election,
            office=self.office,
        )
        assert contest.contest_uuid is not None
        assert contest.seat is None

    def test_contest_with_seat(self):
        seat = Seat.objects.create(
            office=self.office,
            redistricting_plan_id="2020_enacted",
        )
        contest = ElectoralContest.objects.create(
            election=self.election,
            office=self.office,
            seat=seat,
        )
        assert contest.seat == seat

    def test_unique_election_office(self):
        ElectoralContest.objects.create(
            election=self.election,
            office=self.office,
        )
        with pytest.raises(Exception):
            ElectoralContest.objects.create(
                election=self.election,
                office=self.office,
            )

    def test_full_chain_election_to_term(self):
        """Model: US House TX-07 contested in 2024 general, won by Person X."""
        seat = Seat.objects.create(
            office=self.office,
            redistricting_plan_id="2020_enacted",
            effective_from=date(2023, 1, 3),
        )
        contest = ElectoralContest.objects.create(
            election=self.election,
            office=self.office,
            seat=seat,
        )
        winner = uuid.uuid4()
        term = OfficeTerm.objects.create(
            office=self.office,
            person_uuid=winner,
            start_date=date(2025, 1, 3),
            end_date=date(2027, 1, 3),
            term_type="elected",
            congress_number=119,
        )
        chain_contest = ElectoralContest.objects.get(
            election__election_date=date(2024, 11, 5),
            office=self.office,
        )
        chain_term = OfficeTerm.objects.get(
            office=chain_contest.office,
            start_date=date(2025, 1, 3),
        )
        assert chain_term.person_uuid == winner
        assert chain_term.congress_number == 119


@pytest.mark.django_db
class TestOfficeTerm(TestCase):
    def setUp(self):
        self.office = _make_office()

    def test_create_term(self):
        person = uuid.uuid4()
        term = OfficeTerm.objects.create(
            office=self.office,
            person_uuid=person,
            start_date=date(2023, 1, 3),
            term_type="elected",
        )
        assert term.term_uuid is not None
        assert term.is_current is True

    def test_expired_term(self):
        term = OfficeTerm.objects.create(
            office=self.office,
            person_uuid=uuid.uuid4(),
            start_date=date(2021, 1, 3),
            end_date=date(2023, 1, 2),
            term_type="elected",
        )
        assert term.is_current is False

    def test_congressional_term(self):
        term = OfficeTerm.objects.create(
            office=self.office,
            person_uuid=uuid.uuid4(),
            start_date=date(2025, 1, 3),
            term_type="elected",
            congress_number=119,
        )
        assert term.congress_number == 119

    def test_appointed_term(self):
        term = OfficeTerm.objects.create(
            office=self.office,
            person_uuid=uuid.uuid4(),
            start_date=date(2024, 3, 15),
            term_type="appointed",
        )
        assert term.term_type == "appointed"

    def test_special_election_remainder_term(self):
        term = OfficeTerm.objects.create(
            office=self.office,
            person_uuid=uuid.uuid4(),
            start_date=date(2024, 6, 1),
            end_date=date(2025, 1, 2),
            term_type="special_election",
            congress_number=118,
        )
        assert term.term_type == "special_election"
        assert term.is_current is False

    def test_temporal_query_who_held_office_on_date(self):
        person_a = uuid.uuid4()
        person_b = uuid.uuid4()
        OfficeTerm.objects.create(
            office=self.office,
            person_uuid=person_a,
            start_date=date(2021, 1, 3),
            end_date=date(2023, 1, 2),
            term_type="elected",
        )
        OfficeTerm.objects.create(
            office=self.office,
            person_uuid=person_b,
            start_date=date(2023, 1, 3),
            term_type="elected",
        )
        query_date = date(2022, 6, 15)
        holders = OfficeTerm.objects.filter(
            office=self.office,
            start_date__lte=query_date,
        ).exclude(
            end_date__isnull=False,
            end_date__lt=query_date,
        )
        assert holders.count() == 1
        assert holders.first().person_uuid == person_a

    def test_str(self):
        term = OfficeTerm(
            office=self.office,
            person_uuid=uuid.uuid4(),
            start_date=date(2025, 1, 3),
        )
        s = str(term)
        assert "2025-01-03" in s
        assert "present" in s
