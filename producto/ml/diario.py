"""LightGBM con cuantiles diarios (P10, P50, P90) para los 28 días siguientes al origen. Es el modelo final del proyecto.

Misma receta que `laboratorio/src/lab_lgbm.py` (donde se probó y se midió), aplicada a los datos de la base:
  - 38 variables: 18 de la primera versión y 20 nuevas (intermitencia, días de la semana, tendencia, precio y calendario)
  - hiperparámetros ajustados con Optuna en 4 ventanas de validación (tasa baja, mucha regularización, hojas con muchas filas)
  - orígenes de entrenamiento cada 7 días durante 728 días; parada temprana en los 28 días anteriores al origen
"""
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
SPAN_ORIGEN = 728        # se usan los últimos 728 días de orígenes
PACIENCIA = 30
PARAMS = dict(n_estimators=1500, learning_rate=0.02195659111275476, num_leaves=111, max_depth=-1, min_child_samples=398,
              subsample=0.7013614804875485, subsample_freq=1, colsample_bytree=0.619743230321347, reg_alpha=0.0032847593837962213,
              reg_lambda=1.063942153262213, max_bin=63, path_smooth=5.304088936875766, verbose=-1, random_state=42)
VARS_BASE = ["h", "dow", "mes", "snap", "evento", "precio", "precio_rel", "ult", "m7", "m28", "m56", "sd28", "nz28", "lag_dow", "edad", "tienda", "depto", "estado"]
VARS_NUEVAS = ["dsl", "nz7", "nz14", "nz56", "m_pos28",                                       # intermitencia
               "lag_dow2", "lag_dow3", "lag_dow4", "dow_m4", "dow_nz4", "ratio_dow",          # mismos días de la semana anteriores
               "m14", "tend7_28", "tend28_56", "tr_tienda", "tr_grupo",                       # tendencia de la serie, la tienda y el grupo
               "precio_ult_rel", "precio_prev7", "dmes", "evento_tipo"]                       # precio y calendario
COLS_X = VARS_BASE + VARS_NUEVAS
CATEGORICAS = ["tienda", "depto", "estado"]


def _nanmean(a, axis=1):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(a, axis=axis)


def _frec(a):
    """Fracción de días con venta > 0 entre los días observados (ignora NaN)."""
    v = ~np.isnan(a)
    return ((a > 0) & v).sum(1) / np.maximum(v.sum(1), 1)


