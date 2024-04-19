FROM ubuntu:latest
ENV DEBIAN_FRONTEND noninteractive

ARG GDAL_VERSION=3.4.1


# Install the basics
RUN apt-get clean && apt-get update \
    && apt-get install -y python3-pip gdal-bin python3-pyproj \
    build-essential wget ca-certificates postgresql postgresql-contrib \
    postgis vim

# RUN pip install GDAL==3.2.2.1
ADD requirements.txt /tmp/
ADD entrypoint.sh /usr/local/bin/


# trying out GDAL fix
# https://gis.stackexchange.com/questions/28966/python-gdal-package-missing-header-file-when-installing-via-pip

RUN apt-get install -y --install-recommends libgdal-dev
RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
RUN export C_INCLUDE_PATH=/usr/include/gdal
RUN pip3 install gdal==3.4.1


# Install PIP requirements
RUN pip3 install -r /tmp/requirements.txt

# COPY code/ /opt/social_warehouse/code/

WORKDIR /opt/social_warehouse

ENTRYPOINT entrypoint.sh

CMD python3 --version
