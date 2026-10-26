import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.ml import Pipeline
from pyspark.ml.feature import VectorAssembler, RobustScaler
from pyspark.ml.functions import vector_to_array

# 1. Inicialización (Este Job NO necesita la Base de Datos ni la Tabla Cruda)
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

BUCKET = args['BUCKET_NAME']
PROCESSED_PATH = f"s3://{BUCKET}/processed/"

TRAIN_PATH = f"s3://{BUCKET}/curated/train/"
VAL_PATH = f"s3://{BUCKET}/curated/validation/"
TEST_PATH  = f"s3://{BUCKET}/curated/test/"

# 2. Extracción: Leer el dataset procesado completo desde S3
# Como los datos ya están limpios y en Parquet, leer desde S3 directamente es óptimo.
df_processed = spark.read.parquet(PROCESSED_PATH)

print("Iniciando Fase 2: Stratified Split Seguro...")

# 3. Stratified Split
df_with_rand = df_processed.withColumn("rand_id", F.rand(seed=42))
window_stratified = Window.partitionBy("class").orderBy("rand_id")
df_with_rank = df_with_rand.withColumn("pct_rank", F.percent_rank().over(window_stratified)).cache()

train_df = df_with_rank.filter(F.col("pct_rank") <= 0.70).drop("pct_rank", "rand_id")
val_df   = df_with_rank.filter((F.col("pct_rank") > 0.70) & (F.col("pct_rank") <= 0.85)).drop("pct_rank", "rand_id")
test_df  = df_with_rank.filter(F.col("pct_rank") > 0.85).drop("pct_rank", "rand_id")

# Validamos (En producción estos prints van a los logs de CloudWatch)
train_count = train_df.count()
val_count = val_df.count()
test_count = test_df.count()
print(f"Train set: {train_count} registros")
print(f"Val set: {val_count} registros")
print(f"Test set: {test_count} registros")

# 4. Escalamiento (Solo entrenando con train_df)
train_df = train_df.withColumn("amount_log", F.log1p(F.col("amount")))
val_df = val_df.withColumn("amount_log", F.log1p(F.col("amount")))
test_df  = test_df.withColumn("amount_log", F.log1p(F.col("amount")))

assembler_amount = VectorAssembler(inputCols=["amount_log"], outputCol="amount_vec")
scaler_amount = RobustScaler(inputCol="amount_vec", outputCol="amount_scaled_vec")

ml_pipeline = Pipeline(stages=[assembler_amount, scaler_amount])
pipeline_model = ml_pipeline.fit(train_df)

train_df = pipeline_model.transform(train_df)
val_df = pipeline_model.transform(val_df)
test_df  = pipeline_model.transform(test_df)

# 5. Limpieza y Ensamblado Final
columnas_a_borrar = ["amount", "amount_log", "amount_vec", "amount_scaled_vec", "time"]

train_df = train_df.withColumn("amount_scaled", vector_to_array(F.col("amount_scaled_vec"))[0]).drop(*columnas_a_borrar)
val_df = val_df.withColumn("amount_scaled", vector_to_array(F.col("amount_scaled_vec"))[0]).drop(*columnas_a_borrar)
test_df  = test_df.withColumn("amount_scaled", vector_to_array(F.col("amount_scaled_vec"))[0]).drop(*columnas_a_borrar)

feature_cols = [f"v{i}" for i in range(1, 29)] + ["amount_scaled", "hour"]
final_columns = ["class"] + feature_cols

train_df = train_df.select(final_columns)
val_df = val_df.select(final_columns)
test_df = test_df.select(final_columns)

# 6. Carga en S3
print("Escribiendo datasets Curated en S3...")
train_df.write.mode("overwrite").option("compression", "snappy").parquet(TRAIN_PATH)
val_df.write.mode("overwrite").option("compression", "snappy").parquet(VAL_PATH)
test_df.write.mode("overwrite").option("compression", "snappy").parquet(TEST_PATH)

job.commit()