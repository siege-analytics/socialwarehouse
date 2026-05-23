"""Tests for the civic_lookup endpoint (SW#272).

DRF + DRF-GIS composition of geo.Address F11 boundary-cache fields
+ optional DimPerson surfacing + optional GeoJSON Point geometry.
"""

from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse


@pytest.fixture
def api_client(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="civic-lookup-test")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def address_full(db):
    """Address row with every boundary-cache field populated."""
    from socialwarehouse.geo.models import Address
    return Address.objects.create(
        primary_number="123",
        street_name="Main",
        street_suffix="St",
        city_name="Austin",
        state_abbreviation="TX",
        latitude=Decimal("30.2672"),
        longitude=Decimal("-97.7431"),
        geom=Point(-97.7431, 30.2672, srid=4326),
        geocoded=True,
        geocode_source="census-batch",
        census_year=2020,
        state_geoid="48",
        county_geoid="48453",
        tract_geoid="48453000601",
        block_group_geoid="484530006011",
        block_geoid="484530006011001",
        vtd_geoid="48453000001",
        cd_geoid="4810",
        sldu_geoid="4814",
        sldl_geoid="48049",
        zcta_geoid="78701",
    )


@pytest.fixture
def address_no_cd(db):
    """Address row with cd_geoid null — to test omission."""
    from socialwarehouse.geo.models import Address
    return Address.objects.create(
        primary_number="456",
        street_name="Oak",
        city_name="Houston",
        state_abbreviation="TX",
        latitude=Decimal("29.7604"),
        longitude=Decimal("-95.3698"),
        census_year=2020,
        state_geoid="48",
        county_geoid="48201",
    )


@pytest.fixture
def dim_geography_tx(db):
    """DimGeography rows for Texas + Travis County + TX-10."""
    from socialwarehouse.warehouse.models import DimGeography
    DimGeography.objects.create(
        geoid="48", name="Texas", vintage_year=2020, summary_level="state",
        state_fips="48",
    )
    DimGeography.objects.create(
        geoid="48453", name="Travis County", vintage_year=2020,
        summary_level="county", state_fips="48",
    )
    DimGeography.objects.create(
        geoid="4810", name="TX-10", vintage_year=2020, summary_level="cd",
        state_fips="48",
    )


@pytest.fixture
def redistricting_cycle_2020(db):
    from socialwarehouse.warehouse.models import DimRedistrictingCycle
    return DimRedistrictingCycle.objects.create(
        cycle_year=2020, census_year=2020, first_election_year=2022,
    )


@pytest.fixture
def lookup_url():
    return reverse("geo:civic_lookup")


@pytest.mark.django_db
class TestErrors:
    def test_missing_address_returns_400(self, api_client, lookup_url):
        resp = api_client.get(lookup_url)
        assert resp.status_code == 400
        assert resp.json()["code"] == "missing_address"

    def test_empty_address_returns_400(self, api_client, lookup_url):
        resp = api_client.get(lookup_url, {"address": "   "})
        assert resp.status_code == 400
        assert resp.json()["code"] == "missing_address"

    def test_address_not_found_returns_404(self, api_client, lookup_url):
        resp = api_client.get(lookup_url, {"address": "999 Nowhere St, Nullsville, ZZ 00000"})
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "address_not_found"
        assert "geocode" in body["hint"]

    def test_address_not_found_with_state_filter(self, api_client, lookup_url):
        resp = api_client.get(
            lookup_url,
            {"address": "999 Nowhere St, Nullsville, ZZ 00000", "state": "tx"},
        )
        assert resp.status_code == 404
        assert "TX" in resp.json()["error"]


