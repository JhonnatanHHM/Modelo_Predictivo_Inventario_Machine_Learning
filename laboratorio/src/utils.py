import json, logging, sys, time, platform, os
from contextlib import contextmanager
from pathlib import Path
import numpy as np
import pandas as pd
from config import OUT_DATA, OUT_RES

TIEMPOS = {}

def preparar_log(nombre="alfa"):
    OUT_RES.mkdir(parents=True, exist_ok=True)
    ruta = OUT_RES / f"log_{nombre}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    logger = logging.getLogger("alfa")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(ruta, encoding="utf-8")):
        h.setFormatter(fmt); logger.addHandler(h)
    logger.info(f"Log: {ruta}")
    return logger

def log():
    return logging.getLogger("alfa")

@contextmanager
def cronometro(etapa):
    t0 = time.perf_counter()
    log().info(f"--> {etapa}: inicio")
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        TIEMPOS[etapa] = round(dt, 1)
        log().info(f"<-- {etapa}: {dt:.1f} s")

def info_equipo():
    d = {"python": sys.version.split()[0], "so": platform.platform(), "procesador": platform.processor(),
         "nucleos_logicos": os.cpu_count()}
    for lib in ("numpy", "pandas", "torch", "lightgbm", "statsforecast", "neuralforecast", "pyarrow", "matplotlib"):
        try:
            m = __import__(lib); d[lib] = getattr(m, "__version__", "?")
        except Exception:
            d[lib] = "NO INSTALADO"
    try:
        import torch
        d["torch_hilos"] = torch.get_num_threads(); d["cuda"] = bool(torch.cuda.is_available())
    except Exception:
        pass
    return d

def guardar_tabla(df, nombre):
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow  # noqa
        ruta = OUT_DATA / f"{nombre}.parquet"; df.to_parquet(ruta, index=False)
    except ImportError:
        ruta = OUT_DATA / f"{nombre}.csv.gz"; df.to_csv(ruta, index=False)
    return ruta

def leer_tabla(nombre):
    p = OUT_DATA / f"{nombre}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return pd.read_csv(OUT_DATA / f"{nombre}.csv.gz", parse_dates=["ds"])

def guardar_json(obj, ruta):
    Path(ruta).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
