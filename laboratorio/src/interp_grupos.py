"""Suma la importancia de las variables que son partes de un mismo concepto (los 6 indicadores de día de la semana, seno y coseno del mes, precio y oferta)
y añade el resultado a INTERPRETABILIDAD_TFT.md. Lee los CSV que dejó interpretabilidad_tft.py."""
import numpy as np, pandas as pd
from pathlib import Path
RES = Path(__file__).resolve().parents[1] / "resultados_completa"
GRUPOS = {"Día de la semana (6 indicadores)": lambda c: c.startswith("dow_"), "Mes del año (seno + coseno)": lambda c: c.startswith("mes_"),
          "Precio y oferta": lambda c: c in ("precio_log", "on_sale"), "Días SNAP": lambda c: c == "snap", "Evento del calendario": lambda c: c == "event_flag"}
filas = {}
for m in ("tft_o1913_h64", "tft_o1913_s1"):
    f = pd.read_csv(RES / f"interp_{m}_futuro.csv", index_col=0).iloc[:, 0]
    filas[m] = {g: f[[c for c in f.index if fn(c)]].sum() for g, fn in GRUPOS.items()}
df = pd.DataFrame(filas).sort_values("tft_o1913_h64", ascending=False).round(3)
a = pd.read_csv(RES / "interp_tft_o1913_h64_atencion.csv", index_col=0).to_numpy().mean(axis=0)
semanas = [a[i:i + 7].sum() for i in range(0, 84, 7)]
txt = ("\n## Importancia del futuro agrupada por concepto (suma de las variables que forman cada concepto)\n\n```\n" + df.to_string() + "\n```\n\n"
       "Los seis indicadores de día de la semana son un solo concepto codificado en columnas excluyentes; por eso el peso individual salta de un indicador a otro entre modelos (lunes en uno, martes en otro) "
       "y solo tiene sentido leerlos juntos. Atención sumada por bloques de 7 posiciones (de la más antigua a la más reciente): " + ", ".join(f"{x:.3f}" for x in semanas) +
       ". La atención decrece de forma casi monótona desde el inicio de la ventana; no se ven picos semanales claros, así que esta gráfica no demuestra por sí sola que la red use la estacionalidad semanal.\n")
p = RES / "INTERPRETABILIDAD_TFT.md"
s = p.read_text(encoding="utf-8")
if "agrupada por concepto" not in s:
    p.write_text(s + txt, encoding="utf-8")
print(txt)
