FROM ubuntu:latest as spark-base
ENV DEBIAN_FRONTEND noninteractive

ARG SPARK_VERSION='3.4.2'
ARG JAVA_VERSION='11.0.22-ms'
ARG SCALA_VERSION='2.13.2'
ARG GDAL_VERSION='3.4.1'

# Install tools for OS

RUN apt-get update
RUN apt-get install -y tzdata
RUN apt-get install -y --install-recommends \
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
        unzip \
        zip \
        wget \
        postgis && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up directories for Spark and Hadoop \
ENV SPARK_HOME=${SPARK_HOME:-"/opt/spark"}
ENV HADOOP_HOME=${HADOOP_HOME:-"/opt/hadoop"}

RUN mkdir -p ${HADOOP_HOME} && mkdir -p ${SPARK_HOME}
WORKDIR ${SPARK_HOME}

# Trying to add sdkman
# https://stackoverflow.com/questions/53656537/install-sdkman-in-docker-image

RUN rm /bin/sh && ln -s /bin/bash /bin/sh
RUN apt-get -qq -y install curl wget unzip zip

RUN curl -s "https://get.sdkman.io" | bash
RUN source "$HOME/.sdkman/bin/sdkman-init.sh"

from spark-base as pyspark

# Download and install Spark
# Spark URL has changed : https://dlcdn.apache.org/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3-scala${SCALA_VERSION}.tgz

ENV SPARK_DOWNLOAD_URL https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3-scala${SCALA_VERSION}.tgz
ENV SPARK_FILE_NAME spark-${SPARK_VERSION}-bin-hadoop3-scala${SCALA_VERSION}.tgz
ENV SPARK_FILE_PATH ${SPARK_HOME}/${SPARK_FILE_NAME}

#RUN curl -L ${SPARK_DOWNLOAD_URL} -o ${SPARK_FILE_PATH}
RUN wget -O ${SPARK_FILE_PATH} https://archive.apache.org/dist/spark/spark-3.4.2/spark-3.4.2-bin-hadoop3-scala2.13.tgz
RUN tar -xvzf ${SPARK_FILE_PATH} --directory /opt/spark
RUN rm -rf ${SPARK_FILE_PATH}

# trying out GDAL fix

RUN apt-get install -y --install-recommends libgdal-dev
RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
RUN export C_INCLUDE_PATH=/usr/include/gdal
RUN pip3 install --upgrade pip
RUN pip3 install gdal==3.4.1
##
## Python
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

#RUN chmod u+x /opt/spark/sbin/* && \
#    chmod u+x /opt/spark/bin/*

ENV PYTHONPATH=$SPARK_HOME/python:$PYTHONPATH

# install sdkman for java and scala

RUN curl -s "https://get.sdkman.io" | bash

RUN /bin/bash -c "source $HOME/.sdkman/bin/sdkman-init.sh; sdk version; sdk install java ${JAVA_VERSION}; sdk install scala ${SCALA_VERSION}"

# Copy appropriate entrpoint
COPY spark_entrypoint.sh /usr/local/bin/

ENTRYPOINT spark_entrypoint.sh
