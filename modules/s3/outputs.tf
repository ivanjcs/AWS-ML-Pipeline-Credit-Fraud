output "datalake_bucket_arn" {
  description = "ARN del bucket de S3"
  value       = aws_s3_bucket.datalake.arn
}

output "datalake_bucket_name" {
  description = "Nombre del bucket de S3"
  value       = aws_s3_bucket.datalake.id
}