def filas_origen(D, o, series=None, con_y=True):
    """Variables de todas las series (o de `series`) con origen o (índice 0-based del último día observado) y h = 1..28."""
    Y, P = D.Y, D.P
    series = np.arange(Y.shape[0]) if series is None else np.asarray(series)
    ns = len(series)
    h = np.arange(1, H + 1)
    t = o + h
    base = o + 1 - 7 + ((h - 1) % 7)                                       # mismo día de la semana de la última semana
    w56, w28, w14, w7 = (Y[series, o - 55: o + 1], Y[series, o - 27: o + 1], Y[series, o - 13: o + 1], Y[series, o - 6: o + 1])
    rep = lambda v: np.repeat(np.asarray(v, dtype=float)[:, None], H, axis=1)
    pm = _nanmean(P[series, o - 27: o + 1])
    pt = P[series][:, t]
    m7, m14, m28, m56 = _nanmean(w7), _nanmean(w14), _nanmean(w28), _nanmean(w56)
    f = {
        "h": np.tile(h, (ns, 1)), "dow": np.tile(D.DOW[t], (ns, 1)), "mes": np.tile(D.MES[t], (ns, 1)),
        "snap": D.SN[series][:, t], "evento": D.EV[series][:, t], "precio": pt,
        "precio_rel": np.where((pm > 0)[:, None], pt / np.where(pm > 0, pm, 1)[:, None], np.nan),
        "ult": rep(Y[series, o]), "m7": rep(m7), "m28": rep(m28), "m56": rep(m56), "sd28": rep(np.nanstd(w28, axis=1)), "nz28": rep(_frec(w28)),
        "lag_dow": Y[series][:, base], "edad": rep(np.minimum(o - D.inicio[series], 1000)),
        "tienda": rep(D.tienda[series]), "depto": rep(D.depto[series]), "estado": rep(D.estado[series]),
    }
    eps = 1e-3
    l2, l3, l4 = (Y[series][:, base - 7], Y[series][:, base - 14], Y[series][:, base - 21])
    dow4 = np.stack([f["lag_dow"], l2, l3, l4], axis=0)
    dow_m4 = _nanmean(np.moveaxis(dow4, 0, -1), axis=2)
    ts, gs = D.TIENDA_SUM[series], D.GRUPO_SUM[series]
    f.update({
        "dsl": rep(np.minimum(o - D.ULT_POS[series, o], 100)),
        "nz7": rep(_frec(w7)), "nz14": rep(_frec(w14)), "nz56": rep(_frec(w56)),
        "m_pos28": rep(np.nan_to_num(_nanmean(np.where(w28 > 0, w28, np.nan)))),
        "lag_dow2": l2, "lag_dow3": l3, "lag_dow4": l4, "dow_m4": dow_m4,
        "dow_nz4": ((dow4 > 0) & ~np.isnan(dow4)).sum(0) / np.maximum((~np.isnan(dow4)).sum(0), 1),
        "ratio_dow": dow_m4 / (rep(m28) + eps),
        "m14": rep(m14), "tend7_28": rep(m7 / (m28 + eps)), "tend28_56": rep(m28 / (m56 + eps)),
        "tr_tienda": rep(ts[:, o - 6: o + 1].sum(1) / (ts[:, o - 27: o + 1].sum(1) / 4 + eps)),
        "tr_grupo": rep(gs[:, o - 6: o + 1].sum(1) / (gs[:, o - 27: o + 1].sum(1) / 4 + eps)),
        "precio_ult_rel": pt / P[series, o][:, None], "precio_prev7": pt / P[series][:, t - 7],
        "dmes": np.tile(D.DMES[t], (ns, 1)), "evento_tipo": np.tile(D.ETIPO[t], (ns, 1)),
    })
    with np.errstate(all="ignore"):
        df = pd.DataFrame({k: np.asarray(v, dtype=np.float32).ravel() for k, v in f.items()})
    df["serie"] = np.repeat(series, H)
    df["t"] = np.tile(t, ns)
    if con_y:
        df["y"] = Y[series][:, t].ravel()
    return df


def tablas(D, origen):
    """Entrenamiento, validación y prueba para un origen (d_N, 1-based, último día observado)."""
    o_val = origen - H - 1                       # los objetivos de la validación son los 28 días anteriores al origen
    o_tr_max = o_val - H                         # el último origen de entrenamiento no mira a la ventana de validación
    tr = []
    for o in range(o_tr_max, o_tr_max - SPAN_ORIGEN - 1, -PASO_ORIGEN):
        ok = np.where((o - D.inicio) >= 56)[0]
        if len(ok):
            tr.append(filas_origen(D, o, ok))
    va = filas_origen(D, o_val, np.where((o_val - D.inicio) >= 56)[0])
    te = filas_origen(D, origen - 1, None, con_y=False)
    tr = pd.concat(tr, ignore_index=True)
    tr, va = tr[tr.y.notna()], va[va.y.notna()]
    assert tr.t.max() + 1 <= origen - H and va.t.max() + 1 <= origen and te.t.min() + 1 == origen + 1
    return tr, va, te


def pronosticar(D, origen, carpeta_modelos=None):
    """origen = último día observado (d_N, 1-based). Devuelve un arreglo (n, 28, 3) con P10, P50, P90 (ordenados y no negativos)."""
    n = len(D.ids)
    tr, va, te = tablas(D, origen)
    Q = np.zeros((len(te), 3))
    for j, tau in enumerate(QUANTILES):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, **PARAMS)
        m.fit(tr[COLS_X], tr.y, eval_set=[(va[COLS_X], va.y)], eval_metric="quantile", categorical_feature=CATEGORICAS,
              callbacks=[lgb.early_stopping(PACIENCIA, verbose=False)])
        Q[:, j] = m.predict(te[COLS_X])
        if carpeta_modelos:
            Path(carpeta_modelos).mkdir(parents=True, exist_ok=True)
            m.booster_.save_model(str(Path(carpeta_modelos) / f"diario_{NOMBRES[j]}.txt"))
    Q = np.sort(np.clip(Q, 0, None), axis=1)
    out = np.full((n, H, 3), np.nan)
    for k in range(n):
        out[k] = Q[(te.serie == k).to_numpy()]
    return out
