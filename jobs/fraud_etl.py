import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import pyspark.sql.functions as F
from pyspark.ml import Pipeline
from pyspark.ml.feature import VectorAssembler, RobustScaler
from pyspark.ml.functions import vector_to_array
import pyspark.sql.functions as F

# 1. Inicialización de contextos nativos de AWS
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Construimos las rutas dinámicamente usando el argumento BUCKET_NAME
BUCKET = args['BUCKET_NAME']
RAW_PATH = f"s3://{BUCKET}/raw/creditcard.csv"
PROCESSED_PATH = f"s3://{BUCKET}/processed/"

# ==========================================
# FASE 1: CAPA PROCESSED (Fuente de la Verdad)
# ==========================================

# 2. Extracción: Leer de S3 usando DynamicFrame, infiere el esquema al vuelo
dynamic_frame_raw = glueContext.create_dynamic_frame.from_options(
    format_options={"quoteChar": '"', "withHeader": True, "separator": ","},
    connection_type="s3",
    format="csv",
    connection_options={"paths": [RAW_PATH]},
    transformation_ctx="raw_input"
)

# 3. Convertir a Spark DataFrame clásico para transformaciones complejas
df = dynamic_frame_raw.toDF()

# 4. Casteo de tipos esenciales (Aseguramos que las columnas clave sean Double o Integer)
df = df.withColumn("Time", F.col("Time").cast("double")) \
       .withColumn("Amount", F.col("Amount").cast("double")) \
       .withColumn("Class", F.col("Class").cast("integer"))

# 5. Transformaciones universales (La lógica que sacamos del EDA)
# Creación de la columna Hour
df_processed = df.withColumn("Hour", (F.col("Time") / 3600).cast("integer") % 24)

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

print("Iniciando Fase 2: Stratified Split...")

# 1. Definimos una partición por la variable objetivo ("Class") (seed=42 para reproducibilidad)
window_stratified = Window.partitionBy("Class").orderBy(F.rand(seed=42))

# 2. Calculamos el rango percentil (de 0.0 a 1.0) para cada fila dentro de su clase.
# Esto significa que el 80% de los fraudes tendrán un valor <= 0.8, 
# y el 80% de las legítimas también tendrán un valor <= 0.8.
df_with_rank = df_processed.withColumn("pct_rank", F.percent_rank().over(window_stratified))

# 3. Ejecutamos el Split usando el rango calculado
train_df = df_with_rank.filter(F.col("pct_rank") <= 0.8).drop("pct_rank")
test_df  = df_with_rank.filter(F.col("pct_rank") > 0.8).drop("pct_rank")

# Validamos (En producción estos prints van a los logs de CloudWatch)
train_count = train_df.count()
test_count = test_df.count()
print(f"Train set: {train_count} registros")
print(f"Test set: {test_count} registros")

# -- Escalamiento --

# 1. Transformaciones Matemáticas Sin Estado
# log1p no aprende de los datos, por lo que se aplica directamente a ambos sets
train_df = train_df.withColumn("Amount_log", F.log1p(F.col("Amount")))
test_df  = test_df.withColumn("Amount_log", F.log1p(F.col("Amount")))

# 2. Definición del ML Pipeline (Para evitar Data Leakage)
assembler_amount = VectorAssembler(inputCols=["Amount_log"], outputCol="Amount_vec")
scaler_amount = RobustScaler(inputCol="Amount_vec", outputCol="Amount_scaled_vec")

ml_pipeline = Pipeline(stages=[assembler_amount, scaler_amount])

# 3. Ajuste Exclusivo y Transformación
# !: El modelo aprende los parámetros (mediana e IQR) ÚNICAMENTE del set de entrenamiento
pipeline_model = ml_pipeline.fit(train_df)

train_df = pipeline_model.transform(train_df)
test_df  = pipeline_model.transform(test_df)

# 4. Desempaquetar el vector y limpieza de variables redundantes (ruido)
# SageMaker necesita números planos (Double), no estructuras de vectores de Spark
columnas_a_borrar = ["Amount", "Amount_log", "Amount_vec", "Amount_scaled_vec", "Time"]

train_df = train_df.withColumn("Amount_scaled", vector_to_array(F.col("Amount_scaled_vec"))[0]).drop(*columnas_a_borrar)
test_df  = test_df.withColumn("Amount_scaled", vector_to_array(F.col("Amount_scaled_vec"))[0]).drop(*columnas_a_borrar)

# -- Cost-Sensitive Learning (Manejo del Desbalance)

print("Calculando pesos dinámicos para Cost-Sensitive Learning...")

# Calculamos la distribución real en el set de entrenamiento
total_train = train_df.count()
fraudes_train = train_df.filter(F.col("Class") == 1).count()
legitimas_train = total_train - fraudes_train

# La heurística más robusta para balancear XGBoost es Inversamente Proporcional a la Frecuencia
# Ratio esperado: ~227,451 / 394 = 577.28
fraude_weight = legitimas_train / fraudes_train

print(f"Peso asignado a transacciones legítimas: 1.0")
print(f"Peso asignado a transacciones fraudulentas: {fraude_weight:.2f}")

# Asignamos los pesos. SageMaker usará esta columna para penalizar fuertemente 
# al algoritmo cada vez que se equivoque al predecir un fraude.
train_df = train_df.withColumn("weightCol", F.when(F.col("Class") == 1, F.lit(fraude_weight)).otherwise(F.lit(1.0)))
test_df  = test_df.withColumn("weightCol", F.when(F.col("Class") == 1, F.lit(fraude_weight)).otherwise(F.lit(1.0)))

# -- PREPARACIÓN PARA SAGEMAKER Y CARGA EN S3 --

# El algoritmo built-in de XGBoost en SageMaker requiere que la variable objetivo ("Class")
# sea estrictamente la primera columna del dataset.
feature_cols = [f"V{i}" for i in range(1, 29)] + ["Amount_scaled", "Hour", "weightCol"]
final_columns = ["Class"] + feature_cols

train_df = train_df.select(final_columns)
test_df = test_df.select(final_columns)

# Rutas de destino (La variable BUCKET viene de args['BUCKET_NAME'] inicial)
TRAIN_PATH = f"s3://{BUCKET}/curated/train/"
TEST_PATH  = f"s3://{BUCKET}/curated/test/"

print("Escribiendo datasets Curated en S3...")
train_df.write.mode("overwrite").option("compression", "snappy").parquet(TRAIN_PATH)
test_df.write.mode("overwrite").option("compression", "snappy").parquet(TEST_PATH)

# --- Finalizar el Job y registrar Bookmarks ---
job.commit()