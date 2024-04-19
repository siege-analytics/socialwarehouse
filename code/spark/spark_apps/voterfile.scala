val tsv = spark.read.option("delimiter", "\t").option("header", "true").csv("./data/TX25VoterFile.txt")
