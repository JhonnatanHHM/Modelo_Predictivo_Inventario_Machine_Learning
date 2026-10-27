"""Orquesta el set de pruebas completo (374 series, varias ventanas, varias semillas) con un tope de hora.

Cada corrida es un proceso aparte de run_alfa.py (si una falla, las demás siguen). Antes de lanzar una corrida
estima cuánto tarda y solo la lanza si termina antes del límite; así aprovecha el tiempo sobrante sin pasarse.
Uso: python src/run_completa.py --limite 2026-10-22T08:00   (hora de Bogotá)
"""
import argparse, ctypes, json, os, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "resultados_completa"
TABLA = ROOT / "datos_completa"
PY = sys.executable
BOGOTA = timezone(timedelta(hours=-5))

def ahora():
    return datetime.now(BOGOTA)

def log(msg):
    linea = f"{ahora():%H:%M:%S} | {msg}"
    print(linea, flush=True)
    with open(RES / "orquestador.log", "a", encoding="utf-8") as f:
        f.write(linea + "\n")

def no_dormir(activar=True):
    """Pide a Windows que no suspenda el equipo mientras corre (no cambia ningún ajuste del sistema)."""
    try:
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if activar else 0))
    except Exception:
        pass

ORIGENES_BASE = [1913, 1885, 1857, 1829, 1801, 1773]      # 6 ventanas de 28 días hacia atrás

def trabajos(pasos):
    """(nombre, origen, modelos, semilla, input, hidden, factor_de_tamaño). Prioridad = orden."""
    t = []
    for o in ORIGENES_BASE:
        t.append((f"base_o{o}", o, "base", 1, 56, 32, 0))
    for o in (1913, 1885, 1857):
        t.append((f"tft_o{o}_s1", o, "tft", 1, 56, 32, 1.0))
    t += [
        ("tft_o1913_s2", 1913, "tft", 2, 56, 32, 1.0),
        ("tft_o1913_in112", 1913, "tft", 1, 112, 32, 1.8),
        ("tft_o1913_h64", 1913, "tft", 1, 56, 64, 1.6),
        ("tft_o1885_s2", 1885, "tft", 2, 56, 32, 1.0),
        ("tft_o1857_s2", 1857, "tft", 2, 56, 32, 1.0),
        ("tft_o1913_s3", 1913, "tft", 3, 56, 32, 1.0),
    ]
    return t

def lanzar(nombre, origen, modelos, semilla, inp, hidden, pasos, timeout_s, lr=1e-3):
    carpeta = RES / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, M5_OUT_RES=str(carpeta), M5_OUT_DATA=str(carpeta / "datos"), M5_TABLA_DIR=str(TABLA),
               M5_ORIGIN=str(origen), M5_SEED=str(semilla), M5_INPUT=str(inp), M5_HIDDEN=str(hidden),
               M5_STEPS=str(pasos), M5_LR=str(lr), M5_PATIENCE="6", PYTHONUNBUFFERED="1")
    cmd = [PY, "-u", str(ROOT / "src" / "run_alfa.py"), "--reusar-tabla", "--pasos", str(pasos)]
    cmd += ["--sin-tft"] if modelos == "base" else ["--sin-ets", "--sin-lgbm"]
    t0 = time.time()
    with open(carpeta / "stdout.txt", "w", encoding="utf-8") as so, open(carpeta / "stderr.txt", "w", encoding="utf-8") as se:
        p = subprocess.Popen(cmd, stdout=so, stderr=se, env=env, cwd=str(ROOT))
        try:
            codigo = p.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            p.kill(); codigo = "TIMEOUT"
    ok = codigo == 0 and (carpeta / "metricas_globales.csv").exists()
    return ok, time.time() - t0, codigo

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", required=True, help="hora de Bogotá límite, ej. 2026-10-22T08:00")
    ap.add_argument("--margen-min", type=int, default=20, help="minutos antes del límite en que todo debe haber terminado")
    ap.add_argument("--pasos", type=int, default=1500)
    ap.add_argument("--seg-por-paso", type=float, default=2.8)
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    limite = datetime.fromisoformat(a.limite).replace(tzinfo=BOGOTA) - timedelta(minutes=a.margen_min)
    no_dormir(True)
    log(f"Inicio. Todo debe terminar antes de {limite:%H:%M} (Bogotá). Pasos TFT: {a.pasos}")
    sps = a.seg_por_paso
    pendientes = trabajos(a.pasos)
    hechos, fallidos = [], []

    def estado(actual):
        (RES / "estado.json").write_text(json.dumps({"hora": f"{ahora():%H:%M:%S}", "actual": actual, "hechos": hechos,
                                                      "fallidos": fallidos, "pendientes": [p[0] for p in pendientes],
                                                      "seg_por_paso": round(sps, 2)}, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        while pendientes:
            elegido = None
            for tr in pendientes:                         # el primero en prioridad que alcance a terminar
                nombre, origen, modelos, semilla, inp, hidden, factor = tr
                est = 360 if modelos == "base" else 300 + a.pasos * sps * factor
                if ahora() + timedelta(seconds=est) <= limite:
                    elegido = (tr, est); break
            if not elegido:
                log("Ninguna corrida pendiente cabe antes del límite. Fin."); break
            (nombre, origen, modelos, semilla, inp, hidden, factor), est = elegido
            pendientes.remove((nombre, origen, modelos, semilla, inp, hidden, factor))
            estado(nombre)
            log(f"--> {nombre}: inicio (estimado {est/60:.0f} min)")
            ok, dur, codigo = lanzar(nombre, origen, modelos, semilla, inp, hidden, a.pasos, timeout_s=est * 2)
            log(f"<-- {nombre}: {'OK' if ok else 'FALLÓ (' + str(codigo) + ')'} en {dur/60:.1f} min")
            if ok:
                hechos.append(nombre)
                if modelos == "tft":
                    sps = max(2.4, (dur - 300) / (a.pasos * factor))     # reajusta la estimación con lo medido
            else:
                fallidos.append(nombre)
            estado(None)
    finally:
        no_dormir(False)
        estado("TERMINADO")
        log(f"Terminado. Hechos: {hechos} | Fallidos: {fallidos}")

if __name__ == "__main__":
    main()
