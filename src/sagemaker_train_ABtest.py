import os
import boto3
import logging
from dotenv import load_dotenv

from sagemaker.core.helper.session_helper import Session
from sagemaker.core.image_uris import retrieve
from sagemaker.train import ModelTrainer
from sagemaker.train.configs import InputData, Compute, StoppingCondition, OutputDataConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()
BUCKET_NAME = os.getenv("DATALAKE_BUCKET_NAME")
if not BUCKET_NAME:
    raise ValueError("Falta DATALAKE_BUCKET_NAME en el .env")

boto_session = boto3.Session()
region = boto_session.region_name

if not region:
    raise ValueError("boto3 no encontró región: configurá AWS_DEFAULT_REGION o `aws configure`")

sts_client = boto_session.client("sts")
ACCOUNT_ID = sts_client.get_caller_identity()["Account"]
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/SageMakerExecutionRole"



sagemaker_session = Session(boto_session=boto_session)
container_uri = retrieve(framework="xgboost", region=region, version="1.7-1")

train_input = InputData(channel_name="train", data_source=f"s3://{BUCKET_NAME}/curated/train/", content_type="application/x-parquet")
val_input = InputData(channel_name="validation", data_source=f"s3://{BUCKET_NAME}/curated/validation/",content_type="application/x-parquet")

experimentos = [
    {"name": "baseline_unweighted", "scale_pos_weight": 1},
    {"name": "cost_sensitive_577", "scale_pos_weight": 577}
]

resultados = {}

for exp in experimentos:
    name = exp["name"]
    logging.info(f"=== INICIANDO EXPERIMENTO: {name} ===")
 
    # Todo lo específico del experimento va dentro del try: si falla la creación
    # del trainer o el entrenamiento, se registra y se sigue con el siguiente.
    try:
        output_path = f"s3://{BUCKET_NAME}/models/{name}/"
 
        xgb_trainer = ModelTrainer(
            training_image=container_uri,
            role=ROLE_ARN,
            compute=Compute(
                instance_type="ml.m5.xlarge",
                instance_count=1
            ),
            stopping_condition=StoppingCondition(
                max_runtime_in_seconds=3600
            ),
            output_data_config=OutputDataConfig(
                s3_output_path=output_path
            ),
            # Las claves deben estar en minúscula (key, value)
            tags=[
                {"key": "Project", "value": "fraud-detection-pipeline"},
                {"key": "Experiment", "value": name}
            ],
            sagemaker_session=sagemaker_session,
            hyperparameters={
                "objective": "binary:logistic",
                "eval_metric": "aucpr",
                "num_round": 150,
                "early_stopping_rounds": 15,
                "max_depth": 5,
                "eta": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "scale_pos_weight": exp["scale_pos_weight"]
            }
        )
 
        logging.info(f"Entrenando modelo {name}...")
        xgb_trainer.train(input_data_config=[train_input, val_input])
 
        resultados[name] = "OK"
        logging.info(f"¡Modelo {name} guardado en {output_path}!\n")
 
    except Exception as e:
        # `except Exception` (y no un except vacío) deja pasar Ctrl+C (KeyboardInterrupt)
        resultados[name] = f"FALLÓ ({type(e).__name__})"
        logging.exception(f"El experimento {name} falló. Se continúa con el siguiente.\n")
        
        
        
# --- Resumen final ---
logging.info("=== RESUMEN DE EXPERIMENTOS ===")
for nombre, estado in resultados.items():
    logging.info(f"{nombre}: {estado}")
 
# Código de salida distinto de 0 si algún experimento falló
# (útil si más adelante lo corre Step Functions o un workflow de CI)
if any(estado != "OK" for estado in resultados.values()):
    sys.exit(1)        