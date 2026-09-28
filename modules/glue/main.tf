# 1. Glue Data Catalog: La base de datos lógica que almacenará los metadatos
resource "aws_glue_catalog_database" "churn_db" {
  name = "churn_prediction_db"
}

# 2. Glue Crawler: Escanea la capa raw/ y detecta el esquema automáticamente
resource "aws_glue_crawler" "raw_crawler" {
  database_name = aws_glue_catalog_database.churn_db.name
  name          = "churn_raw_crawler"
  role          = var.glue_role_arn

  s3_target {
    path = "s3://${var.datalake_bucket_name}/raw/"
  }
}

# 3. Glue ETL Job: El motor Spark Serverless
resource "aws_glue_job" "etl_processor" {
  name     = "fraud_etl_processor"
  role_arn = var.glue_role_arn

  # Definimos que usará PySpark y la ruta donde subiremos el script más adelante
  command {
    name            = "glueetl"
    script_location = "s3://${var.datalake_bucket_name}/scripts/fraud_etl.py"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X" # Optimización de costos: Memoria y CPU balanceadas
  number_of_workers = 2      # Clúster mínimo inicial

  default_arguments = {
    "--job-bookmark-option" = "job-bookmark-enable" # Evita reprocesar datos antiguos
    "--enable-auto-scaling" = "true"                # Escala dinámicamente según la carga
    "--TempDir"             = "s3://${var.datalake_bucket_name}/temp/"
    "--BUCKET_NAME"         = var.datalake_bucket_name
    "--enable-observability-metrics" = "true" # para ver métricas
  }
}