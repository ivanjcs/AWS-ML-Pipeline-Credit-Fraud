import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F

# 1. Inicialización
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME', 'DATABASE_NAME', 'TABLE_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

BUCKET = args['BUCKET_NAME']
GLUE_DB = args['DATABASE_NAME']
GLUE_TABLE = args['TABLE_NAME']
PROCESSED_PATH = f"s3://{BUCKET}/processed/"

# 2. Extracción: Leer desde el Data Catalog
dynamic_frame = glueContext.create_dynamic_frame.from_catalog(
    database=GLUE_DB,
    table_name=GLUE_TABLE,
    transformation_ctx="read_raw" # Mantenemos esto para los Bookmarks
)
# Auditar tipos reales
dynamic_frame.printSchema()

# Convertir a DataFrame de Spark tradicional
df_processed = dynamic_frame.toDF()

# 3. Transformaciones universales
df_processed = df_processed \
    .withColumn("amount", F.col("amount").cast("double")) \
    .withColumn("class", F.col("class").cast("integer")) \
    .withColumn("hour", (F.col("time") / 3600).cast("integer") % 24) \
    .dropna()

# 4. Carga: Escribir a S3
# OJO: Cuando uses Bookmarks, esto deberá cambiar a "append". Por ahora lo dejamos en overwrite.
df_processed.write \
    .mode("overwrite") \
    .option("compression", "snappy") \
    .parquet(PROCESSED_PATH)

job.commit()