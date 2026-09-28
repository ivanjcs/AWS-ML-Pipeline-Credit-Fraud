output "glue_role_arn" {
  description = "ARN del rol de Glue para ser usado en el módulo de procesamiento"
  value       = aws_iam_role.glue_etl_role.arn
}

output "sagemaker_role_arn" {
  description = "ARN del rol de SageMaker para ejecutar el Training y Batch Transform"
  value       = aws_iam_role.sagemaker_execution_role.arn
}

output "redshift_role_arn" {
  description = "ARN del rol de Redshift para ejecutar el COPY FROM S3"
  value       = aws_iam_role.redshift_load_role.arn
}

output "stepfunctions_role_arn" {
  description = "ARN del rol de Step Functions para orquestar el pipeline"
  value       = aws_iam_role.stepfunctions_role.arn
}