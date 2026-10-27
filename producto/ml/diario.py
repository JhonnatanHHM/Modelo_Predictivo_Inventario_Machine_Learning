"""LightGBM con cuantiles diarios (P10, P50, P90) para los 28 días siguientes al origen."""
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message=".*eval_set.*", category=Warning)   # aviso de LightGBM 4.7; sigue funcionando en 4.0 o superior
H = 28
QUANTILES = (0.1, 0.5, 0.9)
NOMBRES = ("p10", "p50", "p90")
PASO_ORIGEN = 7          # un origen de entrenamiento cada 7 días
SPAN_ORIGEN = 364        # se usan los últimos 364 días de orígenes
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, random_state=42)
COLS_X = ["h", "dow", "mes", "snap", "evento", "precio", "precio_rel", "ult", "m7", "m28", "m56", "sd28", "nz28", "lag_dow", "edad", "tienda", "depto", "estado"]


def filas_origen(D, k, o, con_y=True):
    """Filas (h = 1..28) de la serie k con origen o (índice 0-based del último día observado)."""
    y = D.Y[k]; s0 = D.inicio[k]
    hist = y[max(s0, o - 55): o + 1]
    h = np.arange(1, H + 1); t = o + h
    base = o + 1 - 7 + ((h - 1) % 7)                          # mismo día de la semana de la última semana
    w28 = y[max(s0, o - 27): o + 1]; w7 = y[max(s0, o - 6): o + 1]
    p28 = D.P[k, max(s0, o - 27): o + 1]; pm = np.nanmean(p28) if np.isfinite(p28).any() else np.nan
    pt = D.P[k, t]
    f = {"h": h, "dow": D.DOW[t], "mes": D.MES[t], "snap": D.SN[k, t], "evento": D.EV[k, t], "precio": pt,
         "precio_rel": pt / pm if pm == pm and pm > 0 else np.full(H, np.nan),
         "ult": np.full(H, y[o]), "m7": np.full(H, w7.mean()), "m28": np.full(H, w28.mean()), "m56": np.full(H, hist.mean()),
         "sd28": np.full(H, w28.std()), "nz28": np.full(H, (w28 > 0).mean()), "lag_dow": y[base],
         "edad": np.full(H, min(o - s0, 1000)), "tienda": np.full(H, D.tienda[k]), "depto": np.full(H, D.depto[k]), "estado": np.full(H, D.estado[k])}
    df = pd.DataFrame(f); df["serie"] = k; df["t"] = t
    if con_y:
        df["y"] = y[t]
    return df


def pronosticar(D, origen, carpeta_modelos=None):
    """origen = último día observado (d_N, 1-based). Devuelve un arreglo (n, 28, 3) con P10, P50, P90."""
    n = len(D.ids)
    train_end = origen - H                    # el entrenamiento solo ve objetivos hasta d_train_end
    o_val = train_end - 1                     # origen (0-based) de la validación: sus objetivos son los 28 días anteriores al origen
    o_tr_max = o_val - H                      # el último origen de entrenamiento no mira a la ventana de validación
    tr, va = [], []
    for k in range(n):
        o_min = max(D.inicio[k] + 56, o_tr_max - SPAN_ORIGEN)
        for o in range(o_tr_max, o_min - 1, -PASO_ORIGEN):
            tr.append(filas_origen(D, k, o))
        if o_val - D.inicio[k] >= 56:
            va.append(filas_origen(D, k, o_val))
    tr = pd.concat(tr, ignore_index=True); va = pd.concat(va, ignore_index=True)
    tr = tr[tr.y.notna()]; va = va[va.y.notna()]
    te = pd.concat([filas_origen(D, k, origen - 1, con_y=False) for k in range(n)], ignore_index=True)
    assert tr.t.max() + 1 <= origen - H and va.t.max() + 1 <= origen and te.t.min() + 1 == origen + 1
    Q = np.zeros((len(te), 3))
    for j, tau in enumerate(QUANTILES):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, **PARAMS)
        m.fit(tr[COLS_X], tr.y, eval_set=[(va[COLS_X], va.y)], eval_metric="quantile", categorical_feature=["tienda", "depto", "estado"],
              callbacks=[lgb.early_stopping(30, verbose=False)])
        Q[:, j] = m.predict(te[COLS_X])
        if carpeta_modelos:
            Path(carpeta_modelos).mkdir(parents=True, exist_ok=True)
            m.booster_.save_model(str(Path(carpeta_modelos) / f"diario_{NOMBRES[j]}.txt"))
    Q = np.sort(np.clip(Q, 0, None), axis=1)
    out = np.full((n, H, 3), np.nan)
    for k in range(n):
        out[k] = Q[(te.serie == k).to_numpy()]
    return out
