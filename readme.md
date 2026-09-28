# 💳 AWS Fraud Detection ML Pipeline: Serverless Data Engineering & MLOps

![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Terraform](https://img.shields.io/badge/terraform-%235835CC.svg?style=for-the-badge&logo=terraform&logoColor=white)
![Apache Spark](https://img.shields.io/badge/apache%20spark-%23E25A1C.svg?style=for-the-badge&logo=apachespark&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

## 📌 Resumen
Este proyecto implementa una arquitectura **Serverless de Machine Learning** en Amazon Web Services (AWS) para identificar transacciones fraudulentas con tarjetas de crédito. 

Aborda un desafío del **desbalance de clases extremo (0.17% de fraude)** mediante un enfoque nativo en la nube: despliegue de Infraestructura como Código (IaC), construcción de un Data Lake bajo la **Arquitectura Medallón**, y procesamiento distribuido enfocado en la reproducibilidad estadística y la prevención de fuga de información (*Data Leakage*).

## Arquitectura e Infraestructura
Toda la infraestructura está gestionada a través de **Terraform**, aplicando el principio de privilegio mínimo (Least Privilege) en IAM.

*   **S3 Data Lake (Medallion Architecture):**
    *   🥉 `raw/`: Datos inmutables originales.
    *   🥈 `processed/`: Datos limpios, normalizados temporalmente y almacenados en formato columnar (Parquet + Snappy).
    *   🥇 `curated/`: Datasets particionados (Train/Test) listos para consumo por algoritmos de Machine Learning, con ingeniería de características avanzada aplicada.
*   **Procesamiento (AWS Glue):** Motor Apache Spark *serverless* utilizado para el ETL, escalamiento dinámico y particionamiento masivo de datos.

## Decisiones Clave de Ingeniería (Fase 1 y 2)

A diferencia de los enfoques tradicionales en entornos locales (Pandas/Scikit-Learn), este pipeline está diseñado para escalar en clústeres distribuidos:

1.  **Stratified Split Distribuido:** En lugar de depender de librerías locales, se implementó un particionamiento estratificado (80/20) utilizando **PySpark Window Functions** y percentiles, garantizando determinismo (seed=42) en múltiples nodos sin colapsar la memoria.
2.  **Prevención Estricta de Data Leakage:** El escalamiento de variables con colas pesadas (`Amount` mediante `log1p` y `RobustScaler`) se ajusta (`.fit()`) **estrictamente sobre el conjunto de entrenamiento**, aplicando la transformación resultante a ambos conjuntos.
3.  **Cost-Sensitive Learning Nativo:** En lugar de técnicas costosas de sobremuestreo (como SMOTE), se integró el balanceo dinámico de pesos (`weightCol`) directamente en PySpark. Se calcula dinámicamente el factor de penalización para XGBoost basándose inversamente en la frecuencia de la clase mayoritaria.

## 🚀 Estado del Proyecto (Roadmap)

- [x] **Fase 0:** Despliegue de Infraestructura (Terraform, IAM, S3, Glue).
- [x] **Fase 1:** [Análisis Exploratorio (EDA) local y diseño de estrategia](notebooks/1.%20EDA.ipynb).
- [x] **Fase 2:** Serverless ETL en AWS Glue (PySpark) -> Capa Processed (Limpieza).
- [x] **Fase 3:** Feature Engineering y Pipeline ML -> Capa Curated (ML-Ready).
- [ ] **Fase 4:** Entrenamiento del Modelo (XGBoost en Amazon SageMaker). *(En desarrollo)*
- [ ] **Fase 5:** Inferencia Batch y Orquestación (AWS Step Functions). *(Próximamente)*

## 📂 Estructura del Repositorio

```text
├── modules/                # Módulos de Terraform (IaC)
│   ├── glue/               # Configuración del clúster serverless y Crawler
│   ├── iam/                # Políticas estrictas de acceso
│   └── s3/                 # Zonas del Data Lake (Medallón)
├── notebooks/              # Jupyter Notebooks (EDA y experimentación local)
├── src/                    # Código fuente de aplicación
│   └── fraud_etl.py        # Script PySpark principal (AWS Glue)
├── main.tf                 # Orquestador principal de Terraform
├── variables.tf            # Definición de variables globales
└── .gitignore              # Protección de credenciales y datos crudos
