#bin/spark-shell --master local[*] \
${SPARK_HOME}/bin/spark-shell --master spark://localhost:7077 \
  --deploy-mode client \
  --packages org.apache.sedona:sedona-spark-shaded-3.4_2.13:1.5.1,org.datasyslab:geotools-wrapper:1.5.1-28.2,edu.ucar:cdm-core:5.5.3 \
  --properties-file ./spark-client-defaults.properties
#  --driver-memory 2g \
#  --executor-memory 2g \
#  --num-executors 2 \
#  --executor-cores 4 \
#  --total-executor-cores 8 \
