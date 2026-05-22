"""
Tests for SW#251 — DimPerson, FactPersonScore, FactVoteHistory.

Per writing-tests:1, each test fails on revert of the named feature.
"""

from datetime import date, datetime, timezone

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError


@pytest.mark.django_db
class TestDimPerson:
    def _person_kwargs(self, **overrides):
        defaults = {
            "vendor": "ts",
            "vendor_voter_id": "TS-100",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "registration_state": "TX",
            "registration_status": "active",
        }
        defaults.update(overrides)
        return defaults

    def test_create_minimum_required(self):
        from socialwarehouse.warehouse.models import DimPerson
        p = DimPerson.objects.create(**self._person_kwargs())
        assert p.id is not None
        assert p.is_registered_voter is True
        assert p.pdi_extras == {}
        assert p.ts_extras == {}

    def test_unique_vendor_voter_id(self):
        from socialwarehouse.warehouse.models import DimPerson
        DimPerson.objects.create(**self._person_kwargs())
        with pytest.raises(IntegrityError):
            DimPerson.objects.create(**self._person_kwargs())

    def test_same_voter_id_different_vendor_allowed(self):
        from socialwarehouse.warehouse.models import DimPerson
        DimPerson.objects.create(**self._person_kwargs(vendor="ts", vendor_voter_id="100"))
        # Should not raise — natural key includes vendor.
        DimPerson.objects.create(**self._person_kwargs(vendor="l2", vendor_voter_id="100"))

    def test_is_registered_voter_property(self):
        from socialwarehouse.warehouse.models import DimPerson
        cases = [
            ("active", True),
            ("inactive", True),
            ("pending", True),
            ("purged", False),
            ("not_registered", False),
            ("deceased", False),
        ]
        for i, (status, expected) in enumerate(cases):
            p = DimPerson.objects.create(**self._person_kwargs(
                vendor_voter_id=f"REG-{i}", registration_status=status,
            ))
            assert p.is_registered_voter is expected, status

    def test_jsonfield_roundtrip(self):
        from socialwarehouse.warehouse.models import DimPerson
        p = DimPerson.objects.create(**self._person_kwargs(
            ts_extras={"tsmart_partisan_score": "55", "tsmart_segment": "X1"},
            l2_extras={"l2_internal_id": "LX-9"},
        ))
        p.refresh_from_db()
        assert p.ts_extras == {"tsmart_partisan_score": "55", "tsmart_segment": "X1"}
        assert p.l2_extras == {"l2_internal_id": "LX-9"}
        assert p.pdi_extras == {}

    def test_address_protect(self):
        from socialwarehouse.geo.models import Address
        from socialwarehouse.warehouse.models import DimPerson
        addr = Address.objects.create(state_abbreviation="TX")
        DimPerson.objects.create(**self._person_kwargs(address=addr))
        with pytest.raises(ProtectedError):
            addr.delete()


