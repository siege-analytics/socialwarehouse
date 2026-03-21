#!/bin/bash
# Install the swh package in editable mode from the mounted volume,
# then keep the container running for interactive use.

if [ -f /opt/social_warehouse/pyproject.toml ]; then
    pip install -e /opt/social_warehouse/ --quiet 2>/dev/null
fi

trap : TERM INT
tail -f /dev/null & wait
