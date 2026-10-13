import os
import boto3
import sagemaker
from dotenv import load_dotenv
from sagemaker.inputs import TrainingInput
from sagemaker.estimator import Estimator

# 1. Cargar configuración desde el archivo .env
load_dotenv()

BUCKET_NAME = os.getenv("DATALAKE_BUCKET_NAME")

if not BUCKET_NAME:
    raise ValueError("CRÍTICO: La variable DATALAKE_BUCKET_NAME no fue encontrada en el archivo .env")

print("Inicializando configuración de SageMaker...")

# 2. Configuración de sesión usando tus credenciales locales de AWS
boto_session = boto3.Session()
region = boto_session.region_name
sagemaker_session = sagemaker.Session(boto_session=boto_session)

# 3. Obtener el Account ID dinámicamente (Seguridad y Portabilidad)
sts_client = boto_session.client("sts")
ACCOUNT_ID = sts_client.get_caller_identity()["Account"]

# Armamos el ARN del rol automáticamente
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/SageMakerExecutionRole"

print(f"-> Cuenta AWS: {ACCOUNT_ID}")
print(f"-> Bucket objetivo: {BUCKET_NAME}")

# 4. Obtener el contenedor oficial de XGBoost de AWS
container_uri = sagemaker.image_uris.retrieve("xgboost", region, "1.7-1")

# 5. Punteros a la Capa Oro (Curated)
train_input = TrainingInput(
    s3_data=f"s3://{BUCKET_NAME}/curated/train/",
    content_type="application/x-parquet"
)
test_input = TrainingInput(
    s3_data=f"s3://{BUCKET_NAME}/curated/test/",
    content_type="application/x-parquet"
)

# 6. Configuración del Servidor de Entrenamiento (Estimator)
xgb_estimator = Estimator(
    image_uri=container_uri,
    role=ROLE_ARN,
    instance_count=1,
    instance_type="ml.m5.xlarge",
    use_spot_instances=True,
    max_run=3600,
    max_wait=7200,
    output_path=f"s3://{BUCKET_NAME}/models/",
    sagemaker_session=sagemaker_session
)

# 7. Hiperparámetros enfocados en Maximizar el Recall (Cost-Sensitive Learning)
xgb_estimator.set_hyperparameters(
    objective="binary:logistic",
    eval_metric="aucpr",             # Métrica de negocio principal (AUPRC)
    num_round=150,                   # Épocas de entrenamiento
    max_depth=5,                     # Profundidad baja/media para evitar memorizar la clase mayoritaria
    eta=0.1,                         # Tasa de aprendizaje conservadora
    subsample=0.8,                   # Muestreo de filas para robustez
    colsample_bytree=0.8,            # Muestreo de columnas (variables) para evitar depender de una sola señal
    scale_pos_weight=577             # PENALIZACIÓN CRÍTICA: Obliga al modelo a prestar 577 veces más atención a un fraude que a una transacción normal
)

# 8. Ejecución
print("Enviando trabajo a Amazon SageMaker... (Esto puede tomar entre 3 y 5 minutos)")
xgb_estimator.fit({"train": train_input, "validation": test_input})

print(f"¡Entrenamiento finalizado! Modelo guardado en s3://{BUCKET_NAME}/models/")