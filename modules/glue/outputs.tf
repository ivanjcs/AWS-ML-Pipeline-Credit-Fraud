output "glue_job_name" {
  description = "El nombre del trabajo de Glue ETL"
  value       = aws_glue_job.etl_processor.name
}

output "glue_database_name" {
  description = "El nombre de la base de datos de Glue"
  value       = aws_glue_catalog_database.data_lake.name
}

output "glue_table_name" {
  description = "El nombre de la tabla cruda"
  value       = aws_glue_catalog_table.raw_transactions.name
}