@pytest.mark.django_db
class TestFactPersonScore:
    def _person(self):
        from socialwarehouse.warehouse.models import DimPerson
        return DimPerson.objects.create(
            vendor="ts", vendor_voter_id="SCORE-1",
            registration_state="TX", registration_status="active",
        )

    def test_create(self):
        from socialwarehouse.warehouse.models import FactPersonScore
        p = self._person()
        s = FactPersonScore.objects.create(
            person=p, score_type="partisan_score",
            value=0.72, source_vendor="ts",
            methodology_version="2024Q4",
            scored_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert s.id is not None

    def test_unique_per_methodology(self):
        from socialwarehouse.warehouse.models import FactPersonScore
        p = self._person()
        kwargs = dict(
            person=p, score_type="partisan_score", value=0.5,
            source_vendor="ts", methodology_version="v1",
            scored_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        FactPersonScore.objects.create(**kwargs)
        with pytest.raises(IntegrityError):
            FactPersonScore.objects.create(**kwargs)

    def test_same_score_type_different_vendor_allowed(self):
        from socialwarehouse.warehouse.models import FactPersonScore
        p = self._person()
        common = dict(
            person=p, score_type="partisan_score", value=0.5,
            methodology_version="v1",
            scored_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        FactPersonScore.objects.create(source_vendor="ts", **common)
        FactPersonScore.objects.create(source_vendor="l2", **common)

    def test_cascade_on_person_delete(self):
        from socialwarehouse.warehouse.models import DimPerson, FactPersonScore
        p = self._person()
        FactPersonScore.objects.create(
            person=p, score_type="x", value=1.0, source_vendor="ts",
            scored_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        DimPerson.objects.filter(pk=p.pk).delete()
        assert FactPersonScore.objects.count() == 0


@pytest.mark.django_db
class TestFactVoteHistory:
    def _person(self):
        from socialwarehouse.warehouse.models import DimPerson
        return DimPerson.objects.create(
            vendor="ts", vendor_voter_id="VH-1",
            registration_state="TX", registration_status="active",
        )

    def test_create(self):
        from socialwarehouse.warehouse.models import FactVoteHistory
        p = self._person()
        v = FactVoteHistory.objects.create(
            person=p, election_date=date(2024, 11, 5),
            election_type="general", voted_method="in_person",
            source_vendor="ts",
        )
        assert v.id is not None

    def test_unique_per_vendor(self):
        from socialwarehouse.warehouse.models import FactVoteHistory
        p = self._person()
        kwargs = dict(
            person=p, election_date=date(2024, 11, 5),
            election_type="general", source_vendor="ts",
        )
        FactVoteHistory.objects.create(**kwargs)
        with pytest.raises(IntegrityError):
            FactVoteHistory.objects.create(**kwargs)

    def test_two_vendors_same_vote_allowed(self):
        from socialwarehouse.warehouse.models import FactVoteHistory
        p = self._person()
        common = dict(
            person=p, election_date=date(2024, 11, 5),
            election_type="general",
        )
        FactVoteHistory.objects.create(source_vendor="ts", **common)
        FactVoteHistory.objects.create(source_vendor="l2", **common)


pyspark = pytest.importorskip("pyspark", reason="pyspark not installed in this env; Delta-schema tests run in CI docker-build job")


class TestDeltaSchemas:
    """Schemas must be importable + registered. Pyspark import-only test;
    no Spark session required."""

    def test_silver_persons_imports(self):
        from socialwarehouse.delta.tables import SILVER_PERSONS
        names = {f.name for f in SILVER_PERSONS.fields}
        # Natural key columns
        assert "vendor" in names
        assert "vendor_voter_id" in names
        assert "person_key" in names
        # Map-typed extension bag
        assert "vendor_extras" in names

    def test_silver_person_scores_tall(self):
        from socialwarehouse.delta.tables import SILVER_PERSON_SCORES
        names = {f.name for f in SILVER_PERSON_SCORES.fields}
        assert {"person_key", "score_type", "value", "source_vendor", "methodology_version"} <= names

    def test_silver_vote_history(self):
        from socialwarehouse.delta.tables import SILVER_VOTE_HISTORY
        names = {f.name for f in SILVER_VOTE_HISTORY.fields}
        assert {"person_key", "election_date", "election_type", "source_vendor"} <= names

    def test_registry_entries(self):
        from socialwarehouse.delta.tables import TABLES
        for key in (
            "bronze.voter_file_ts",
            "bronze.voter_file_l2",
            "bronze.voter_file_catalist",
            "bronze.voter_file_pdi",
            "silver.persons",
            "silver.person_scores",
            "silver.vote_history",
        ):
            assert key in TABLES, key
            assert "schema" in TABLES[key]
            assert "path" in TABLES[key]
            assert "partition_by" in TABLES[key]

    def test_silver_persons_partitioned_by_state_vendor(self):
        from socialwarehouse.delta.tables import TABLES
        assert TABLES["silver.persons"]["partition_by"] == ["registration_state", "vendor"]
