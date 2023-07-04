FROM ubuntu:latest

ENV DEBIAN_FRONTEND noninteractive

# Install the basics
RUN apt-get clean && apt-get update \
    && apt-get install -y python3-pip gdal-bin python3-pyproj \
    build-essential wget ca-certificates postgresql postgresql-contrib \
    postgis

ADD requirements.txt /tmp/
ADD entrypoint.sh /usr/local/bin/

# Install PIP requirements
RUN pip3 install -r /tmp/requirements.txt

COPY code/ /opt/social_warehouse/code/

WORKDIR /opt/social_warehouse

ENTRYPOINT entrypoint.sh

CMD python3 --version
