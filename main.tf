# 1. Llamamos al módulo S3 para crear el Data Lake
module "s3_datalake" {
  source = "./modules/s3"

  # ATENCIÓN: Los nombres en S3 deben ser únicos en todo el mundo.
  # Agrega una combinación única como tu nombre y el año.
  bucket_name = "ivan-fraud-prediction-datalake-2026" 
}

# 2. Llamamos al módulo IAM para crear los Roles
module "iam_roles" {
  source = "./modules/iam"

  # En lugar de usar un string temporal, ahora usamos el output dinámico de S3.
  # Terraform sabrá que debe crear el bucket ANTES de crear los roles.
  datalake_bucket_arn = module.s3_datalake.datalake_bucket_arn
}

# 3. Llamamos al módulo de procesamiento (Glue)
module "glue_processing" {
  source = "./modules/glue"

  # Le pasamos los outputs generados por los módulos anteriores
  datalake_bucket_name = module.s3_datalake.datalake_bucket_name
  glue_role_arn        = module.iam_roles.glue_role_arn
}