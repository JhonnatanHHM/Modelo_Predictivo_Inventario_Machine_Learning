"""Experimento 3: ¿más orígenes de entrenamiento (más filas) o más historia mejoran el modelo ajustado?

Usa los mejores parámetros del experimento 2 (37 variables) en las ventanas de validación 1773, 1801, 1829 y 1857.
Configuraciones (paso entre orígenes en días, historia en días): (7, 364) referencia de la Unidad 1, (3, 364), (7, 728), (3, 728), (1, 364).
"""
import sys, warnings, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")
import pandas as pd
import lab_lgbm as L

L.no_dormir()
VALIDACION = [1773, 1801, 1829, 1857]
SAL = L.LAB / "resultados"
mejor = json.load(open(SAL / "exp2_mejor_todas_nuevas.json"))
VARS, PARAMS = mejor["variables"], dict(mejor["mejores_parametros"], verbose=-1, random_state=L.SEMILLA, subsample_freq=1)
CONFIGS = [(7, 364), (3, 364), (7, 728), (3, 728), (1, 364)]
master, sel = L.cargar()
D = L.preparar(master)
filas = []
for o in VALIDACION:
    esc = L.escalas(master, o)
    for paso, span in CONFIGS:
        c = L.cronometro()
        tr, va, te = L.tablas(D, o, paso=paso, span=span, nuevas=True)
        out, it = L.ajustar_predecir(tr, va, te, VARS, PARAMS)
        ps, g = L.evaluar(L.a_pronostico(out, D), master, sel, o, esc)
        filas.append(dict(paso=paso, historia=span, origen=o, filas=len(tr), MASE=g.MASE_medio, pinball_esc=g.pinball_escalada_media,
                          WQL=g.WQL, cob80=g.cobertura_80, it_p50=it["p50"], seg=round(c(), 1)))
        print(f"origen {o} paso {paso} historia {span}: filas {len(tr):,}  MASE {g.MASE_medio:.4f}  pinball {g.pinball_escalada_media:.4f}  ({c():.0f} s)", flush=True)
        pd.DataFrame(filas).to_csv(SAL / "exp3_origenes.csv", index=False)
r = pd.DataFrame(filas)
print("\nPROMEDIO EN LAS 4 VENTANAS")
print(r.groupby(["paso", "historia"])[["filas", "MASE", "pinball_esc", "WQL", "cob80", "seg"]].mean().round(4).to_string())
