"""Experimento 1: ¿ayudan las variables nuevas? Línea base, todas las nuevas, cada grupo agregado y cada grupo quitado.

Ventanas de validación (se usan para decidir): orígenes 1773, 1801, 1829 y 1857.
Las ventanas de prueba (1885 y 1913) NO se tocan aquí.
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")
import pandas as pd
import lab_lgbm as L

VALIDACION = [1773, 1801, 1829, 1857]
SAL = L.LAB / "resultados"
SAL.mkdir(exist_ok=True)

master, sel = L.cargar()
D = L.preparar(master)

configs = {"base": L.VARS_BASE, "todas_nuevas": L.VARS_BASE + L.VARS_NUEVAS}
for g, v in L.GRUPOS_NUEVOS.items():
    configs[f"base+{g}"] = L.VARS_BASE + v
for g, v in L.GRUPOS_NUEVOS.items():
    configs[f"todas-{g}"] = L.VARS_BASE + [x for x in L.VARS_NUEVAS if x not in v]

filas, series = [], []
for o in VALIDACION:
    c = L.cronometro()
    tr, va, te = L.tablas(D, o, nuevas=True)
    esc = L.escalas(master, o)
    print(f"origen {o}: tablas listas en {c():.0f} s ({len(tr):,} filas)", flush=True)
    for nombre, vars_ in configs.items():
        c2 = L.cronometro()
        out, it = L.ajustar_predecir(tr, va, te, vars_, L.PARAMS_BASE)
        ps, g = L.evaluar(L.a_pronostico(out, D), master, sel, o, esc)
        filas.append(dict(config=nombre, origen=o, n_vars=len(vars_), MASE=g.MASE_medio, pinball_esc=g.pinball_escalada_media,
                          WQL=g.WQL, cob80=g.cobertura_80, cob_p10=g.cobertura_p10, cob_p90=g.cobertura_p90, ancho=g.ancho_medio,
                          sesgo=g.sesgo_relativo, it_p10=it["p10"], it_p50=it["p50"], it_p90=it["p90"], seg=round(c2(), 1)))
        ps.insert(0, "config", nombre); ps.insert(1, "origen", o); series.append(ps)
        print(f"  {nombre:32s} MASE {g.MASE_medio:.4f}  pinball {g.pinball_escalada_media:.4f}  WQL {g.WQL:.4f}  ({c2():.0f} s)", flush=True)
    pd.DataFrame(filas).to_csv(SAL / "exp1_variables.csv", index=False)
pd.concat(series).to_parquet(SAL / "exp1_por_serie.parquet")
r = pd.DataFrame(filas)
print("\nPROMEDIO EN LAS 4 VENTANAS DE VALIDACIÓN")
print(r.groupby("config")[["MASE", "pinball_esc", "WQL", "cob80"]].mean().sort_values("MASE").round(4).to_string())
