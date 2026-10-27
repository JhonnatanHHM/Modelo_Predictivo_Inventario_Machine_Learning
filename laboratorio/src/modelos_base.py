"""Modelos de comparación: naive estacional, ETS (statsforecast) y LightGBM por cuantiles."""
import numpy as np, pandas as pd
from config import QUANTILES, ORIGIN, TRAIN_END, TEST_START, LAST_DAY, H, LGBM_ORIGIN_STEP, LGBM_ORIGIN_SPAN, LGBM_PARAMS
from utils import log

def _ordenar(df):
    """Fuerza p10<=p50<=p90 y no negativos."""
    v = np.sort(np.clip(df[["p10", "p50", "p90"]].to_numpy(float), 0, None), axis=1)
    out = df[["unique_id", "ds"]].copy(); out[["p10", "p50", "p90"]] = v
    return out

# ---------------------------------------------------------------- naive estacional
def pronostico_naive(master):
    train = master[master.dnum <= ORIGIN]; test = master[master.dnum >= TEST_START]
    filas = []
    for uid, g in train.groupby("unique_id"):
        y = g.sort_values("dnum")["y"].to_numpy(float)
        res = (y[7:] - y[:-7])[-91:]                         # residuos del naive en los últimos ~3 meses
        q10, q50, q90 = np.quantile(res, QUANTILES)
        fechas = test[test.unique_id == uid].sort_values("dnum")["ds"].to_numpy()
        for h in range(1, H + 1):
            base = y[len(y) - 7 + ((h - 1) % 7)]            # mismo día de la semana de la última semana vista
            filas.append((uid, fechas[h - 1], base + q10, base + q50, base + q90))
    return _ordenar(pd.DataFrame(filas, columns=["unique_id", "ds", "p10", "p50", "p90"]))

# ---------------------------------------------------------------- ETS
def pronostico_ets(master):
    from statsforecast import StatsForecast
    from statsforecast.models import AutoETS
    train = master[master.dnum <= ORIGIN][["unique_id", "ds", "y"]].copy(); train["y"] = train["y"].astype(float)
    sf = StatsForecast(models=[AutoETS(season_length=7)], freq="D", n_jobs=1)
    f = sf.forecast(df=train, h=H, level=[80])
    if "unique_id" not in f.columns:
        f = f.reset_index()
    f = f.rename(columns={"AutoETS": "p50", "AutoETS-lo-80": "p10", "AutoETS-hi-80": "p90"})
    return _ordenar(f[["unique_id", "ds", "p10", "p50", "p90"]])

# ---------------------------------------------------------------- LightGBM
def _arreglos(master):
    """Pasa la tabla larga a matrices (series x días). NaN antes del lanzamiento."""
    ids = sorted(master.unique_id.unique()); idx = {u: i for i, u in enumerate(ids)}
    n = len(ids); T = LAST_DAY
    Y = np.full((n, T), np.nan); P = np.full((n, T), np.nan); SN = np.zeros((n, T)); EV = np.zeros((n, T))
    DOW = np.zeros(T); MES = np.zeros(T)
    i = master.unique_id.map(idx).to_numpy(); t = master.dnum.to_numpy() - 1
    Y[i, t] = master.y.to_numpy(); P[i, t] = master.sell_price.to_numpy(float)
    SN[i, t] = master.snap.to_numpy(); EV[i, t] = master.event_flag.to_numpy()
    cal = master.drop_duplicates("dnum").sort_values("dnum"); DOW[cal.dnum.to_numpy() - 1] = cal.wday.to_numpy(); MES[cal.dnum.to_numpy() - 1] = cal.month.to_numpy()
    est = master.drop_duplicates("unique_id").set_index("unique_id").loc[ids]
    stat = {"store": est.store_id.astype("category").cat.codes.to_numpy(), "dept": est.dept_id.astype("category").cat.codes.to_numpy(),
            "state": est.state_id.astype("category").cat.codes.to_numpy()}
    inicio = np.array([np.where(~np.isnan(Y[k]))[0][0] for k in range(n)])
    return ids, Y, P, SN, EV, DOW, MES, stat, inicio

