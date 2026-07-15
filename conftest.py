import django
import pytest
from django.conf import settings


def pytest_configure():
    settings.DJANGO_SETTINGS_MODULE = "socialwarehouse.settings.test"
    django.setup()


@pytest.fixture(scope="session", autouse=True)
def _attestation_link_test_tables(django_db_setup, django_db_blocker):
    """Create the test-only concrete attestation-link tables session-wide.

    ``tests/unit/core/test_attestation_links.py`` declares its adopter stand-in
    models (CommitteeAttestationLink / FilingAttestationLink /
    AddressResolutionAttestation) at module level, so they are registered in the
    app registry — each with an FK to ``core.Attestation`` — for the entire test
    session. Any test that deletes an Attestation (e.g. the Event-canonicalization
    ``SET_NULL`` test) traverses these reverse relations via Django's
    delete-collector and queries their tables. The tables must therefore exist
    for the whole session regardless of test order (events tests run before core
    tests). Create them once here; the test-DB teardown drops them at session end.
    """
    from django.db import connection

    with django_db_blocker.unblock():
        from tests.unit.core.test_attestation_links import (
            AddressResolutionAttestation,
            CommitteeAttestationLink,
            FilingAttestationLink,
        )

        existing = set(connection.introspection.table_names())
        with connection.schema_editor() as editor:
            for model in (
                CommitteeAttestationLink,
                FilingAttestationLink,
                AddressResolutionAttestation,
            ):
                if model._meta.db_table not in existing:
                    editor.create_model(model)
    yield
