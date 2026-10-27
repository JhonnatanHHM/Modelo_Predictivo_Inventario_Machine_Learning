"""LightGBM que predice directamente el cuantil de la demanda TOTAL (semanal y de 28 días); base de la reposición.
En las pruebas, el cuantil tau tiene una cobertura real cercana a tau, así que tau se puede leer como nivel de servicio."""
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

TAUS = (0.5, 0.8, 0.9, 0.95)
PARAMS = dict(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=50, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, random_state=42)
COLS = ["sem", "ult_L", "m7", "m28", "m56", "sd28", "nz28", "edad", "precio", "precio_rel", "snap", "evento", "mes", "tienda", "depto", "estado"]


def fila(D, k, o, w0, L):
    """Rasgos de la serie k con último día observado o (d_o, 1-based) para la ventana de L días que empieza en o + 1 + w0."""
    s0 = D.inicio[k]; hist = D.Y[k, s0:o]
    if len(hist) < 56:
        return None
    t0 = o + w0
    p = D.P[k, t0:t0 + L]; p_hist = D.P[k, max(s0, o - 28):o]
    pm = np.nanmean(p) if np.isfinite(p).any() else np.nan
    ph = np.nanmean(p_hist) if np.isfinite(p_hist).any() else np.nan
    return [w0 // 7, hist[-L:].sum() if L == 7 else hist[-28:].sum(), hist[-7:].mean(), hist[-28:].mean(), hist[-56:].mean(), hist[-28:].std(),
            (hist[-28:] > 0).mean(), min(o - s0, 1000), pm, pm / ph if ph and ph > 0 else np.nan, D.SN[k, t0:t0 + L].sum(),
            D.EV[k, t0:t0 + L].sum(), D.MES[t0 + L // 2], D.tienda[k], D.depto[k], D.estado[k]]


def tabla(D, O, L, w0s, entrenamiento):
    X, y = [], []
    for k in range(len(D.ids)):
        for w0 in w0s:
            if entrenamiento:
                o_max = O - w0 - L                                   # el objetivo termina a más tardar en O
                for o in range(o_max, max(D.inicio[k] + 56, O - 28 - 364) - 1, -7):
                    f = fila(D, k, o, w0, L); t = D.Y[k, o + w0:o + w0 + L]
                    if f is not None and np.isfinite(t).all():
                        X.append(f); y.append(t.sum())
            else:
                f = fila(D, k, O, w0, L)
                if f is not None:
                    X.append(f); y.append(np.nan)
    return pd.DataFrame(X, columns=COLS), np.array(y)


def _predecir(D, O, L, w0s, carpeta, nombre):
    Xtr, ytr = tabla(D, O, L, w0s, True)
    Xte, _ = tabla(D, O, L, w0s, False)
    Q = np.zeros((len(Xte), len(TAUS)))
    for j, tau in enumerate(TAUS):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, **PARAMS)
        m.fit(Xtr, ytr, categorical_feature=["tienda", "depto", "estado"])
        Q[:, j] = m.predict(Xte)
        if carpeta:
            Path(carpeta).mkdir(parents=True, exist_ok=True)
            m.booster_.save_model(str(Path(carpeta) / f"agregado_{nombre}_tau{tau}.txt"))
    return np.sort(np.clip(Q, 0, None), axis=1)


def pronosticar(D, origen, carpeta_modelos=None):
    """Devuelve (Qsem, Q28): Qsem (n, 4, len(TAUS)) con la demanda de cada una de las 4 semanas y Q28 (n, len(TAUS)) con la de los 28 días."""
    n = len(D.ids)
    Qsem = _predecir(D, origen, 7, [0, 7, 14, 21], carpeta_modelos, "semana").reshape(n, 4, len(TAUS))
    Q28 = _predecir(D, origen, 28, [0], carpeta_modelos, "28d")
    return Qsem, Q28
