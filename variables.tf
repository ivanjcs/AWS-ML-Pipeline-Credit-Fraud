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