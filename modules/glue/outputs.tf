output "glue_ingestion_job_name" {
  description = "El nombre del trabajo de Glue ETL de Ingestión"
  value       = aws_glue_job.ingestion_processor.name
}

output "glue_curation_job_name" {
  description = "El nombre del trabajo de Glue ETL de Curación"
  value       = aws_glue_job.curation_processor.name
}

output "glue_database_name" {
  description = "El nombre de la base de datos de Glue"
  value       = aws_glue_catalog_database.data_lake.name
}

output "glue_table_name" {
  description = "El nombre de la tabla cruda"
  value       = aws_glue_catalog_table.raw_transactions.name
}