def _filas_origen(k, o, Y, P, SN, EV, DOW, MES, stat, inicio, con_y=True):
    """Todas las filas (h=1..H) de la serie k con origen o (último día observado, índice 0-based)."""
    y = Y[k]; s0 = inicio[k]
    hist = y[max(s0, o - 55): o + 1]
    h = np.arange(1, H + 1); t = o + h
    base = o + 1 - 7 + ((h - 1) % 7)                          # mismo día de semana de la última semana
    w28 = y[max(s0, o - 27): o + 1]; w7 = y[max(s0, o - 6): o + 1]
    p28 = P[k, max(s0, o - 27): o + 1]; pm = np.nanmean(p28) if np.isfinite(p28).any() else np.nan
    pt = P[k, t]
    f = {
        "h": h, "dow": DOW[t], "mes": MES[t], "snap": SN[k, t], "evento": EV[k, t], "precio": pt,
        "precio_rel": pt / pm if pm == pm and pm > 0 else np.full(H, np.nan),
        "ult": np.full(H, y[o]), "m7": np.full(H, w7.mean()), "m28": np.full(H, w28.mean()), "m56": np.full(H, hist.mean()),
        "sd28": np.full(H, w28.std()), "nz28": np.full(H, (w28 > 0).mean()), "lag_dow": y[base],
        "edad": np.full(H, min(o - s0, 1000)), "tienda": np.full(H, stat["store"][k]), "depto": np.full(H, stat["dept"][k]), "estado": np.full(H, stat["state"][k]),
    }
    df = pd.DataFrame(f); df["serie"] = k; df["t"] = t
    if con_y:
        df["y"] = y[t]
    return df

COLS_X = ["h", "dow", "mes", "snap", "evento", "precio", "precio_rel", "ult", "m7", "m28", "m56", "sd28", "nz28", "lag_dow", "edad", "tienda", "depto", "estado"]

def construir_tablas_lgbm(master):
    """Arma las tablas de entrenamiento, validación y prueba (sin necesitar LightGBM)."""
    ids, Y, P, SN, EV, DOW, MES, stat, inicio = _arreglos(master)
    args = (Y, P, SN, EV, DOW, MES, stat, inicio)
    tr, va = [], []
    o_val = TRAIN_END - 1                    # índice 0-based de d_TRAIN_END (origen de validación)
    o_tr_max = o_val - H                     # el último origen de entrenamiento no mira a la ventana de validación
    for k in range(len(ids)):
        o_min = max(inicio[k] + 56, o_tr_max - LGBM_ORIGIN_SPAN)
        for o in range(o_tr_max, o_min - 1, -LGBM_ORIGIN_STEP):   # orígenes cada 7 días hacia atrás
            tr.append(_filas_origen(k, o, *args))
        if o_val - inicio[k] >= 56:
            va.append(_filas_origen(k, o_val, *args))             # validación: d_1886..d_1913
    tr = pd.concat(tr, ignore_index=True); va = pd.concat(va, ignore_index=True)
    tr = tr[tr.y.notna()]; va = va[va.y.notna()]
    te = pd.concat([_filas_origen(k, ORIGIN - 1, *args, con_y=False) for k in range(len(ids))], ignore_index=True)
    return ids, tr, va, te

def pronostico_lgbm(master):
    import lightgbm as lgb
    ids, tr, va, te = construir_tablas_lgbm(master)
    log().info(f"LightGBM: filas de entrenamiento {len(tr):,}, validación {len(va):,}, prueba {len(te):,}")
    assert tr.t.max() + 1 <= TRAIN_END and va.t.max() + 1 <= ORIGIN and te.t.min() + 1 == TEST_START
    sal = {"unique_id": [ids[k] for k in te.serie], "dnum": te.t + 1}
    for tau, col in zip(QUANTILES, ["p10", "p50", "p90"]):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, **LGBM_PARAMS)
        m.fit(tr[COLS_X], tr.y, eval_set=[(va[COLS_X], va.y)], eval_metric="quantile",
              categorical_feature=["tienda", "depto", "estado"], callbacks=[lgb.early_stopping(30, verbose=False)])
        log().info(f"LightGBM q={tau}: mejor iteración {m.best_iteration_}")
        from config import OUT_RES
        (OUT_RES / "modelo_lgbm").mkdir(parents=True, exist_ok=True); m.booster_.save_model(str(OUT_RES / "modelo_lgbm" / f"q{col}.txt"))
        sal[col] = m.predict(te[COLS_X])
    out = pd.DataFrame(sal)
    fechas = master.drop_duplicates("dnum")[["dnum", "ds"]]
    out = out.merge(fechas, on="dnum", how="left")
    return _ordenar(out[["unique_id", "ds", "p10", "p50", "p90"]])
