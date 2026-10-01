# 1. Política de Confianza: Le permite al servicio AWS Glue "ponerse" este rol
data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

# 2. Creación de la identidad (Rol)
resource "aws_iam_role" "glue_etl_role" {
  name               = "GlueETLRole"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
}


# 3. Política de Permisos: Mínimo privilegio estricto para el Data Lake
data "aws_iam_policy_document" "glue_permissions" {
  # Lectura (Agregamos scripts/ para que lea el código y temp/ para operaciones de Spark)
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      var.datalake_bucket_arn,
      "${var.datalake_bucket_arn}/raw/*",
      "${var.datalake_bucket_arn}/processed/*",
      "${var.datalake_bucket_arn}/scripts/*",
      "${var.datalake_bucket_arn}/temp/*"
    ]
  }

# Escritura y Borrado (Ajustado para los marcadores de directorio de Hadoop/Spark)
  statement {
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${var.datalake_bucket_arn}/processed/*",
      "${var.datalake_bucket_arn}/processed_$folder$",
      "${var.datalake_bucket_arn}/curated/*",
      "${var.datalake_bucket_arn}/curated_$folder$",
      "${var.datalake_bucket_arn}/temp/*",
      "${var.datalake_bucket_arn}/temp_$folder$"
    ]
  }

  # Permisos básicos para usar el Data Catalog y guardar logs de la ejecución
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "glue:CreateTable",
      "glue:GetTable",
      "glue:UpdateTable",
      "glue:CreateDatabase",
      "glue:GetDatabase"
    ]
    resources = ["*"]
  }
}

# 4. Enlazar la política de permisos al rol que creamos
resource "aws_iam_role_policy" "glue_etl_policy_attachment" {
  name   = "GlueETLPrivileges"
  role   = aws_iam_role.glue_etl_role.id
  policy = data.aws_iam_policy_document.glue_permissions.json
}


# ==========================================
# ROL DE SAGEMAKER (Entrenamiento e Inferencia)
# ==========================================

# 1. Política de Confianza: Permite a SageMaker asumir este rol
data "aws_iam_policy_document" "sagemaker_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

# 2. Creación de la identidad
resource "aws_iam_role" "sagemaker_execution_role" {
  name               = "SageMakerExecutionRole"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume_role.json
}

# 3. Política de Permisos: Mínimo privilegio para Machine Learning
data "aws_iam_policy_document" "sagemaker_permissions" {
  # Solo puede leer los datos de entrenamiento de la capa curated/
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      var.datalake_bucket_arn,
      "${var.datalake_bucket_arn}/curated/*",
      "${var.datalake_bucket_arn}/models/*"
    ]
  }

  # Solo puede escribir los resultados finales en la capa predictions/
  statement {
    actions   = ["s3:PutObject"]
    resources = [
      "${var.datalake_bucket_arn}/predictions/*",
      "${var.datalake_bucket_arn}/models/*"
    ]
  }

  # Permisos para escribir métricas de evaluación (AUC-ROC, etc.) y logs en CloudWatch
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
  }

  # PERMISO CLAVE: Necesario para que SageMaker pueda descargar el algoritmo XGBoost (built-in)
  statement {
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage"
    ]
    resources = ["*"]
  }
}




# 4. Enlazar la política al rol de SageMaker
resource "aws_iam_role_policy" "sagemaker_policy_attachment" {
  name   = "SageMakerPrivileges"
  role   = aws_iam_role.sagemaker_execution_role.id
  policy = data.aws_iam_policy_document.sagemaker_permissions.json
}

# ==========================================
# ROL DE REDSHIFT (Carga Analítica)
# ==========================================

# 1. Política de Confianza: Permite a Redshift asumir este rol
data "aws_iam_policy_document" "redshift_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
  }
}

# 2. Creación de la identidad
resource "aws_iam_role" "redshift_load_role" {
  name               = "RedshiftS3LoadRole"
  assume_role_policy = data.aws_iam_policy_document.redshift_assume_role.json
}

# 3. Política de Permisos: Mínimo privilegio para ingesta
data "aws_iam_policy_document" "redshift_permissions" {
  # Lectura estricta únicamente sobre la zona de predicciones
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      var.datalake_bucket_arn,
      "${var.datalake_bucket_arn}/predictions/*"
    ]
  }
}

# 4. Enlazar la política al rol de Redshift
resource "aws_iam_role_policy" "redshift_policy_attachment" {
  name   = "RedshiftLoadPrivileges"
  role   = aws_iam_role.redshift_load_role.id
  policy = data.aws_iam_policy_document.redshift_permissions.json
}

# ==========================================
# ROL DE STEP FUNCTIONS (Orquestador)
# ==========================================

# 1. Política de Confianza: Permite a Step Functions asumir este rol
data "aws_iam_policy_document" "stepfunctions_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

# 2. Creación de la identidad
resource "aws_iam_role" "stepfunctions_role" {
  name               = "StepFunctionsOrchestratorRole"
  assume_role_policy = data.aws_iam_policy_document.stepfunctions_assume_role.json
}

# 3. Política de Permisos
data "aws_iam_policy_document" "stepfunctions_permissions" {
  # Disparar y monitorear el Job de Glue
  statement {
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun"
    ]
    resources = ["*"]
  }

  # Disparar Training Job y Batch Transform en SageMaker
  statement {
    actions = [
      "sagemaker:CreateTrainingJob",
      "sagemaker:DescribeTrainingJob",
      "sagemaker:StopTrainingJob",
      "sagemaker:CreateTransformJob",
      "sagemaker:DescribeTransformJob",
      "sagemaker:StopTransformJob",
      "sagemaker:CreateModel"
    ]
    resources = ["*"]
  }

  # Publicar notificaciones de éxito/fallo
  statement {
    actions   = ["sns:Publish"]
    resources = ["*"]
  }

  # PERMISO CRÍTICO: PassRole. Step Functions debe poder pasarle
  # sus respectivos roles a Glue y SageMaker cuando los invoca.
  statement {
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.glue_etl_role.arn,
      aws_iam_role.sagemaker_execution_role.arn
    ]
  }
}

# 4. Enlazar la política al rol de Step Functions
resource "aws_iam_role_policy" "stepfunctions_policy_attachment" {
  name   = "StepFunctionsOrchestratorPrivileges"
  role   = aws_iam_role.stepfunctions_role.id
  policy = data.aws_iam_policy_document.stepfunctions_permissions.json
}