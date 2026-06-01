"""Canonical Dagster Definitions for socialwarehouse.

Discovered by ``dagster dev -m socialwarehouse.orchestration``. The
``Definitions`` object below assembles:

- **resources**: ``warehouse`` (WarehouseConfig), ``spark`` (SparkResource), ``postgis`` (PostGISResource)
- **assets**: discovered from ``socialwarehouse.orchestration.assets.*``
- **schedules**: from ``socialwarehouse.orchestration.schedules``
- **sensors**: from ``socialwarehouse.orchestration.sensors``
- **jobs**: from ``socialwarehouse.orchestration.schedules``

Instance projects rebuild this object with their own resources +
asset set; see ``docs/orchestration/instance-project-guide.md``.
"""

from __future__ import annotations

from dagster import Definitions

from socialwarehouse.orchestration.assets import economic, geo
from socialwarehouse.orchestration.resources import (
    PostGISResource,
    SparkResource,
    WarehouseConfig,
)
from socialwarehouse.orchestration.schedules import all_jobs, all_schedules
from socialwarehouse.orchestration.sensors import all_sensors


defs = Definitions(
    assets=[*geo.all_assets, *economic.all_assets],
    jobs=all_jobs,
    schedules=all_schedules,
    sensors=all_sensors,
    resources={
        "warehouse": WarehouseConfig(),
        "spark": SparkResource(),
        "postgis": PostGISResource(),
    },
)
