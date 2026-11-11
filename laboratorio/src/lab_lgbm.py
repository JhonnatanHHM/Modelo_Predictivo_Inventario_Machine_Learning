"""Biblioteca del modelo final: LightGBM de cuantiles con 37 variables, ajuste de hiperparámetros y evaluación por segmentos.

Lee la tabla maestra que construye `etapa1_tabla_maestra.py` (carpeta `datos_completa/`, no incluida en el repositorio) y usa las métricas de `metricas.py`.

Protocolo (por origen = último día que ve el modelo; ventana de prueba = los 28 días siguientes):
  - entrenamiento: orígenes cada `paso` días hasta `origen - 56` (el último no mira la validación)
  - validación (parada temprana): los 28 días anteriores al origen
  - prueba: d_{origen+1} .. d_{origen+28}
"""
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
LAB = AQUI.parent                                  # carpeta laboratorio/
TABLA = Path(os.environ["M5_TABLA_DIR"]) if os.environ.get("M5_TABLA_DIR") else LAB / "datos_completa"
sys.path.insert(0, str(AQUI))
import metricas as M  # noqa: E402

H = 28
LAST_DAY = 1941
CUANTILES = (0.1, 0.5, 0.9)
COLS_Q = ["p10", "p50", "p90"]
SEMILLA = 42

# parámetros de la línea base (primera versión del modelo)
PARAMS_BASE = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50,
                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=SEMILLA)

VARS_BASE = ["h", "dow", "mes", "snap", "evento", "precio", "precio_rel", "ult", "m7", "m28", "m56", "sd28", "nz28",
             "lag_dow", "edad", "tienda", "depto", "estado"]
# grupos de variables nuevas (para ablación)
GRUPOS_NUEVOS = {
    "intermitencia": ["dsl", "nz7", "nz14", "nz56", "m_pos28"],
    "dias_semana": ["lag_dow2", "lag_dow3", "lag_dow4", "dow_m4", "dow_nz4", "ratio_dow"],
    "tendencia": ["m14", "tend7_28", "tend28_56", "tr_tienda", "tr_grupo"],
    "precio_calendario": ["precio_ult_rel", "precio_prev7", "dmes", "evento_tipo"],
}
VARS_NUEVAS = [v for g in GRUPOS_NUEVOS.values() for v in g]
CATEGORICAS_BASE = ["tienda", "depto", "estado"]


def cargar():
    """Tabla maestra y catálogo de las 374 series (los crea etapa1_tabla_maestra.py)."""
    master = pd.read_parquet(TABLA / "tabla_maestra_alfa.parquet")
    sel = pd.read_csv(TABLA / "series_alfa.csv")
    return master, sel


def preparar(master):
    """Matrices serie x día y vectores de calendario. NaN antes del lanzamiento de cada serie."""
    ids = sorted(master.unique_id.unique())
    idx = {u: i for i, u in enumerate(ids)}
    n, T = len(ids), LAST_DAY
    Y = np.full((n, T), np.nan)
    P = np.full((n, T), np.nan)
    SN = np.zeros((n, T))
    EV = np.zeros((n, T))
    i = master.unique_id.map(idx).to_numpy()
    t = master.dnum.to_numpy() - 1
    Y[i, t] = master.y.to_numpy()
    P[i, t] = master.sell_price.to_numpy(float)
    SN[i, t] = master.snap.to_numpy()
    EV[i, t] = master.event_flag.to_numpy()
    cal = master.drop_duplicates("dnum").sort_values("dnum")
    ci = cal.dnum.to_numpy() - 1
    DOW = np.zeros(T)
    MES = np.zeros(T)
    DMES = np.zeros(T)
    ETIPO = np.zeros(T)
    DOW[ci] = cal.wday.to_numpy()
    MES[ci] = cal.month.to_numpy()
    DMES[ci] = cal.ds.dt.day.to_numpy()
    ETIPO[ci] = cal.event_type_1.astype("category").cat.codes.to_numpy()
    est = master.drop_duplicates("unique_id").set_index("unique_id").loc[ids]
    stat = {"store": est.store_id.astype("category").cat.codes.to_numpy(),
            "dept": est.dept_id.astype("category").cat.codes.to_numpy(),
            "state": est.state_id.astype("category").cat.codes.to_numpy()}
    inicio = np.array([np.where(~np.isnan(Y[k]))[0][0] for k in range(n)])
    # último día con venta positiva hasta cada día (para "días desde la última venta")
    pos = np.where(np.nan_to_num(Y) > 0, np.arange(T)[None, :], -1)
    ULT_POS = np.maximum.accumulate(pos, axis=1)
    # ventas agregadas por tienda y por tienda x departamento (para la tendencia del grupo)
    Y0 = np.nan_to_num(Y)
    g_tienda = stat["store"]
    g_grupo = stat["store"] * 100 + stat["dept"]
    S_t = {g: Y0[g_tienda == g].sum(0) for g in np.unique(g_tienda)}
    S_g = {g: Y0[g_grupo == g].sum(0) for g in np.unique(g_grupo)}
    TIENDA_SUM = np.vstack([S_t[g] for g in g_tienda])
    GRUPO_SUM = np.vstack([S_g[g] for g in g_grupo])
    fechas = cal.set_index("dnum")["ds"]
    return dict(ids=ids, Y=Y, P=P, SN=SN, EV=EV, DOW=DOW, MES=MES, DMES=DMES, ETIPO=ETIPO, stat=stat, inicio=inicio,
                ULT_POS=ULT_POS, TIENDA_SUM=TIENDA_SUM, GRUPO_SUM=GRUPO_SUM, fechas=fechas)


