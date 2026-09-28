variable "datalake_bucket_name" {
  description = "Nombre del bucket principal del Data Lake"
  type        = string
}

variable "glue_role_arn" {
  description = "ARN del rol de IAM con permisos para AWS Glue"
  type        = string
}