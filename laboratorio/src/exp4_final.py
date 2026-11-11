"""Experimento 4: evaluación final en las ventanas de PRUEBA (origenes 1885 y 1913), una sola vez.

Compara el modelo de la Unidad 1 (18 variables, parámetros fijos, 364 días de historia) con el modelo final de la Unidad 2
(37 variables, parámetros ajustados, 728 días de historia). Calcula:
  - métricas por ventana y promedio, con intervalos de confianza por remuestreo de series (diferencia pareada)
  - métricas por segmento (tienda, rotación, categoría, departamento) y brechas entre segmentos, antes y después
  - frecuencia de cruce de cuantiles antes de ordenarlos
  - importancia de variables (ganancia y SHAP nativo de LightGBM con pred_contrib)
Uso: python src/exp4_final.py [min_child_samples]   (por defecto, el de los mejores parámetros de la ronda 1)
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import lab_lgbm as L

L.no_dormir()
PRUEBA = [1885, 1913]
SAL = L.LAB / "resultados"
mcs = int(sys.argv[1]) if len(sys.argv) > 1 else None
m1 = json.load(open(SAL / "exp2_mejor_todas_nuevas.json"))
VARS_F = m1["variables"]
PARAMS_F = dict(m1["mejores_parametros"], verbose=-1, random_state=L.SEMILLA, subsample_freq=1)
if mcs:
    PARAMS_F["min_child_samples"] = mcs

master, sel = L.cargar()
D = L.preparar(master)
sel = sel.copy()
modelos = {
    "unidad1": dict(vars=L.VARS_BASE, params=L.PARAMS_BASE, paso=7, span=364, nuevas=False),
    "final": dict(vars=VARS_F, params=PARAMS_F, paso=7, span=728, nuevas=True),
}
por_serie, filas, cruce, importancias = [], [], [], {}
for o in PRUEBA:
    esc = L.escalas(master, o)
    for nombre, cfg in modelos.items():
        tr, va, te = L.tablas(D, o, paso=cfg["paso"], span=cfg["span"], nuevas=cfg["nuevas"])
        out, it, mods = L.ajustar_predecir(tr, va, te, cfg["vars"], cfg["params"], devolver_modelos=True)
        crudo = out[L.COLS_Q].to_numpy()
        cruce.append(dict(modelo=nombre, origen=o, filas_con_cruce=float(((crudo[:, 0] > crudo[:, 1]) | (crudo[:, 1] > crudo[:, 2])).mean())))
        ps, g = L.evaluar(L.a_pronostico(out, D), master, sel, o, esc)
        ps.insert(0, "modelo", nombre); ps.insert(1, "origen", o)
        por_serie.append(ps)
        filas.append(dict(modelo=nombre, origen=o, MASE=g.MASE_medio, pinball_esc=g.pinball_escalada_media, WQL=g.WQL, cob80=g.cobertura_80,
                          cob_p10=g.cobertura_p10, cob_p90=g.cobertura_p90, ancho=g.ancho_medio, sesgo=g.sesgo_relativo, it_p50=it["p50"]))
        print(f"{nombre:8s} origen {o}: MASE {g.MASE_medio:.4f}  pinball {g.pinball_escalada_media:.4f}  WQL {g.WQL:.4f}  cob80 {g.cobertura_80:.4f}", flush=True)
        if nombre == "final" and o == PRUEBA[-1]:
            X = te[cfg["vars"]]
            m50 = mods["p50"]
            gan = pd.Series(m50.booster_.feature_importance("gain"), index=cfg["vars"])
            contrib = m50.booster_.predict(X, pred_contrib=True)[:, :-1]
            shap = pd.Series(np.abs(contrib).mean(0), index=cfg["vars"])
            imp = pd.DataFrame({"ganancia_pct": 100 * gan / gan.sum(), "shap_abs_medio": shap, "shap_pct": 100 * shap / shap.sum()}).sort_values("shap_pct", ascending=False)
            imp.to_csv(SAL / "exp4_importancia_p50.csv")
            print(imp.head(12).round(2).to_string(), flush=True)
r = pd.DataFrame(filas)
r.to_csv(SAL / "exp4_ventanas_prueba.csv", index=False)
d = pd.concat(por_serie)
d.to_parquet(SAL / "exp4_por_serie.parquet")
pd.DataFrame(cruce).to_csv(SAL / "exp4_cruce_cuantiles.csv", index=False)

# ---- promedio y diferencia pareada con IC por remuestreo de series
print("\nPROMEDIO EN LAS VENTANAS DE PRUEBA")
print(r.groupby("modelo")[["MASE", "pinball_esc", "WQL", "cob80", "ancho", "sesgo"]].mean().round(4).to_string())
rng = np.random.default_rng(0)
pares = []
for col in ("mase", "pinball_escalada", "mae"):
    A = d[d.modelo == "unidad1"].pivot_table(index="unique_id", columns="origen", values=col).mean(1)
    B = d[d.modelo == "final"].pivot_table(index="unique_id", columns="origen", values=col).mean(1)
    x = (B - A).dropna().to_numpy()
    bs = np.array([rng.choice(x, len(x)).mean() for _ in range(5000)])
    pares.append(dict(metrica=col, dif_media=x.mean(), ic_inf=np.percentile(bs, 2.5), ic_sup=np.percentile(bs, 97.5), pct_series_mejor=float((x < 0).mean())))
    print(f"final - unidad1, {col}: {x.mean():+.4f}  IC95 [{np.percentile(bs, 2.5):+.4f}, {np.percentile(bs, 97.5):+.4f}]  mejor en {100 * (x < 0).mean():.0f} % de las series")
pd.DataFrame(pares).to_csv(SAL / "exp4_diferencia_pareada.csv", index=False)

# ---- por segmento y brechas
seg = d.merge(sel[["id", "store_id", "dept_id", "cat_id", "tier"]], left_on="unique_id", right_on="id", how="left")
filas_seg = []
for col in ("store_id", "tier", "cat_id", "dept_id"):
    for (m, k), g in seg.groupby(["modelo", col]):
        filas_seg.append(dict(segmento=col, valor=k, modelo=m, n_series=g.unique_id.nunique(), MASE=g.mase.mean(), pinball_esc=g.pinball_escalada.mean(),
                              cob80=g.cob_80.mean(), sesgo_rel=(g.suma_p50.sum() - g.suma_y.sum()) / max(g.suma_y.sum(), 1e-9)))
S = pd.DataFrame(filas_seg)
S.to_csv(SAL / "exp4_por_segmento.csv", index=False)
print("\nBRECHAS ENTRE SEGMENTOS (máximo - mínimo del MASE y desviación)")
for col in ("store_id", "tier", "cat_id", "dept_id"):
    for m in ("unidad1", "final"):
        g = S[(S.segmento == col) & (S.modelo == m)]
        print(f"{col:9s} {m:8s} MASE max-min {g.MASE.max() - g.MASE.min():.4f}  desv {g.MASE.std():.4f}   peor: {g.loc[g.MASE.idxmax(), 'valor']} ({g.MASE.max():.3f})")
