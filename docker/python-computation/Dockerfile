# Args from compose
ARG UBUNTU_BASE_IMAGE
ARG PYTHON_VENV_PATH

FROM ${UBUNTU_BASE_IMAGE}
ENV DEBIAN_FRONTEND noninteractive

# Install the basics
RUN apt-get clean && apt-get update \
    && apt-get install -y python3-pip \
    python3-venv \
    gdal-bin \
    python3-pyproj \
    build-essential \
    wget \
    ca-certificates \
    postgresql  \
    postgresql-contrib \
    postgis \
    vim

# Python tasks

RUN python3 -m venv ${PYTHON_VENV_PATH}
ENV PATH="${PYTHON_VENV_PATH}/bin:$PATH"

ADD requirements.txt /tmp/
ADD entrypoint.sh /usr/local/bin/

# trying out GDAL fix
# https://gis.stackexchange.com/questions/28966/python-gdal-package-missing-header-file-when-installing-via-pip

RUN apt-get install -y --install-recommends libgdal-dev
RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
RUN export C_INCLUDE_PATH=/usr/include/gdal

# RUN pip3 install gdal

# Install PIP requirements

RUN pip3 install -r /tmp/requirements.txt

WORKDIR /opt/social_warehouse

ENTRYPOINT entrypoint.sh

CMD python3 --version
