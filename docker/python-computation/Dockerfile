# Social Warehouse — Python Computation Image
#
# Installs GDAL, siege_utilities, and the swh package.
# The entire repo is mounted at /opt/social_warehouse/ for development.

ARG UBUNTU_BASE_IMAGE=ubuntu:24.04
FROM ${UBUNTU_BASE_IMAGE}

ARG PYTHON_VENV_PATH=/opt/venv
ARG DEBIAN_FRONTEND=noninteractive

# ---- OS packages ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata build-essential wget ca-certificates \
        python3-pip python3-venv python3-dev python3-pyproj \
        gdal-bin libgdal-dev \
        postgresql-client \
        vim \
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

# ---- Non-root user ----
RUN groupadd -r swh && useradd -r -g swh -d /opt/social_warehouse -s /bin/bash swh
RUN mkdir -p /opt/social_warehouse && chown -R swh:swh /opt/social_warehouse ${PYTHON_VENV_PATH}

WORKDIR /opt/social_warehouse

COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

USER swh

ENTRYPOINT ["entrypoint.sh"]
CMD ["python3", "--version"]