def _nanmean(a, axis=1):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(a, axis=axis)


def _frec(a):
    """Fracción de días con venta > 0 entre los días observados (ignora NaN)."""
    v = ~np.isnan(a)
    return ((a > 0) & v).sum(1) / np.maximum(v.sum(1), 1)


def filas_origen(D, o, series=None, con_y=True, nuevas=True):
    """Variables para todas las series con origen o (último día observado, índice 0-based) y h = 1..H."""
    Y, P = D["Y"], D["P"]
    n = Y.shape[0]
    series = np.arange(n) if series is None else series
    h = np.arange(1, H + 1)
    t = o + h
    base = o + 1 - 7 + ((h - 1) % 7)                      # mismo día de la semana de la última semana
    w56, w28, w14, w7 = (Y[series, o - 55: o + 1], Y[series, o - 27: o + 1], Y[series, o - 13: o + 1], Y[series, o - 6: o + 1])
    ns = len(series)
    rep = lambda v: np.repeat(np.asarray(v, dtype=float)[:, None], H, axis=1)
    pm = _nanmean(P[series, o - 27: o + 1])
    pt = P[series][:, t]
    f = {
        "h": np.tile(h, (ns, 1)), "dow": np.tile(D["DOW"][t], (ns, 1)), "mes": np.tile(D["MES"][t], (ns, 1)),
        "snap": D["SN"][series][:, t], "evento": D["EV"][series][:, t],
        "precio": pt,
        "precio_rel": np.where((pm > 0)[:, None], pt / np.where(pm > 0, pm, 1)[:, None], np.nan),
        "ult": rep(Y[series, o]), "m7": rep(_nanmean(w7)), "m28": rep(_nanmean(w28)), "m56": rep(_nanmean(w56)),
        "sd28": rep(np.nanstd(np.where(np.isnan(w28), np.nan, w28), axis=1)), "nz28": rep(_frec(w28)),
        "lag_dow": Y[series][:, base],
        "edad": rep(np.minimum(o - D["inicio"][series], 1000)),
        "tienda": rep(D["stat"]["store"][series]), "depto": rep(D["stat"]["dept"][series]), "estado": rep(D["stat"]["state"][series]),
    }
    if nuevas:
        m28 = _nanmean(w28)
        m56 = _nanmean(w56)
        m7 = _nanmean(w7)
        eps = 1e-3
        l2, l3, l4 = (Y[series][:, base - 7], Y[series][:, base - 14], Y[series][:, base - 21])
        dow4 = np.stack([f["lag_dow"], l2, l3, l4], axis=0)
        dow_m4 = _nanmean(np.moveaxis(dow4, 0, -1), axis=2)
        w28pos = np.where(w28 > 0, w28, np.nan)
        ts = D["TIENDA_SUM"][series]
        gs = D["GRUPO_SUM"][series]
        f.update({
            "dsl": rep(np.minimum(o - D["ULT_POS"][series, o], 100)),
            "nz7": rep(_frec(w7)), "nz14": rep(_frec(w14)), "nz56": rep(_frec(w56)),
            "m_pos28": rep(np.nan_to_num(_nanmean(w28pos))),
            "lag_dow2": l2, "lag_dow3": l3, "lag_dow4": l4, "dow_m4": dow_m4,
            "dow_nz4": ((dow4 > 0) & ~np.isnan(dow4)).sum(0) / np.maximum((~np.isnan(dow4)).sum(0), 1),
            "ratio_dow": dow_m4 / (rep(m28) + eps),
            "m14": rep(_nanmean(w14)), "tend7_28": rep(m7 / (m28 + eps)), "tend28_56": rep(m28 / (m56 + eps)),
            "tr_tienda": rep(ts[:, o - 6: o + 1].sum(1) / (ts[:, o - 27: o + 1].sum(1) / 4 + eps)),
            "tr_grupo": rep(gs[:, o - 6: o + 1].sum(1) / (gs[:, o - 27: o + 1].sum(1) / 4 + eps)),
            "precio_ult_rel": pt / P[series, o][:, None],
            "precio_prev7": pt / P[series][:, t - 7],
            "dmes": np.tile(D["DMES"][t], (ns, 1)), "evento_tipo": np.tile(D["ETIPO"][t], (ns, 1)),
        })
    df = pd.DataFrame({k: np.asarray(v, dtype=np.float32).ravel() for k, v in f.items()})
    df["serie"] = np.repeat(series, H)
    df["t"] = np.tile(t, ns)
    if con_y:
        df["y"] = Y[series][:, t].ravel()
    return df


