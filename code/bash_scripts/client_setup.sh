#!/bin/bash

sdk use maven 3.9.3
sdk use java 11.0.21-zulu
sdk use scala 2.13.12

export SPARK_HOME=/Users/Shared/Tools/spark-3.4.2-bin-hadoop3-scala2.13
export PATH=${SCALA_HOME}/bin:${MAVEN_HOME}/bin:${JAVA_HOME}/bin:${SPARK_HOME}/bin:${PATH}
