variable "datalake_bucket_name" {
  description = "Nombre del bucket principal del Data Lake"
  type        = string
}

variable "glue_role_arn" {
  description = "ARN del rol de IAM con permisos para AWS Glue"
  type        = string
}
variable "database_name" {
  description = "Nombre de la base de datos del Glue Catalog"
  type        = string
  default     = "fraud_detection_catalog"
}

variable "table_name" {
  description = "Nombre de la tabla cruda"
  type        = string
  default     = "raw_transactions"
}