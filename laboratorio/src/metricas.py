import numpy as np, pandas as pd
from config import QUANTILES, ORIGIN

COLS_Q = ["p10", "p50", "p90"]

def pinball(y, qhat, tau):
    d = y - qhat
    return np.maximum(tau * d, (tau - 1) * d)

def escalas(master):
    """Escala por serie = error medio absoluto del naive estacional (rezago 7) en el historial visto (hasta d_ORIGIN)."""
    esc = {}
    for uid, g in master[master.dnum <= ORIGIN].groupby("unique_id"):
        y = g.sort_values("dnum")["y"].to_numpy(dtype=float)
        e = np.abs(y[7:] - y[:-7]).mean() if len(y) > 7 else np.nan
        esc[uid] = e
    return pd.Series(esc, name="escala")

def evaluar_series(pred, test, esc):
    """pred: unique_id, ds, p10,p50,p90 (un modelo). test: unique_id, ds, y. Devuelve una fila por serie."""
    m = test[["unique_id", "ds", "y"]].merge(pred, on=["unique_id", "ds"], how="inner")
    assert len(m) == len(test), f"Predicciones incompletas: {len(m)} de {len(test)}"
    filas = []
    for uid, g in m.groupby("unique_id"):
        y = g["y"].to_numpy(float)
        pl = np.mean([pinball(y, g[c].to_numpy(float), t).mean() for c, t in zip(COLS_Q, QUANTILES)])
        e = esc.get(uid, np.nan)
        filas.append({
            "unique_id": uid,
            "mae": np.abs(y - g.p50).mean(),
            "mase": np.abs(y - g.p50).mean() / e if e and e > 0 else np.nan,
            "pinball_media": pl,
            "pinball_escalada": pl / e if e and e > 0 else np.nan,
            "cob_p10": float((y <= g.p10).mean()), "cob_p50": float((y <= g.p50).mean()), "cob_p90": float((y <= g.p90).mean()),
            "cob_80": float(((y >= g.p10) & (y <= g.p90)).mean()),
            "ancho_80": float((g.p90 - g.p10).mean()),
            "sesgo_unid": float((g.p50 - y).mean()), "suma_y": float(y.sum()), "suma_p50": float(g.p50.sum()),
            "wql_num": float(sum(2 * pinball(y, g[c].to_numpy(float), t).sum() for c, t in zip(COLS_Q, QUANTILES))),
        })
    return pd.DataFrame(filas)

def _agregar(g):
    return pd.Series({
        "n_series": len(g), "MASE_medio": g.mase.mean(), "MASE_mediana": g.mase.median(), "MASE_p90": g.mase.quantile(.9),
        "pinball_escalada_media": g.pinball_escalada.mean(),
        "WQL": g.wql_num.sum() / max(g.suma_y.sum(), 1e-9),
        "cobertura_p10": g.cob_p10.mean(), "cobertura_p90": g.cob_p90.mean(), "cobertura_80": g.cob_80.mean(),
        "ancho_medio": g.ancho_80.mean(),
        "sesgo_relativo": (g.suma_p50.sum() - g.suma_y.sum()) / max(g.suma_y.sum(), 1e-9),
        "dispersion_MASE_desv": g.mase.std()})

def resumen(por_serie, sel, columna=None):
    """Resumen global (columna=None) o por segmento (store_id, dept_id, cat_id, tier)."""
    d = por_serie.merge(sel[["id", "store_id", "dept_id", "cat_id", "tier"]], left_on="unique_id", right_on="id", how="left")
    if columna is None:
        return _agregar(d).to_frame().T
    filas = {k: _agregar(g) for k, g in d.groupby(columna)}
    return pd.DataFrame(filas).T
