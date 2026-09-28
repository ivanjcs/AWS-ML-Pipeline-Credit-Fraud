output "glue_database_name" {
  value = aws_glue_catalog_database.churn_db.name
}

output "glue_crawler_name" {
  value = aws_glue_crawler.raw_crawler.name
}

output "glue_job_name" {
  value = aws_glue_job.etl_processor.name
}