def tablas(D, origen, paso=7, span=364, nuevas=True):
    """Entrenamiento, validación y prueba para un origen de evaluación (día `origen` = último que ve el modelo)."""
    inicio = D["inicio"]
    o_val = origen - H - 1                                 # 0-based del último día de entrenamiento: ventana de validación = origen-27..origen
    o_tr_max = o_val - H
    tr = []
    for o in range(o_tr_max, o_tr_max - span - 1, -paso):
        ok = np.where((o - inicio) >= 56)[0]
        if len(ok):
            tr.append(filas_origen(D, o, ok, True, nuevas))
    va_ok = np.where((o_val - inicio) >= 56)[0]
    va = filas_origen(D, o_val, va_ok, True, nuevas)
    te = filas_origen(D, origen - 1, None, False, nuevas)
    tr = pd.concat(tr, ignore_index=True)
    tr = tr[tr.y.notna()]
    va = va[va.y.notna()]
    return tr, va, te


def ajustar_predecir(tr, va, te, variables, params, categoricas=CATEGORICAS_BASE, paciencia=30, devolver_modelos=False):
    """Un modelo por cuantil (objetivo 'quantile') con parada temprana en la ventana de validación."""
    import lightgbm as lgb
    cats = [c for c in categoricas if c in variables]
    salida = {"serie": te["serie"].to_numpy(), "t": te["t"].to_numpy()}
    modelos, iteraciones = {}, {}
    for tau, col in zip(CUANTILES, COLS_Q):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, **params)
        m.fit(tr[variables], tr.y, eval_set=[(va[variables], va.y)], eval_metric="quantile",
              categorical_feature=cats, callbacks=[lgb.early_stopping(paciencia, verbose=False)])
        salida[col] = m.predict(te[variables])
        modelos[col] = m
        iteraciones[col] = m.best_iteration_
    out = pd.DataFrame(salida)
    return (out, iteraciones, modelos) if devolver_modelos else (out, iteraciones)


def a_pronostico(salida, D):
    """Devuelve unique_id, ds, p10, p50, p90 con cuantiles ordenados y no negativos."""
    v = np.sort(np.clip(salida[COLS_Q].to_numpy(float), 0, None), axis=1)
    ids = np.array(D["ids"])[salida["serie"].to_numpy()]
    ds = D["fechas"].reindex(salida["t"].to_numpy() + 1).to_numpy()
    out = pd.DataFrame({"unique_id": ids, "ds": ds})
    out[COLS_Q] = v
    return out


def escalas(master, origen):
    """Escala MASE por serie: error medio absoluto del naive estacional (rezago 7) hasta d_origen."""
    esc = {}
    for uid, g in master[master.dnum <= origen].groupby("unique_id"):
        y = g.sort_values("dnum")["y"].to_numpy(dtype=float)
        esc[uid] = np.abs(y[7:] - y[:-7]).mean() if len(y) > 7 else np.nan
    return pd.Series(esc, name="escala")


def evaluar(pred, master, sel, origen, esc=None):
    """Métricas por serie y resumen global para un pronóstico y un origen."""
    test = master[(master.dnum > origen) & (master.dnum <= origen + H)][["unique_id", "ds", "y"]]
    esc = escalas(master, origen) if esc is None else esc
    por_serie = M.evaluar_series(pred, test, esc)
    glob = M.resumen(por_serie, sel).iloc[0]
    return por_serie, glob


def no_dormir(activar=True):
    """Pide a Windows que no suspenda el equipo mientras corre un experimento (no cambia ningún ajuste del sistema)."""
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if activar else 0))
    except Exception:
        pass


def cronometro():
    t0 = time.time()
    return lambda: time.time() - t0
