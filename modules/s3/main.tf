# 1. El Bucket Principal
resource "aws_s3_bucket" "datalake" {
  bucket = var.bucket_name

  # Permitimos que Terraform pueda borrar el bucket en el futuro aunque tenga archivos dentro (ideal para entornos de desarrollo)
  force_destroy = true 
}

# 2. Bloqueo de Acceso Público (Seguridad de grado empresarial)
resource "aws_s3_bucket_public_access_block" "datalake_public_block" {
  bucket                  = aws_s3_bucket.datalake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 3. Creación de las Zonas Lógicas (Prefijos)
resource "aws_s3_object" "raw_zone" {
  bucket = aws_s3_bucket.datalake.id
  key    = "raw/"
}

resource "aws_s3_object" "processed_zone" {
  bucket = aws_s3_bucket.datalake.id
  key    = "processed/"
}

resource "aws_s3_object" "curated_zone" {
  bucket = aws_s3_bucket.datalake.id
  key    = "curated/"
}

resource "aws_s3_object" "predictions_zone" {
  bucket = aws_s3_bucket.datalake.id
  key    = "predictions/"
}

# Carpetas operativas para AWS Glue
resource "aws_s3_object" "scripts_zone" {
  bucket = aws_s3_bucket.datalake.id
  key    = "scripts/"
}

resource "aws_s3_object" "temp_zone" {
  bucket = aws_s3_bucket.datalake.id
  key    = "temp/"
}