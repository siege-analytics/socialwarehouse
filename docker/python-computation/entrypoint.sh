#!/bin/bash
# Install the swh package in editable mode from the mounted volume.
# With args: exec the requested command (one-shot use, e.g. CI).
# Without args: keep the container running for interactive use.

if [ -f /opt/social_warehouse/pyproject.toml ]; then
    pip install -e /opt/social_warehouse/ --quiet 2>/dev/null
fi

trap : TERM INT
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    tail -f /dev/null & wait
fi
