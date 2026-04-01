"""
Celery tasks for geographic warehouse operations.

These wrap management commands for async execution, enabling
bulk geocoding and boundary assignment to run in the background
or be distributed across Celery workers.
"""

import logging

from celery import shared_task

logger = logging.getLogger("socialwarehouse.geo")


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def geocode_addresses_task(self, state=None, source="dual", batch_size=5000, limit=0):
    """Async geocoding via Census + Nominatim."""
    from django.core.management import call_command

    logger.info("Starting geocode_addresses task (state=%s, source=%s)", state, source)

    kwargs = {"source": source, "batch_size": batch_size}
    if state:
        kwargs["state"] = state
    if limit:
        kwargs["limit"] = limit

    try:
        call_command("geocode_addresses", **kwargs)
    except Exception as exc:
        logger.error("geocode_addresses failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def assign_boundaries_task(self, year=2020, state=None, batch_size=500, limit=0, populate_fks=False):
    """Async boundary assignment via PostGIS spatial joins."""
    from django.core.management import call_command

    logger.info("Starting assign_boundaries task (year=%s, state=%s)", year, state)

    kwargs = {"year": year, "batch_size": batch_size}
    if state:
        kwargs["state"] = state
    if limit:
        kwargs["limit"] = limit
    if populate_fks:
        kwargs["populate_fks"] = True

    try:
        call_command("assign_boundaries", **kwargs)
    except Exception as exc:
        logger.error("assign_boundaries failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1)
def compute_intersections_task(self, year, intersection_type="all", state=None, min_overlap=1.0):
    """Async intersection computation (County-CD, VTD-CD)."""
    from django.core.management import call_command

    logger.info("Starting compute_intersections task (year=%s, type=%s)", year, intersection_type)

    kwargs = {"year": year, "type": intersection_type, "min_overlap": min_overlap}
    if state:
        kwargs["state"] = state

    try:
        call_command("compute_geographic_intersections", **kwargs)
    except Exception as exc:
        logger.error("compute_intersections failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task
def compute_intersections_for_state_task(state_fips, year, intersection_type="all", min_overlap=1.0):
    """Compute intersections for a single state — used for parallel fan-out."""
    from django.core.management import call_command

    logger.info("Computing intersections for state %s, year %s", state_fips, year)
    call_command(
        "compute_geographic_intersections",
        year=year,
        type=intersection_type,
        state=state_fips,
        min_overlap=min_overlap,
    )


@shared_task
def geocode_and_assign_pipeline(state=None, year=2020):
    """Full pipeline: geocode ungeocoded addresses, then assign boundaries.

    Chains geocode_addresses → assign_boundaries for a given state.
    """
    from celery import chain

    return chain(
        geocode_addresses_task.s(state=state),
        assign_boundaries_task.s(year=year, state=state, populate_fks=True),
    ).apply_async()
