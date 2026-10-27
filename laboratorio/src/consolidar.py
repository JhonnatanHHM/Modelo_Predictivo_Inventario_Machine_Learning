"""Junta todas las corridas de resultados_completa y compara modelos por ventana, semilla y segmento.
Uso: python src/consolidar.py   -> escribe resultados_completa/CONSOLIDADO.md y consolidado_*.csv
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import metricas as M

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "resultados_completa"
sel = pd.read_csv(ROOT / "datos_completa" / "series_alfa.csv")

def corridas():
    for d in sorted(RES.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "metricas_por_serie.csv").exists():
            yield d

filas = []
for d in corridas():
    ps = pd.read_csv(d / "metricas_por_serie.csv").rename(columns={"Unnamed: 0": "modelo"})
    ps = ps.drop(columns=[c for c in ps.columns if c.startswith("Unnamed")])
    partes = d.name.split("_")
    origen = int(partes[1][1:]) if partes[0] in ("base", "tft") else None
    variante = "_".join(partes[2:]) if partes[0] == "tft" else "base"
    for modelo, g in ps.groupby("modelo"):
        if partes[0] == "tft" and modelo != "tft":
            continue                                   # naive ya viene en la corrida base
        if partes[0] == "base" and modelo == "tft":
            continue
        g = g.copy(); g["origen"] = origen; g["variante"] = variante if modelo == "tft" else "base"
        g["modelo_id"] = modelo if modelo != "tft" else f"tft_{variante}"
        filas.append(g)
todo = pd.concat(filas, ignore_index=True)
todo.to_csv(RES / "consolidado_por_serie.csv", index=False)

def agregar(g):
    return M._agregar(g)

# ---- 1) tabla por modelo x ventana
por_vent = todo.groupby(["modelo_id", "origen"]).apply(agregar, include_groups=False).reset_index()
por_vent.to_csv(RES / "consolidado_por_modelo_ventana.csv", index=False)
pv = por_vent.pivot(index="modelo_id", columns="origen", values="MASE_medio").round(3)
# ---- 2) promedio sobre las ventanas comunes (las 3 con TFT) para comparar justo
comunes = [1857, 1885, 1913]                       # ventanas que tienen la configuración base del TFT: comparación justa
sub = todo[todo.origen.isin(comunes)]
ventanas_tft = sorted(todo[todo.modelo_id.str.startswith("tft_")].origen.unique())
sub_all = todo[todo.origen.isin(ventanas_tft)]       # todas las ventanas con algún TFT (para diferencias pareadas)
glob = sub.groupby("modelo_id").apply(agregar, include_groups=False)
glob["ventanas"] = sub.groupby("modelo_id").origen.apply(lambda s: ",".join(str(x) for x in sorted(s.unique())))
glob.to_csv(RES / "consolidado_global_ventanas_comunes.csv")
# ---- 3) por rotación y por tienda
sub2 = sub.merge(sel[["id", "tier", "store_id", "cat_id"]], left_on="unique_id", right_on="id", how="left")
por_tier = sub2.pivot_table(index="modelo_id", columns="tier", values="mase", aggfunc="mean").round(3)
por_cat = sub2.pivot_table(index="modelo_id", columns="cat_id", values="mase", aggfunc="mean").round(3)
por_tienda = sub2.pivot_table(index="modelo_id", columns="store_id", values="mase", aggfunc="mean").round(3)
# ---- 4) diferencias pareadas con bootstrap (misma serie y ventana)
rng = np.random.default_rng(0)
def pareada(a, b):
    x = sub_all.pivot_table(index=["unique_id", "origen"], columns="modelo_id", values="mase")
    if a not in x or b not in x:
        return None
    d = (x[a] - x[b]).dropna().to_numpy()
    bs = [rng.choice(d, len(d)).mean() for _ in range(2000)]
    return f"{a} - {b}: {d.mean():+.3f} (IC95 {np.percentile(bs, 2.5):+.3f} a {np.percentile(bs, 97.5):+.3f}); {a} mejor en {(d < 0).mean():.0%} de {len(d)} casos"
tfts = [m for m in sorted(todo.modelo_id.unique()) if m.startswith("tft_")]
pares = [pareada("lightgbm", "ets"), pareada("lightgbm", "naive")] + [pareada(t, "lightgbm") for t in tfts] + [pareada(t, "ets") for t in tfts[:1]] + [pareada("tft_h64", "tft_s1")]
# ---- 5) semillas: variación del mismo TFT en la ventana 1913
sem = por_vent[(por_vent.modelo_id.str.startswith("tft_")) & (por_vent.origen == 1913)][["modelo_id", "MASE_medio", "pinball_escalada_media", "WQL", "cobertura_80", "sesgo_relativo"]].round(3)

glob = glob.reindex(sorted(glob.index, key=lambda m: (not m.startswith(("naive", "ets", "lightgbm")), m)))
cols = ["ventanas", "MASE_medio", "MASE_mediana", "pinball_escalada_media", "WQL", "cobertura_p90", "cobertura_80", "ancho_medio", "sesgo_relativo"]
with open(RES / "CONSOLIDADO.md", "w", encoding="utf-8") as f:
    f.write(f"# Consolidado del set completo (374 series)\n\nVentanas con TFT: {comunes}. Línea base en todas sus ventanas.\n\n")
    f.write("## MASE medio por modelo y ventana (origen = último día visto)\n\n```\n" + pv.to_string() + "\n```\n\n")
    f.write("## Global en las ventanas comunes\n\n```\n" + glob[cols].round(3).to_string() + "\n```\n\n")
    f.write("## MASE por rotación\n\n```\n" + por_tier.to_string() + "\n```\n\n## MASE por categoría\n\n```\n" + por_cat.to_string() + "\n```\n\n## MASE por tienda\n\n```\n" + por_tienda.to_string() + "\n```\n\n")
    f.write("## Diferencias pareadas (MASE, negativo = el primero es mejor)\n\n" + "\n".join("- " + p for p in pares if p) + "\n\n")
    f.write("## TFT en la ventana 1913 según variante (semilla, historia, tamaño)\n\n```\n" + sem.to_string(index=False) + "\n```\n")
print((RES / "CONSOLIDADO.md").read_text(encoding="utf-8"))
