import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.ml import Pipeline
from pyspark.ml.feature import VectorAssembler, RobustScaler
from pyspark.ml.functions import vector_to_array


# 1. Inicialización de contextos nativos de AWS
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME', 'DATABASE_NAME', 'TABLE_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)


BUCKET = args['BUCKET_NAME']
GLUE_DB = args['DATABASE_NAME']
GLUE_TABLE = args['TABLE_NAME']
RAW_PATH = f"s3://{BUCKET}/raw/creditcard.csv"
PROCESSED_PATH = f"s3://{BUCKET}/processed/"

# ==========================================
# FASE 1: CAPA PROCESSED (Fuente de la Verdad)
# ==========================================

# 2. Leer desde el Data Catalog usando los parámetros parametrizados
dynamic_frame = glueContext.create_dynamic_frame.from_catalog(
    database=GLUE_DB,
    table_name=GLUE_TABLE,
    transformation_ctx="read_raw" # Crucial para Job Bookmarks
)

# 3. Convertir a DataFrame de Spark tradicional
df_processed = dynamic_frame.toDF()

# 4. Transformaciones (Adaptado a las minúsculas del Data Catalog)
# Nota: Los Crawlers de AWS Glue suelen convertir todos los nombres de columnas a minúsculas
df_processed = df_processed \
    .withColumn("amount", F.col("amount").cast("double")) \
    .withColumn("class", F.col("class").cast("integer")) \
    .withColumn("hour", (F.col("time") / 3600).cast("integer") % 24) \
    .dropna()

job.commit()

# 5. Transformaciones universales (La lógica que sacamos del EDA)
# Creación de la columna Hour
df_processed = df_processed.withColumn("hour", (F.col("time") / 3600).cast("integer") % 24)

# Filtro preventivo de nulos (Aunque en el EDA dijimos que no había, en prod se blinda)
df_processed = df_processed.dropna()

# 6. Carga: Escribir a S3 en formato columnar (Parquet) con compresión
# Usamos mode("overwrite") en desarrollo. En producción avanzada podría ser "append"
df_processed.write \
    .mode("overwrite") \
    .option("compression", "snappy") \
    .parquet(PROCESSED_PATH)

# ==========================================
# FASE 2: CAPA CURATED
# ==========================================
# Aquí irán el VectorAssembler, RobustScaler y Cost-Sensitive Learning.

# -- Stratified Split --

print("Iniciando Fase 2: Stratified Split Seguro...")

# 1. Creamos una columna aleatoria FIJA usando un seed para evitar que cambie durante la ejecución
df_with_rand = df_processed.withColumn("rand_id", F.rand(seed=42))

# 2. Definimos la ventana ordenando por esa columna fija
window_stratified = Window.partitionBy("class").orderBy("rand_id")

# 3. Calculamos el rango percentil
df_with_rank = df_with_rand.withColumn("pct_rank", F.percent_rank().over(window_stratified)).cache()

# 4. Filtramos los datasets de forma segura y eliminamos las columnas temporales
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

# -- Escalamiento --

# 1. Transformaciones Matemáticas Sin Estado
# log1p no aprende de los datos, por lo que se aplica directamente a ambos sets
train_df = train_df.withColumn("amount_log", F.log1p(F.col("amount")))
val_df = val_df.withColumn("amount_log", F.log1p(F.col("amount")))
test_df  = test_df.withColumn("amount_log", F.log1p(F.col("amount")))

# 2. Definición del ML Pipeline (Para evitar Data Leakage)
assembler_amount = VectorAssembler(inputCols=["amount_log"], outputCol="amount_vec")
scaler_amount = RobustScaler(inputCol="amount_vec", outputCol="amount_scaled_vec")

ml_pipeline = Pipeline(stages=[assembler_amount, scaler_amount])

# 3. Ajuste Exclusivo y Transformación
# !: El modelo aprende los parámetros (mediana e IQR) ÚNICAMENTE del set de entrenamiento
pipeline_model = ml_pipeline.fit(train_df)

train_df = pipeline_model.transform(train_df)
val_df = pipeline_model.transform(val_df)
test_df  = pipeline_model.transform(test_df)

# 4. Desempaquetar el vector y limpieza de variables redundantes (ruido)
# SageMaker necesita números planos (Double), no estructuras de vectores de Spark
columnas_a_borrar = ["amount", "amount_log", "amount_vec", "amount_scaled_vec", "time"]

train_df = train_df.withColumn("amount_scaled", vector_to_array(F.col("amount_scaled_vec"))[0]).drop(*columnas_a_borrar)
val_df = val_df.withColumn("amount_scaled", vector_to_array(F.col("amount_scaled_vec"))[0]).drop(*columnas_a_borrar)
test_df  = test_df.withColumn("amount_scaled", vector_to_array(F.col("amount_scaled_vec"))[0]).drop(*columnas_a_borrar)

# -- PREPARACIÓN PARA SAGEMAKER Y CARGA EN S3 --

# El algoritmo built-in de XGBoost en SageMaker requiere que la variable objetivo ("Class")
# sea estrictamente la primera columna del dataset.
feature_cols = [f"v{i}" for i in range(1, 29)] + ["amount_scaled", "hour"]
final_columns = ["class"] + feature_cols

train_df = train_df.select(final_columns)
val_df = val_df.select(final_columns)
test_df = test_df.select(final_columns)

# Rutas de destino (La variable BUCKET viene de args['BUCKET_NAME'] inicial)
TRAIN_PATH = f"s3://{BUCKET}/curated/train/"
VAL_PATH = f"s3://{BUCKET}/curated/validation/"
TEST_PATH  = f"s3://{BUCKET}/curated/test/"

print("Escribiendo datasets Curated en S3...")
train_df.write.mode("overwrite").option("compression", "snappy").parquet(TRAIN_PATH)
val_df.write.mode("overwrite").option("compression", "snappy").parquet(VAL_PATH)
test_df.write.mode("overwrite").option("compression", "snappy").parquet(TEST_PATH)

# --- Finalizar el Job y registrar Bookmarks ---
job.commit()