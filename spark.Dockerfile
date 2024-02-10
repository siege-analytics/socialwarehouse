# FROM ubuntu:latest as spark-base
FROM python:3.10-bullseye as spark-base

ARG SPARK_VERSION=3.4.2
ARG GDAL_VERSION=3.4.1

# Install tools for OS

RUN apt-get update && \
    apt-get install -y --install-recommends \
        sudo \
        curl \
        vim \
        unzip \
        rsync \
        build-essential \
        software-properties-common \
        ssh \
        python3-pip \
        gdal-bin \
        libgdal-dev  \
        python3-pyproj \
        postgresql \
        postgresql-contrib \
        postgis && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up directories for Spark and Hadoop \
ENV SPARK_HOME=${SPARK_HOME:-"/opt/spark"}
ENV HADOOP_HOME=${HADOOP_HOME:-"/opt/hadoop"}

RUN mkdir -p ${HADOOP_HOME} && mkdir -p ${SPARK_HOME}
WORKDIR ${SPARK_HOME}

from spark-base as pyspark

# Download and install Spark
# Spark URL has changed : https://dlcdn.apache.org/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz

RUN curl https://dlcdn.apache.org/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz -o spark-${SPARK_VERSION}-bin-hadoop3.tgz \
 && tar xvzf spark-${SPARK_VERSION}-bin-hadoop3.tgz --directory /opt/spark --strip-components 1 \
 && rm -rf spark-${SPARK_VERSION}-bin-hadoop3.tgz


# trying out GDAL fix
# https://gis.stackexchange.com/questions/28966/python-gdal-package-missing-header-file-when-installing-via-pip

RUN apt-get install -y --install-recommends libgdal-dev
RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
RUN export C_INCLUDE_PATH=/usr/include/gdal
# RUN pip install gdal==3.4.1

# Python
COPY spark_requirements.txt .
RUN pip3 install --upgrade pip
RUN pip3 install -r spark_requirements.txt

# Set up Spark related environment variables

ENV PATH="/opt/spark/sbin:/opt/spark/bin:${PATH}"
ENV SPARK_MASTER="spark://spark-master:7077"
ENV SPARK_MASTER_HOST spark-master
ENV SPARK_MASTER_PORT 7077
ENV PYSPARK_PYTHON python3

# Copy the default configurations into $SPARK_HOME/conf
COPY ./code/config_files/spark-defaults.conf "$SPARK_HOME/conf/"

RUN chmod u+x /opt/spark/sbin/* && \
    chmod u+x /opt/spark/bin/*

ENV PYTHONPATH=$SPARK_HOME/python:$PYTHONPATH

# Copy appropriate entrpoint
COPY spark_entrypoint.sh /usr/local/bin/

ENTRYPOINT spark_entrypoint.sh