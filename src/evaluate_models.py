import os
import tarfile
import tempfile
from pathlib import Path
 
import boto3
import matplotlib.pyplot as plt
import pandas as pd
import xgboost as xgb
from dotenv import load_dotenv
from sklearn.metrics import (
    PrecisionRecallDisplay,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
)
 
load_dotenv()
BUCKET_NAME = os.getenv("DATALAKE_BUCKET_NAME")
if not BUCKET_NAME:
    raise ValueError("Falta DATALAKE_BUCKET_NAME en el .env")
 
s3_client = boto3.client("s3")
 
# Carpeta temporal: evita llenar el repo con parquets, tar.gz y modelos extraídos
WORKDIR = Path(tempfile.mkdtemp(prefix="eval_fraud_"))
 
MODELOS = {
    "baseline_unweighted": "Baseline (sin pesos)",
    "cost_sensitive_577": "Cost-sensitive (x577)",
}
COLORES = {"baseline_unweighted": "blue", "cost_sensitive_577": "red"}
 
 
# ---------- Utilidades S3 ----------
def list_objects(prefix):
    """Lista TODOS los objetos de un prefijo (list_objects_v2 devuelve máx. 1000 por llamada)."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objetos = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        objetos.extend(page.get("Contents", []))
    return objetos
 
 
def load_parquet_prefix(prefix):
    """Descarga todos los .parquet de un prefijo y los une en un DataFrame."""
    keys = [o["Key"] for o in list_objects(prefix) if o["Key"].endswith(".parquet")]
    if not keys:
        raise FileNotFoundError(f"No hay archivos .parquet en s3://{BUCKET_NAME}/{prefix}")
    dfs = []
    for key in keys:
        local_file = WORKDIR / key.replace("/", "_")  # evita colisiones entre carpetas
        s3_client.download_file(BUCKET_NAME, key, str(local_file))
        dfs.append(pd.read_parquet(local_file))
    return pd.concat(dfs, ignore_index=True)
 
 
def load_sagemaker_model(model_name):
    """Descarga el model.tar.gz MÁS RECIENTE (por fecha de modificación) y carga el Booster."""
    tars = [o for o in list_objects(f"models/{model_name}/") if o["Key"].endswith("model.tar.gz")]
    if not tars:
        raise FileNotFoundError(f"No hay model.tar.gz en s3://{BUCKET_NAME}/models/{model_name}/")
    latest = max(tars, key=lambda o: o["LastModified"])
    print(f"[{model_name}] usando {latest['Key']}")
 
    local_tar = WORKDIR / f"{model_name}.tar.gz"
    s3_client.download_file(BUCKET_NAME, latest["Key"], str(local_tar))
 
    extract_dir = WORKDIR / f"{model_name}_extracted"
    # filter="data" (si tu Python lo soporta) evita rutas peligrosas dentro del tar
    extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
    with tarfile.open(local_tar) as tar:
        tar.extractall(path=extract_dir, **extra)
 
    # SageMaker XGBoost >= 1.3-1 guarda con Booster.save_model -> se carga con load_model
    booster = xgb.Booster()
    booster.load_model(str(extract_dir / "xgboost-model"))
    return booster
 
 
def predict_proba(booster, X):
    """Predice con la mejor iteración si el modelo la trae (early stopping); requiere xgboost >= 1.4."""
    dmat = xgb.DMatrix(X)
    best_it = booster.attr("best_iteration")
    if best_it is not None:
        print(f"   best_iteration = {best_it}")
        return booster.predict(dmat, iteration_range=(0, int(best_it) + 1))
    return booster.predict(dmat)
 
 
# ---------- Datos ----------
print("Descargando validation y test...")
val_df = load_parquet_prefix("curated/validation/")
test_df = load_parquet_prefix("curated/test/")
 
y_val, X_val = val_df["class"], val_df.drop(columns="class")
y_test, X_test = test_df["class"], test_df.drop(columns="class")
 
# ---------- Evaluación ----------
resultados = {}
preds_test = {}
 
for nombre, etiqueta in MODELOS.items():
    print(f"\nEvaluando {etiqueta}...")
    booster = load_sagemaker_model(nombre)
 
    p_val = predict_proba(booster, X_val)
    p_test = predict_proba(booster, X_test)
    preds_test[nombre] = p_test
 
    # El umbral se elige SOLO con validation (máximo F1); test queda para reportar.
    # Con scale_pos_weight las probabilidades no están calibradas: 0.5 no es un umbral razonable.
    prec, rec, thr = precision_recall_curve(y_val, p_val)
    f1 = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-12)
    umbral = float(thr[f1.argmax()])
 
    y_pred = (p_test >= umbral).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    precision_t = tp / (tp + fp) if (tp + fp) else 0.0
    recall_t = tp / (tp + fn) if (tp + fn) else 0.0
    f1_t = 2 * precision_t * recall_t / (precision_t + recall_t) if (precision_t + recall_t) else 0.0
 
    resultados[nombre] = {
        "auprc_val": average_precision_score(y_val, p_val),
        "auprc_test": average_precision_score(y_test, p_test),
        "umbral_(val)": umbral,
        "precision_test": precision_t,
        "recall_test": recall_t,
        "f1_test": f1_t,
        "TP": int(tp),
        "FP": int(fp),
        "FN": int(fn),
    }
 
tabla = pd.DataFrame(resultados).T
print("\n=== RESULTADOS ===")
print(tabla.round(4).to_string())
tabla.round(4).to_csv("resultados_modelos.csv")
print("\nTabla guardada en resultados_modelos.csv (para el ADR-002 y el README)")
print("Elegí el modelo por AUPRC de VALIDATION; test es para reportar el resultado final.")
 
# ---------- Curva Precision-Recall (test) - STORYTELLING WITH DATA ----------

fig, ax = plt.subplots(figsize=(10, 6.5))

# Fondo completamente blanco
fig.patch.set_facecolor('white')
ax.set_facecolor('white')

# Identificar al mejor modelo para resaltarlo y armar el título
modelos_ordenados = sorted(MODELOS.keys(), key=lambda x: resultados[x]['auprc_test'], reverse=True)
mejor_modelo = modelos_ordenados[0]
mejor_etiqueta = MODELOS[mejor_modelo]

# Trazar las curvas manualmente para tener control total del diseño
for nombre in modelos_ordenados:
    etiqueta = MODELOS[nombre]
    auprc = resultados[nombre]['auprc_test']
    prec_curve, rec_curve, _ = precision_recall_curve(y_test, preds_test[nombre])

    # Jerarquía visual: Resaltar el mejor, atenuar los demás
    if nombre == mejor_modelo:
        lw = 3.0
        alpha = 1.0
        label_text = f"★ {etiqueta} (AUPRC = {auprc:.3f})"
    else:
        lw = 1.8
        alpha = 0.5
        label_text = f"    {etiqueta} (AUPRC = {auprc:.3f})"

    ax.plot(rec_curve, prec_curve, color=COLORES[nombre], linewidth=lw, alpha=alpha, label=label_text)

from bootstrap_ci import bootstrap_evaluation, print_bootstrap_report, plot_bootstrap_intervals

umbrales = {n: resultados[n]["umbral_(val)"] for n in MODELOS}
boot = bootstrap_evaluation(y_test, preds_test, umbrales,
                            n_boot=2000, seed=42, n_jobs=-1)
print_bootstrap_report(boot, baseline="baseline_unweighted", labels=MODELOS)
plot_bootstrap_intervals(
    boot=boot, 
    baseline="baseline_unweighted", 
    labels=MODELOS,
    metric="auprc" # Por defecto usa auprc, pero puedes cambiarlo a "precision" o "recall"
)

# Línea base (prevalencia)
prevalencia = y_test.mean()
ax.axhline(prevalencia, linestyle="--", color="#AAAAAA", linewidth=1.2)
# Etiquetado Directo (Direct Labeling) en lugar de usar la leyenda
ax.text(1.02, prevalencia, f"Línea base sin habilidad\n(Fraude: {prevalencia:.1%})", 
        color="#777777", va='center', ha='left', fontsize=10)

# --- Limpieza Visual (Decluttering) ---
# Quitar bordes innecesarios
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#DDDDDD')
ax.spines['bottom'].set_color('#DDDDDD')

# Quitar las "marquitas" (ticks) de los ejes pero dejar los números
ax.tick_params(axis='both', length=0, colors='#555555')

# Cuadrícula solo horizontal, sutil
ax.yaxis.grid(True, linestyle='-', color='#EEEEEE')
ax.xaxis.grid(False)

# Etiquetas de ejes limpias y descriptivas
ax.set_xlabel("Recall (Proporción de fraudes reales detectados)", fontsize=11, color='#555555', labelpad=12)
ax.set_ylabel("Precision (Asertividad de la alerta)", fontsize=11, color='#555555', labelpad=12)

# Límites fijos para estandarizar la vista
ax.set_xlim(0, 1)
ax.set_ylim(0, 1.05)

# --- Textos y Storytelling ---
# Título y subtítulo alineados a la izquierda como indica el estándar de lectura occidental
titulo = f"El modelo '{mejor_etiqueta}' supera al resto en la detección de fraude"
subtitulo = "Curva Precision-Recall (Test Set). Una curva más alta y cercana a 1.0 indica un mejor rendimiento."

fig.text(0.05, 0.98, titulo, fontsize=15, fontweight='bold', color='#222222')
fig.text(0.05, 0.93, subtitulo, fontsize=12, color='#666666')

# Leyenda limpia, sin bordes, ordenada lógicamente, ubicada en espacio negativo
ax.legend(frameon=False, loc='upper right', fontsize=11, bbox_to_anchor=(0.02, 0.02), labelcolor='#333333')

# Ajustar márgenes para que el título y la etiqueta lateral no se corten
plt.subplots_adjust(top=0.85, right=0.82, left=0.08)

fig.savefig("pr_curve_comparison.png", dpi=300, bbox_inches="tight")
print("\n¡Gráfica guardada como pr_curve_comparison.png con formato Storytelling with Data!")