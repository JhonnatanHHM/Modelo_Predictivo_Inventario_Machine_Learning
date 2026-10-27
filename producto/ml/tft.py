"""Temporal Fusion Transformer (NeuralForecast) con salida de cuantiles P10, P50 y P90.
Configuración elegida en las pruebas: historia de 56 días, red más grande (hidden 64), 1.500 pasos, tasa de aprendizaje 1e-3."""
from pathlib import Path

import numpy as np
import pandas as pd

H = 28
INPUT_SIZE = 56
HEADS = 2
LR = 1e-3
BATCH = 32
WINDOWS_BATCH = 256
VAL_CHECK = 50
PACIENCIA = 6
SEMILLA = 1


def entradas(D, origen):
    """Tablas largas para NeuralForecast: entrenamiento (hasta d_origen), variables futuras (28 días siguientes) y variables estáticas."""
    ds = pd.to_datetime(pd.Series(D.fechas)).to_numpy()
    T = len(ds)
    assert origen + H <= T, "El calendario no alcanza para los 28 días siguientes al origen."
    dia = {f"dow_{d}": (D.DOW == d).astype("int8") for d in range(2, 8)}            # día de la semana (wday = 1 es la categoría base)
    por_dia = {"snap": D.SN.astype("int8"), "event_flag": D.EV.astype("int8"), "on_sale": np.isfinite(D.P).astype("int8"),
               "precio_log": np.log1p(np.nan_to_num(D.P, nan=0.0)).astype("float32")}
    comunes = {**dia, "mes_sin": np.sin(2 * np.pi * D.MES / 12).astype("float32"), "mes_cos": np.cos(2 * np.pi * D.MES / 12).astype("float32")}
    futr = ["snap", "event_flag", "on_sale", "precio_log"] + list(dia) + ["mes_sin", "mes_cos"]

    def bloque(k, idx, con_y):
        d = {"unique_id": D.ids[k], "ds": ds[idx]}
        if con_y:
            d["y"] = D.Y[k, idx].astype("float32")
        for c in ("snap", "event_flag", "on_sale", "precio_log"):
            d[c] = por_dia[c][k, idx]
        for c, v in comunes.items():
            d[c] = v[idx]
        return pd.DataFrame(d)

    train = pd.concat([bloque(k, np.arange(D.inicio[k], origen), True) for k in range(len(D.ids))], ignore_index=True)
    futuro = pd.concat([bloque(k, np.arange(origen, origen + H), False) for k in range(len(D.ids))], ignore_index=True)
    est = pd.DataFrame({"unique_id": D.ids, "store_id": D.tienda_nombre, "dept_id": D.depto_nombre})
    stat = pd.get_dummies(est, columns=["store_id", "dept_id"], dtype="int8")
    return train, futuro, stat, futr, [c for c in stat.columns if c != "unique_id"]


def _mapear(pred):
    cols = [c for c in pred.columns if c.startswith("TFT")]

    def buscar(*claves):
        for c in cols:
            if any(k in c for k in claves):
                return c
        raise KeyError(f"No encontré columna con {claves} en {cols}")
    return buscar("lo-80", "q-0.1"), buscar("median", "q-0.5"), buscar("hi-80", "q-0.9")


def entrenar_y_pronosticar(D, origen, pasos=1500, hidden=64, carpeta=None):
    """Entrena con los datos hasta d_origen y pronostica los 28 días siguientes. Devuelve (n_series, 28, 3) con P10, P50 y P90."""
    from neuralforecast import NeuralForecast
    from neuralforecast.losses.pytorch import MQLoss
    from neuralforecast.models import TFT
    train, futuro, stat, futr, stat_cols = entradas(D, origen)
    print(f"TFT: {train.unique_id.nunique()} series, {len(train):,} filas de entrenamiento, {pasos} pasos, hidden {hidden}", flush=True)
    modelo = TFT(h=H, input_size=INPUT_SIZE, hidden_size=hidden, n_head=HEADS, rnn_type="lstm",       # "lstm" en minúscula: neuralforecast 2.0.1 falla con el "LSTM" por defecto
                 loss=MQLoss(level=[80]), futr_exog_list=futr, stat_exog_list=stat_cols, scaler_type="standard", learning_rate=LR,
                 max_steps=pasos, batch_size=BATCH, windows_batch_size=WINDOWS_BATCH, inference_windows_batch_size=WINDOWS_BATCH,
                 val_check_steps=VAL_CHECK, early_stop_patience_steps=PACIENCIA, random_seed=SEMILLA, accelerator="cpu",
                 enable_checkpointing=False, logger=False)
    nf = NeuralForecast(models=[modelo], freq="D")
    nf.fit(df=train, static_df=stat, val_size=H)
    if carpeta:
        Path(carpeta).mkdir(parents=True, exist_ok=True)
        nf.save(path=str(carpeta), overwrite=True, save_dataset=False)
    pred = nf.predict(futr_df=futuro)
    if "unique_id" not in pred.columns:
        pred = pred.reset_index()
    c10, c50, c90 = _mapear(pred)
    out = np.full((len(D.ids), H, 3), np.nan)
    pos = {u: i for i, u in enumerate(D.ids)}
    for uid, g in pred.sort_values(["unique_id", "ds"]).groupby("unique_id"):
        out[pos[uid]] = np.sort(np.clip(g[[c10, c50, c90]].to_numpy(float), 0, None), axis=1)
    assert np.isfinite(out).all(), "El TFT no devolvió el pronóstico de todas las series."
    return out
