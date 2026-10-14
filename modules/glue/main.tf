resource "aws_glue_catalog_database" "data_lake" {
  name = var.database_name
}

locals {
  raw_columns = concat(
    [{ name = "time", type = "double" }],
    [for i in range(1, 29) : { name = "v${i}", type = "double" }],
    [
      { name = "amount", type = "double" },
      { name = "class", type = "int" },
    ]
  )
}

resource "aws_glue_catalog_table" "raw_transactions" {
  name          = var.table_name
  database_name = aws_glue_catalog_database.data_lake.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification           = "csv"
    "skip.header.line.count" = "1"
  }

  storage_descriptor {
    location      = "s3://${var.datalake_bucket_name}/raw/creditcard/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.OpenCSVSerde"
      parameters = {
        separatorChar = ","
        quoteChar     = "\""
      }
    }

    dynamic "columns" {
      for_each = local.raw_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

# --- JOB 1: INGESTION ---
resource "aws_glue_job" "ingestion_processor" {
  name     = "fraud_etl_processor"
  role_arn = var.glue_role_arn

  # Definimos que usará PySpark y la ruta donde subiremos el script más adelante
  command {
    name            = "glueetl"
    script_location = "s3://${var.datalake_bucket_name}/scripts/fraud_etl_ingestion.py"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X" # Optimización de costos: Memoria y CPU balanceadas
  number_of_workers = 2      # Clúster mínimo inicial

  default_arguments = {
    "--job-bookmark-option"          = "job-bookmark-disable" # Evita reprocesar datos antiguos
    "--enable-auto-scaling"          = "true"                 # Escala dinámicamente según la carga
    "--TempDir"                      = "s3://${var.datalake_bucket_name}/temp/"
    "--BUCKET_NAME"                  = var.datalake_bucket_name
    "--DATABASE_NAME"                = var.database_name
    "--TABLE_NAME"                   = var.table_name
    "--enable-observability-metrics" = "true" # para ver métricas
  }
}

# --- JOB 2: CURATION ---
resource "aws_glue_job" "curation_processor" {
  name     = "fraud_etl_curation"
  role_arn = var.glue_role_arn

  command {
    name            = "glueetl"
    script_location = "s3://${var.datalake_bucket_name}/scripts/fraud_etl_curation.py"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2

  default_arguments = {
    # Este Job NO usa Bookmarks porque lee el set procesado completo cada vez
    "--job-bookmark-option"          = "job-bookmark-disable" 
    "--enable-auto-scaling"          = "true"
    "--TempDir"                      = "s3://${var.datalake_bucket_name}/temp/"
    "--BUCKET_NAME"                  = var.datalake_bucket_name
    # No necesita DATABASE_NAME ni TABLE_NAME porque lee directo de S3
    "--enable-observability-metrics" = "true"
  }
}