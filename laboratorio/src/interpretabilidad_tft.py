"""Interpretabilidad del TFT: importancia de variables (pesos de selección de variables, VSN) y atención temporal, a partir de modelos ya entrenados.
No entrena nada. El modelo guarda estos pesos del último lote de cada predicción, así que se predice por bloques de series y se promedia.
Uso: python src/interpretabilidad_tft.py [carpeta_modelo ...]   (por defecto tft_o1913_h64 y tft_o1913_s1)  -> resultados_completa/INTERPRETABILIDAD_TFT.md, interp_*.csv, g4_interpretabilidad_tft.png
"""
import os, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "resultados_completa"
os.environ.setdefault("M5_ORIGIN", "1913")
os.environ["M5_TABLA_DIR"] = str(ROOT / "datos_completa")
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")
import modelo_tft as MT                                       # noqa: E402

BLOQUE = 60                                                   # series por bloque (menos que windows_batch_size: un solo lote por bloque)


def etiqueta(c):
    nombres = {"snap": "Días SNAP", "event_flag": "Evento del calendario", "on_sale": "Producto en oferta", "precio_log": "Precio (log)", "mes_sin": "Mes (seno)", "mes_cos": "Mes (coseno)", "observed_target": "Ventas pasadas (y)"}
    if c in nombres:
        return nombres[c]
    if c.startswith("dow_"):
        return f"Día de la semana = {['', '', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'][int(c[4:])]}"
    if c.startswith("store_id_"):
        return "Tienda " + c[9:]
    if c.startswith("dept_id_"):
        return "Departamento " + c[8:]
    return c


def analizar(carpeta):
    from neuralforecast import NeuralForecast
    master = pd.read_parquet(ROOT / "datos_completa" / "tabla_maestra_alfa.parquet")
    train, futr_df, stat, futr, stat_cols = MT.preparar_entradas(master)
    nf = NeuralForecast.load(path=str(RES / carpeta / "modelo_tft"))
    modelo = nf.models[0]
    ids = sorted(train.unique_id.unique())
    pasado, futuro, estatico, atencion, pesos = [], [], [], [], []
    for i in range(0, len(ids), BLOQUE):
        sub = ids[i:i + BLOQUE]
        nf.predict(df=train[train.unique_id.isin(sub)], static_df=stat[stat.unique_id.isin(sub)], futr_df=futr_df[futr_df.unique_id.isin(sub)])
        imp = modelo.feature_importances()
        pasado.append(imp["Past variable importance over time"]); futuro.append(imp["Future variable importance over time"])
        estatico.append(imp["Static covariates"]); atencion.append(modelo.attention_weights()); pesos.append(len(sub))
    w = np.array(pesos, float) / sum(pesos)
    prom = lambda dfs: sum(d.reindex_like(dfs[0]) * wi for d, wi in zip(dfs, w))
    return {"pasado": prom(pasado), "futuro": prom(futuro), "estatico": prom(estatico), "atencion": sum(a * wi for a, wi in zip(atencion, w)),
            "variacion_bloques_futuro": pd.concat([d.mean(axis=0) for d in futuro], axis=1).std(axis=1)}


