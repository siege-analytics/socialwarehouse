# Social Warehouse -- SedonaDB JupyterLab Image
#
# Apache SedonaDB is a single-node analytical database engine with
# geospatial as a first-class citizen. It's distributed as a Python
# library (apache-sedona[db]); there's no official server image. This
# Dockerfile wraps SedonaDB in a JupyterLab notebook environment so it
# can be explored interactively in a browser.
#
# Local-dev only: no Jupyter token, no TLS. Production hardening is a
# followup if SedonaDB graduates from "immature" to "keep" (#64).

ARG UBUNTU_BASE_IMAGE=ubuntu:24.04
FROM ${UBUNTU_BASE_IMAGE}

ARG PYTHON_VENV_PATH=/opt/venv
ARG DEBIAN_FRONTEND=noninteractive

# ---- OS packages ----
# GDAL is for geopandas + shapely interop (SedonaDB consumes/produces
# GeoParquet, geopandas DataFrames). build-essential supports any wheel
# fallbacks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata build-essential ca-certificates curl \
        python3-pip python3-venv \
        gdal-bin libgdal-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- Python venv ----
RUN python3 -m venv ${PYTHON_VENV_PATH}
ENV PATH="${PYTHON_VENV_PATH}/bin:${PATH}"

# ---- GDAL (must match system version) ----
RUN pip install --upgrade pip \
    && pip install GDAL=="$(gdal-config --version).*"

# ---- Python dependencies ----
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# ---- Working directory + persistent volume target ----
RUN mkdir -p /home/sedonadb/work
WORKDIR /home/sedonadb/work

# ---- Default port: JupyterLab ----
EXPOSE 8889

# ---- Entrypoint ----
COPY entrypoint.sh /usr/local/bin/sedonadb-entrypoint.sh
RUN chmod +x /usr/local/bin/sedonadb-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/sedonadb-entrypoint.sh"]
