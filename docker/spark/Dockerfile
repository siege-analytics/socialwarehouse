# Social Warehouse — Spark + Sedona Image
#
# Java/Scala via SDKMAN; Spark downloaded directly from Apache archive
# (SDKMAN has Spark but only up to 4.0.0-preview2; 4.0.2 stable not yet listed).
# GDAL is installed for geospatial Python work (geopandas, sedona, etc.).

ARG UBUNTU_BASE_IMAGE=ubuntu:24.04
FROM ${UBUNTU_BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG PYTHON_VENV_PATH=/opt/venv

ARG SPARK_VERSION=4.0.2
ARG SPARK_HADOOP_PROFILE=hadoop3
ARG JAVA_VERSION=21.0.7-tem
ARG SCALA_VERSION=2.13.14

# ---- OS packages ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata sudo curl vim unzip zip rsync wget \
        build-essential software-properties-common ssh \
        python3-pip python3-venv python3-pyproj \
        gdal-bin libgdal-dev \
        postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- SDKMAN: Java and Scala (SDKMAN has Spark but only up to 4.0.0-preview2; 4.0.2 not yet listed) ----
ENV SPARK_HOME=/opt/spark
ENV HADOOP_HOME=/opt/hadoop

RUN mkdir -p ${SPARK_HOME} ${HADOOP_HOME}

SHELL ["/bin/bash", "-c"]

RUN curl -s "https://get.sdkman.io" | bash \
    && source "$HOME/.sdkman/bin/sdkman-init.sh" \
    && sdk install java ${JAVA_VERSION} \
    && sdk install scala ${SCALA_VERSION}

# ---- Spark: download directly from Apache archive ----
RUN wget -qO /tmp/spark.tgz \
        "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-${SPARK_HADOOP_PROFILE}.tgz" \
    && tar -xzf /tmp/spark.tgz -C /tmp/ \
    && cp -a /tmp/spark-${SPARK_VERSION}-bin-${SPARK_HADOOP_PROFILE}/. ${SPARK_HOME}/ \
    && rm -rf /tmp/spark*

ENV JAVA_HOME=/root/.sdkman/candidates/java/current
ENV SCALA_HOME=/root/.sdkman/candidates/scala/current
ENV PATH="${SPARK_HOME}/sbin:${SPARK_HOME}/bin:${JAVA_HOME}/bin:${PATH}"
ENV SPARK_MASTER="spark://spark-master:7077"
ENV SPARK_MASTER_HOST=spark-master
ENV SPARK_MASTER_PORT=7077
ENV PYSPARK_PYTHON=python3
ENV PYTHONPATH="${SPARK_HOME}/python:${PYTHONPATH}"

# ---- Python venv + geospatial deps ----
RUN python3 -m venv ${PYTHON_VENV_PATH}
ENV PATH="${PYTHON_VENV_PATH}/bin:${PATH}"

RUN pip install --upgrade pip \
    && pip install GDAL=="$(gdal-config --version).*"

COPY spark_requirements.txt .
RUN pip install -r spark_requirements.txt

# ---- Spark config ----
COPY spark-master-defaults.properties ${SPARK_HOME}/conf/spark-defaults.conf

WORKDIR ${SPARK_HOME}

COPY spark_entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/spark_entrypoint.sh

ENTRYPOINT ["spark_entrypoint.sh"]