@pytest.mark.django_db
class TestAmbiguous:
    def test_ambiguous_match_returns_409(self, api_client, lookup_url, db):
        from socialwarehouse.geo.models import Address
        # Two rows that match the same address string.
        Address.objects.create(
            primary_number="100", street_name="Common",
            city_name="Austin", state_abbreviation="TX",
        )
        Address.objects.create(
            primary_number="100", street_name="Common",
            city_name="Austin", state_abbreviation="TX",
        )
        resp = api_client.get(
            lookup_url, {"address": "100 Common, Austin, TX 78701"}
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "ambiguous_address"
        assert body["candidate_count"] == 2


@pytest.mark.django_db
class TestHappyPath:
    def test_returns_full_district_block(
        self, api_client, lookup_url, address_full, dim_geography_tx
    ):
        resp = api_client.get(
            lookup_url, {"address": "123 Main St, Austin, TX 78701"}
        )
        assert resp.status_code == 200
        body = resp.json()

        # Address summary
        assert body["address"]["primary_number"] == "123"
        assert body["address"]["state_abbreviation"] == "TX"

        # Districts: every cache field populated => every key present
        d = body["districts"]
        assert set(d.keys()) == {
            "state", "county", "tract", "block_group", "block",
            "vtd", "congressional", "state_senate", "state_house", "zcta",
        }
        # Names: DimGeography seeded for state/county/cd only
        assert d["state"]["name"] == "Texas"
        assert d["county"]["name"] == "Travis County"
        assert d["congressional"]["name"] == "TX-10"
        # Names null when no DimGeography row
        assert d["vtd"]["name"] is None

    def test_null_cache_fields_omitted(
        self, api_client, lookup_url, address_no_cd
    ):
        resp = api_client.get(
            lookup_url, {"address": "456 Oak, Houston, TX 77002"}
        )
        assert resp.status_code == 200
        d = resp.json()["districts"]
        assert "state" in d
        assert "county" in d
        # cd / sldl / sldu / tract / vtd / etc. are null on the model -> OMITTED
        assert "congressional" not in d
        assert "state_house" not in d
        assert "state_senate" not in d
        assert "tract" not in d
        assert "vtd" not in d

    def test_redistricting_cycle_emitted_when_resolvable(
        self, api_client, lookup_url, address_full, redistricting_cycle_2020
    ):
        resp = api_client.get(
            lookup_url, {"address": "123 Main St, Austin, TX 78701"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "redistricting_cycle" in body
        assert body["redistricting_cycle"]["cycle_year"] == 2020
        assert body["redistricting_cycle"]["first_election_year"] == 2022

    def test_redistricting_cycle_absent_when_no_match(
        self, api_client, lookup_url, address_full
    ):
        # No DimRedistrictingCycle seeded => block omitted
        resp = api_client.get(
            lookup_url, {"address": "123 Main St, Austin, TX 78701"}
        )
        assert resp.status_code == 200
        assert "redistricting_cycle" not in resp.json()


@pytest.mark.django_db
class TestIncludeFlags:
    def test_include_people_default_false_omits_block(
        self, api_client, lookup_url, address_full
    ):
        resp = api_client.get(
            lookup_url, {"address": "123 Main St, Austin, TX 78701"}
        )
        assert resp.status_code == 200
        assert "people" not in resp.json()

    def test_include_people_true_returns_summary(
        self, api_client, lookup_url, address_full
    ):
        from socialwarehouse.warehouse.models import DimPerson
        DimPerson.objects.create(
            vendor="ts", vendor_voter_id="TS001",
            registration_state="TX", registration_status="active",
            address=address_full,
        )
        resp = api_client.get(
            lookup_url,
            {"address": "123 Main St, Austin, TX 78701", "include_people": "true"},
        )
        assert resp.status_code == 200
        people = resp.json()["people"]
        assert people["count"] == 1
        assert people["items"][0]["vendor"] == "ts"
        assert people["items"][0]["vendor_voter_id"] == "TS001"

    def test_include_geometry_true_returns_geojson_point(
        self, api_client, lookup_url, address_full
    ):
        resp = api_client.get(
            lookup_url,
            {"address": "123 Main St, Austin, TX 78701", "include_geometry": "true"},
        )
        assert resp.status_code == 200
        geom = resp.json()["address"]["geom"]
        assert geom["type"] == "Point"
        # DRF-GIS emits [lon, lat] per GeoJSON convention
        assert geom["coordinates"][0] == pytest.approx(-97.7431)
        assert geom["coordinates"][1] == pytest.approx(30.2672)

    def test_include_geometry_default_false_omits_geom(
        self, api_client, lookup_url, address_full
    ):
        resp = api_client.get(
            lookup_url, {"address": "123 Main St, Austin, TX 78701"}
        )
        assert resp.status_code == 200
        assert "geom" not in resp.json()["address"]


@pytest.mark.django_db
class TestStateFilter:
    def test_state_filter_excludes_wrong_state(
        self, api_client, lookup_url, db
    ):
        from socialwarehouse.geo.models import Address
        Address.objects.create(
            primary_number="200", street_name="Universal",
            city_name="Austin", state_abbreviation="TX",
            census_year=2020, state_geoid="48",
        )
        Address.objects.create(
            primary_number="200", street_name="Universal",
            city_name="Austin", state_abbreviation="MN",
            census_year=2020, state_geoid="27",
        )
        resp = api_client.get(
            lookup_url,
            {"address": "200 Universal, Austin, TX 78701", "state": "tx"},
        )
        assert resp.status_code == 200
        assert resp.json()["address"]["state_abbreviation"] == "TX"
