"""Experimento 2c: barrido dirigido de min_child_samples (y num_leaves) con historia de 728 días.

La ronda 2 de Optuna tardaba ~10 min por prueba y con su arranque aleatorio no alcanzaba a aprender, así que se sustituye por
un barrido de pocos puntos alrededor del óptimo de la ronda 1 (min_child_samples 398 estaba pegado al tope del rango).
Todo lo demás se deja en los mejores parámetros de la ronda 1.
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
m1 = json.load(open(SAL / "exp2_mejor_todas_nuevas.json"))
VARS = m1["variables"]
BASE = dict(m1["mejores_parametros"], verbose=-1, random_state=L.SEMILLA, subsample_freq=1)
CONFIGS = [("mcs 398 (ronda 1)", {}), ("mcs 800", {"min_child_samples": 800}), ("mcs 1500", {"min_child_samples": 1500}),
           ("mcs 800 hojas 200", {"min_child_samples": 800, "num_leaves": 200}), ("mcs 3000", {"min_child_samples": 3000})]
master, sel = L.cargar()
D = L.preparar(master)
tablas = {o: (*L.tablas(D, o, span=728, nuevas=True), L.escalas(master, o)) for o in VALIDACION}
print("tablas listas", flush=True)
filas = []
for nombre, cambio in CONFIGS:
    p = dict(BASE, **cambio)
    pin, mas, cob, wql, seg = [], [], [], [], 0
    c = L.cronometro()
    for o in VALIDACION:
        tr, va, te, esc = tablas[o]
        out, it = L.ajustar_predecir(tr, va, te, VARS, p)
        ps, g = L.evaluar(L.a_pronostico(out, D), master, sel, o, esc)
        pin.append(g.pinball_escalada_media); mas.append(g.MASE_medio); cob.append(g.cobertura_80); wql.append(g.WQL)
    f = dict(config=nombre, MASE=sum(mas) / 4, pinball_esc=sum(pin) / 4, WQL=sum(wql) / 4, cob80=sum(cob) / 4, seg=round(c()),
             pinball_por_ventana=[round(x, 5) for x in pin])
    filas.append(f)
    pd.DataFrame(filas).to_csv(SAL / "exp2c_barrido.csv", index=False)
    print(f"prueba {nombre}: pinball {f['pinball_esc']:.5f}  MASE {f['MASE']:.4f}  WQL {f['WQL']:.4f}  cob80 {f['cob80']:.4f}  ({f['seg']} s)  por ventana {f['pinball_por_ventana']}", flush=True)
