"""
Intervalos de confianza por bootstrap para la evaluación de modelos de fraude.

- Remuestrea el set de test con reemplazo (estratificado: fraudes y legítimas por separado).
- Usa LAS MISMAS filas remuestreadas para todos los modelos (bootstrap PAREADO),
  de modo que las diferencias entre modelos se pueden comparar de forma justa.
- Calcula AUPRC (average precision) y precision/recall en el umbral YA CONGELADO con validation.
- Es reproducible: el resultado depende de `seed` y de `n_boot`, no de cuántos núcleos uses.
"""
import numpy as np
import matplotlib.pyplot as plt
from joblib import Parallel, delayed
from sklearn.metrics import average_precision_score

N_CHUNKS = 20  # fijo: así el resultado no cambia con n_jobs

def _run_chunk(y, scores, thresholds, n_iter, seed_seq, stratified):
    rng = np.random.default_rng(seed_seq)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    names = list(scores)

    out = {m: {"auprc": np.empty(n_iter), "precision": np.empty(n_iter), "recall": np.empty(n_iter)}
           for m in names}

    for i in range(n_iter):
        if stratified:
            idx = np.concatenate([rng.choice(pos, pos.size), rng.choice(neg, neg.size)])
        else:
            idx = rng.integers(0, y.size, y.size)
        yb = y[idx]
        n_pos = yb.sum()

        for m in names:
            sb = scores[m][idx]
            out[m]["auprc"][i] = average_precision_score(yb, sb)

            pred = sb >= thresholds[m]
            tp = np.count_nonzero(pred & (yb == 1))
            fp = np.count_nonzero(pred & (yb == 0))
            out[m]["precision"][i] = tp / (tp + fp) if (tp + fp) else 0.0
            out[m]["recall"][i] = tp / n_pos if n_pos else 0.0
    return out


def bootstrap_evaluation(y_true, scores, thresholds, n_boot=2000, seed=42,
                         n_jobs=-1, stratified=True):
    y = np.asarray(y_true).astype(int)
    scores = {m: np.asarray(s) for m, s in scores.items()}

    sizes = [len(c) for c in np.array_split(np.arange(n_boot), N_CHUNKS)]
    seeds = np.random.SeedSequence(seed).spawn(N_CHUNKS)

    parts = Parallel(n_jobs=n_jobs)(
        delayed(_run_chunk)(y, scores, thresholds, n, s, stratified)
        for n, s in zip(sizes, seeds) if n > 0
    )

    result = {}
    for m in scores:
        result[m] = {
            metric: np.concatenate([p[m][metric] for p in parts])
            for metric in ("auprc", "precision", "recall")
        }
    return result

# CORRECCIÓN: La sintaxis de los percentiles estaba rota en el original
def _ci(arr, level=95):
    p_lower = (100 - level) / 2
    p_upper = 100 - p_lower
    lo, hi = np.percentile(arr, [p_lower, p_upper])
    return lo, hi


def print_bootstrap_report(boot, baseline, labels=None, level=95):
    labels = labels or {}
    n_boot = len(next(iter(boot.values()))["auprc"])
    print(f"\n=== BOOTSTRAP ({n_boot} remuestreos, IC {level}%) ===")

    for m, metrics in boot.items():
        print(f"\n{labels.get(m, m)}")
        for metric, arr in metrics.items():
            lo, hi = _ci(arr, level)
            print(f"  {metric:<10} media={arr.mean():.4f}  IC=[{lo:.4f}, {hi:.4f}]")

    print(f"\n--- Diferencia pareada de AUPRC (modelo - {labels.get(baseline, baseline)}) ---")
    for m, metrics in boot.items():
        if m == baseline:
            continue
        diff = metrics["auprc"] - boot[baseline]["auprc"]
        lo, hi = _ci(diff, level)
        p_better = (diff > 0).mean()
        veredicto = ("la diferencia NO parece ruido" if (lo > 0 or hi < 0)
                     else "el IC incluye 0: no se puede descartar que sea ruido")
        print(f"  {labels.get(m, m)}: media={diff.mean():+.4f}  IC=[{lo:+.4f}, {hi:+.4f}]  "
              f"P(mejor que baseline)={p_better:.1%}  -> {veredicto}")


