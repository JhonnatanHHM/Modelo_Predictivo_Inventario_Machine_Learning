import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import OUT_RES, ORIGIN, TEST_START

COLORES = {"naive": "#6B7280", "ets": "#B45309", "lightgbm": "#15803D", "tft": "#1D4ED8"}

def graficas(master, preds, glob_df):
    OUT_RES.mkdir(parents=True, exist_ok=True)
    # 1) comparación global
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    for a, col, tit in zip(ax, ["MASE_medio", "pinball_escalada_media", "cobertura_80"],
                           ["MASE (menor es mejor)", "Pinball escalada (menor es mejor)", "Cobertura del rango P10-P90 (ideal 0,80)"]):
        a.bar(glob_df.index, glob_df[col], color=[COLORES.get(m, "#999") for m in glob_df.index])
        a.set_title(tit, fontsize=10)
        if col == "cobertura_80":
            a.axhline(0.8, color="k", ls="--", lw=1)
    fig.tight_layout(); fig.savefig(OUT_RES / "g1_comparacion_modelos.png", dpi=150); plt.close(fig)
    # 2) ejemplos de series
    uids = master.groupby("unique_id").y.sum().sort_values().index
    elegidos = [uids[len(uids) // 6], uids[len(uids) // 2], uids[-len(uids) // 6]] if len(uids) >= 6 else list(uids)[:3]
    fig, axs = plt.subplots(len(elegidos), 1, figsize=(11, 3.2 * len(elegidos)), squeeze=False)
    for a, uid in zip(axs[:, 0], elegidos):
        g = master[(master.unique_id == uid) & (master.dnum > ORIGIN - 56)].sort_values("dnum")
        a.plot(g.ds, g.y, color="k", lw=1.2, label="real")
        for m, p in preds.items():
            q = p[p.unique_id == uid].sort_values("ds")
            a.plot(q.ds, q.p50, color=COLORES.get(m, "#999"), lw=1.3, label=f"{m} P50")
            if m in ("lightgbm", "tft"):
                a.fill_between(q.ds, q.p10, q.p90, color=COLORES.get(m, "#999"), alpha=0.12)
        a.axvline(g[g.dnum == TEST_START].ds.iloc[0], color="gray", ls="--", lw=0.8)
        a.set_title(uid, fontsize=9); a.legend(fontsize=7, ncol=5, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT_RES / "g2_ejemplos_series.png", dpi=150); plt.close(fig)
