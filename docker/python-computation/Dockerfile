# Args from compose
ARG UBUNTU_BASE_IMAGE
FROM ${UBUNTU_BASE_IMAGE}

ARG PYTHON_VENV_PATH
ARG DEBIAN_FRONTEND noninteractive

# Install the basics
RUN apt-get update && apt-get install -y tzdata
RUN apt-get install -y \
    build-essential \
    wget \
    ca-certificates \
    python3-pip \
    python3-venv \
    python3-pyproj \
    gdal-bin \
    postgresql  \
    postgresql-contrib \
    postgis \
    vim \
    && apt-get clean

#
# Python tasks
#

RUN python3 -m venv ${PYTHON_VENV_PATH}
ENV PATH="${PYTHON_VENV_PATH}/bin:$PATH"

# Install GDAL
RUN apt-get install -y --install-recommends libgdal-dev
RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
RUN export C_INCLUDE_PATH=/usr/include/gdal
RUN pip3 install --upgrade pip
RUN pip install GDAL=="$(gdal-config --version).*"

# Install PIP requirements
ADD requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

WORKDIR /opt/social_warehouse

ADD entrypoint.sh /usr/local/bin/
ENTRYPOINT entrypoint.sh

CMD python3 --version