def main():
    carpetas = sys.argv[1:] or ["tft_o1913_h64", "tft_o1913_s1"]
    salida, md = {}, []
    for c in carpetas:
        print("analizando", c, flush=True)
        salida[c] = r = analizar(c)
        pas = r["pasado"].mean(axis=0).sort_values(ascending=False)
        fut = r["futuro"].mean(axis=0).sort_values(ascending=False)
        est = r["estatico"]["importance"].sort_values(ascending=False)
        pd.DataFrame({"importancia_pasado": pas}).to_csv(RES / f"interp_{c}_pasado.csv"); pd.DataFrame({"importancia_futuro": fut}).to_csv(RES / f"interp_{c}_futuro.csv"); est.to_csv(RES / f"interp_{c}_estaticas.csv")
        pd.DataFrame(np.atleast_2d(r["atencion"])).to_csv(RES / f"interp_{c}_atencion.csv")
    ref = carpetas[0]
    r = salida[ref]
    fut_prom = {c: salida[c]["futuro"].mean(axis=0) for c in carpetas}
    pas_prom = {c: salida[c]["pasado"].mean(axis=0) for c in carpetas}

    # --- gráfica
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    f = fut_prom[ref].sort_values(); ax[0, 0].barh([etiqueta(i) for i in f.index], f.values, color="#FF5E46"); ax[0, 0].set_title("Variables conocidas del futuro (importancia relativa)")
    p = pas_prom[ref].sort_values(); ax[0, 1].barh([etiqueta(i) for i in p.index], p.values, color="#5C423E"); ax[0, 1].set_title("Variables del pasado (incluye las ventas observadas)")
    e = r["estatico"]["importance"].sort_values(); ax[1, 0].barh([etiqueta(i) for i in e.index], e.values, color="#C9958D"); ax[1, 0].set_title("Variables estáticas (tienda y departamento)")
    a = r["atencion"]
    if a.ndim > 1:
        a = a.mean(axis=0)
    ax[1, 1].plot(np.arange(len(a)), a, color="#AF4C3C"); ax[1, 1].set_title("Atención por posición de tiempo (promedio)"); ax[1, 1].set_xlabel("posición en la ventana (historia + horizonte)")
    for x in ax.ravel(): x.grid(alpha=.3)
    fig.suptitle(f"Interpretabilidad del TFT ({ref})"); fig.tight_layout(); fig.savefig(RES / "g4_interpretabilidad_tft.png", dpi=130)

    # --- informe
    def md_df(df): return "```\n" + df.to_string() + "\n```\n\n"
    with open(RES / "INTERPRETABILIDAD_TFT.md", "w", encoding="utf-8") as fh:
        fh.write("# Interpretabilidad del TFT\n\n")
        fh.write("Qué mide: el TFT tiene un mecanismo de *selección de variables* (VSN) que asigna a cada variable un peso entre 0 y 1 que suma 1 en cada bloque; "
                 "indica cuánto se apoyó la red en cada variable, **no** cuánto causa cada variable en las ventas ni cuánto empeoraría el error sin ella. "
                 "Se promedia sobre las 374 series (bloques de 60) y sobre el tiempo. Modelos analizados: " + ", ".join(carpetas) + ".\n\n")
        for nombre, d in (("Variables conocidas del futuro", fut_prom), ("Variables del pasado", pas_prom)):
            df = pd.DataFrame({c: d[c] for c in carpetas}); df.index = [etiqueta(i) for i in df.index]
            df = df.sort_values(carpetas[0], ascending=False).round(4)
            fh.write(f"## {nombre}\n\n" + md_df(df))
        est = pd.DataFrame({c: salida[c]["estatico"]["importance"] for c in carpetas}); est.index = [etiqueta(i) for i in est.index]
        fh.write("## Variables estáticas\n\n" + md_df(est.sort_values(carpetas[0], ascending=False).round(4)))
        a = r["atencion"]; a = a.mean(axis=0) if a.ndim > 1 else a
        top = np.argsort(a)[::-1][:8]
        fh.write("## Atención temporal\n\n"
                 f"El vector de atención tiene {len(a)} posiciones (historia de entrada + horizonte). Las 8 posiciones con más atención (0 = más antigua): "
                 + ", ".join(f"{int(i)} ({a[i]:.3f})" for i in top) + ". Si las posiciones altas coinciden con múltiplos de 7 contados desde el final de la historia, la red está usando la estacionalidad semanal.\n\n")
        fh.write("Estabilidad entre bloques de series (desviación estándar de la importancia del futuro): máxima " + f"{salida[ref]['variacion_bloques_futuro'].max():.4f}.\n")
    print((RES / "INTERPRETABILIDAD_TFT.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
