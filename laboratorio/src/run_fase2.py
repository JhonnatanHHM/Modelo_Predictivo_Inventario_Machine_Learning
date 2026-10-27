"""Fase 2: variantes del TFT (cribado en la ventana 1913) y luego replica la mejor en otras ventanas y semillas.
Reutiliza run_completa.lanzar. Respeta un límite de hora de Bogotá y solo lanza lo que alcance a terminar.
Uso: python src/run_fase2.py --limite 2026-10-23T07:30
"""
import argparse, json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import run_completa as RC
from run_completa import lanzar, log, ahora, BOGOTA, RES

# nombre: (pasos, input, hidden, lr, factor_de_tiempo_respecto_a_la_configuración_base)
VARIANTES = {
    "lr3e3":       (1500, 56, 32, 3e-3, 1.0),
    "p3000":       (3000, 56, 32, 1e-3, 1.0),
    "p3000_lr3e3": (3000, 56, 32, 3e-3, 1.0),
    "in112":       (1500, 112, 32, 1e-3, 1.8),
    "h64":         (1500, 56, 64, 1e-3, 1.6),
}
BASE = (1500, 56, 32, 1e-3, 1.0)     # configuración de la fase 1 (nombre de corrida: tft_o<ventana>_s1 / _s2)

def nombre_corrida(variante, origen, semilla):
    if variante == "base":
        return f"tft_o{origen}_s{semilla}"
    return f"tft_o{origen}_{variante}" + ("" if semilla == 1 else f"_sem{semilla}")

def mase(nombre):
    f = RES / nombre / "metricas_globales.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f, index_col=0)
    return float(d.loc["tft", "MASE_medio"]) if "tft" in d.index else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", required=True)
    ap.add_argument("--margen-min", type=int, default=20)
    ap.add_argument("--seg-por-paso", type=float, default=2.3)
    a = ap.parse_args()
    limite = datetime.fromisoformat(a.limite).replace(tzinfo=BOGOTA) - timedelta(minutes=a.margen_min)
    RC.no_dormir(True)
    sps = a.seg_por_paso
    log(f"FASE 2. Todo debe terminar antes de {limite:%d %H:%M} (Bogotá)")
    hechos, fallidos = [], []

    def ejecutar(variante, origen, semilla):
        nonlocal sps
        pasos, inp, hid, lr, fac = BASE if variante == "base" else VARIANTES[variante]
        nombre = nombre_corrida(variante, origen, semilla)
        if (RES / nombre / "metricas_globales.csv").exists():
            return True                                          # ya existe (de la fase 1 o de una ejecución anterior)
        est = 300 + pasos * sps * fac
        if ahora() + timedelta(seconds=est) > limite:
            log(f"(omitida {nombre}: no cabe, estimado {est/60:.0f} min)"); return None
        log(f"--> {nombre}: inicio (estimado {est/60:.0f} min)")
        ok, dur, cod = lanzar(nombre, origen, "tft", semilla, inp, hid, pasos, timeout_s=est * 2, lr=lr)
        log(f"<-- {nombre}: {'OK' if ok else 'FALLÓ (' + str(cod) + ')'} en {dur/60:.1f} min | MASE={mase(nombre)}")
        (hechos if ok else fallidos).append(nombre)
        if ok:
            sps = max(2.0, (dur - 300) / (pasos * fac))
        (RES / "estado.json").write_text(json.dumps({"hora": f"{ahora():%H:%M:%S}", "fase": 2, "hechos": hechos, "fallidos": fallidos,
                                                      "seg_por_paso": round(sps, 2)}, ensure_ascii=False), encoding="utf-8")
        return ok

    try:
        # ---- Fase 2A: cribado de variantes en la ventana 1913 (semilla 1)
        for v in ["lr3e3", "p3000", "p3000_lr3e3", "in112", "h64"]:
            ejecutar(v, 1913, 1)
        # ---- Fase 2B: la mejor variante (incluida la base) se replica en otras ventanas y semillas
        candidatos = {"base": [m for m in (mase("tft_o1913_s1"), mase("tft_o1913_s2")) if m is not None]}
        for v in VARIANTES:
            m = mase(nombre_corrida(v, 1913, 1))
            if m is not None:
                candidatos[v] = [m]
        medias = {k: sum(x) / len(x) for k, x in candidatos.items() if x}
        log("Cribado (MASE medio en la ventana 1913): " + ", ".join(f"{k}={v:.4f}" for k, v in sorted(medias.items(), key=lambda t: t[1])))
        mejor = min(medias, key=medias.get)
        log(f"Mejor variante: {mejor}. Se replica en otras ventanas y semillas.")
        for origen, semilla in [(1885, 1), (1857, 1), (1913, 2), (1829, 1), (1885, 2), (1857, 2), (1913, 3)]:
            if mejor == "base" and (origen, semilla) in [(1885, 1), (1857, 1), (1913, 2), (1885, 2), (1857, 2)]:
                continue                                         # ya existen de la fase 1
            ejecutar(mejor, origen, semilla)
    finally:
        RC.no_dormir(False)
        (RES / "estado.json").write_text(json.dumps({"hora": f"{ahora():%H:%M:%S}", "actual": "TERMINADO", "hechos": hechos, "fallidos": fallidos}, ensure_ascii=False), encoding="utf-8")
        log(f"FASE 2 terminada. Hechos: {hechos} | Fallidos: {fallidos}")

if __name__ == "__main__":
    main()
