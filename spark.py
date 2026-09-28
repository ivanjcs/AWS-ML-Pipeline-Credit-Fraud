import os
os.environ["SPARK_HOME"] = os.path.dirname(__import__("pyspark").__file__)
os.environ["JAVA_HOME"] = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"

from pyspark.sql import SparkSession
spark = SparkSession.builder.appName("test").master("local[1]").getOrCreate()
print("OK")
spark.stop()
os._exit(0)  # fuerza salida limpia, evita los errores de PID   