export SPARK_HOME=~/Tools/spark-3.4.2-bin-hadoop3-scala2.13

sdk use maven 3.9.3

mvn -U -DremoteRepositories=https://artifacts.unidata.ucar.edu/content/repositories/unidata-releases/ org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=edu.ucar:cdm-core:5.5.3