# ---------- NUEVA VISUALIZACIÓN STORYTELLING WITH DATA ----------
def plot_bootstrap_intervals(boot, baseline, labels=None, level=95, metric="auprc"):
    """
    Genera un gráfico de intervalos de confianza enfocado en comparar contra un baseline.
    """
    labels = labels or {}
    
    # Extraer métricas para ordenar y graficar
    stats = []
    for m, metrics in boot.items():
        arr = metrics[metric]
        mean_val = arr.mean()
        lo, hi = _ci(arr, level)
        stats.append({'model': m, 'mean': mean_val, 'lo': lo, 'hi': hi})
    
    # Ordenar de menor a mayor rendimiento
    stats = sorted(stats, key=lambda x: x['mean'])
    
    # Identificar datos del baseline y del mejor modelo
    baseline_stat = next(item for item in stats if item['model'] == baseline)
    mejor_stat = stats[-1]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # Sombrear el intervalo del baseline de fondo (ESTO ES CLAVE PARA LA COMPARACIÓN)
    ax.axvspan(baseline_stat['lo'], baseline_stat['hi'], color='#E5E5E5', alpha=0.6, zorder=0)
    ax.axvline(baseline_stat['mean'], color='#999999', linestyle='--', linewidth=1.5, zorder=0)

    # Trazar cada modelo
    y_positions = np.arange(len(stats))
    for i, stat in enumerate(stats):
        m = stat['model']
        label = labels.get(m, m)
        is_baseline = (m == baseline)
        is_best = (m == mejor_stat['model'])
        
        # Jerarquía visual: El mejor modelo resalta, el baseline es neutro, el resto atenuado
        if is_best:
            color = '#117733' # Verde oscuro (éxito)
            lw = 3.5
            ms = 10
            font_weight = 'bold'
            label = f"★ {label}"
        elif is_baseline:
            color = '#555555' # Gris oscuro
            lw = 2.5
            ms = 8
            font_weight = 'bold'
            label = f"{label} (Baseline)"
        else:
            color = '#888888' # Gris medio
            lw = 2.0
            ms = 7
            font_weight = 'normal'
            
        # Dibujar la línea del intervalo (error bar horizontal)
        ax.plot([stat['lo'], stat['hi']], [i, i], color=color, linewidth=lw, solid_capstyle='round', zorder=3)
        # Dibujar el punto de la media
        ax.plot(stat['mean'], i, 'o', color=color, markersize=ms, zorder=4)
        
        # Etiquetado directo sobre el gráfico (media y rangos)
        texto = f"{stat['mean']:.3f} [{stat['lo']:.3f} - {stat['hi']:.3f}]"
        ax.text(stat['hi'] + 0.005, i, texto, va='center', color=color, fontsize=10, fontweight=font_weight)

    # Configurar Eje Y
    ax.set_yticks(y_positions)
    ax.set_yticklabels([labels.get(s['model'], s['model']) for s in stats], fontsize=11, color='#333333')
    
    # Limpieza Visual (Decluttering)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False) # Quitamos la línea vertical izquierda
    ax.spines['bottom'].set_color('#DDDDDD')
    
    ax.tick_params(axis='y', length=0) # Sin marcas en Y
    ax.tick_params(axis='x', colors='#555555')
    
    # Cuadrícula sutil solo en X
    ax.xaxis.grid(True, linestyle='-', color='#EEEEEE', zorder=1)
    ax.set_axisbelow(True)
    
    # Título y contexto (Storytelling)
    metric_upper = metric.upper()
    solapamiento = mejor_stat['lo'] > baseline_stat['hi']
    if solapamiento:
        titulo = f"El mejor modelo supera al Baseline con significancia estadística"
        subtitulo = f"El intervalo de confianza ({level}%) de {labels.get(mejor_stat['model'], mejor_stat['model'])} no se solapa con el rango del baseline (franja gris)."
    else:
        titulo = f"El rendimiento del mejor modelo se solapa con el Baseline"
        subtitulo = f"Aunque {labels.get(mejor_stat['model'], mejor_stat['model'])} tiene mejor media, no podemos descartar que la diferencia con la franja gris sea ruido."
        
    fig.text(0.05, 1.05, titulo, fontsize=15, fontweight='bold', color='#222222')
    fig.text(0.05, 0.98, subtitulo, fontsize=12, color='#666666')
    ax.set_xlabel(f"Métrica: {metric_upper} (Media ± IC {level}%)", fontsize=11, color='#555555', labelpad=12)

    # Ajustar márgenes para dar espacio al texto derecho
    plt.subplots_adjust(right=0.85, left=0.15)
    
    plt.savefig("bootstrap_intervals.png", dpi=300, bbox_inches="tight")
    print(f"\n¡Gráfica de intervalos {metric_upper} guardada como bootstrap_intervals.png!")