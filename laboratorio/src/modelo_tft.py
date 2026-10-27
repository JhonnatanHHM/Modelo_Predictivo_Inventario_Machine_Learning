"""TFT con NeuralForecast (versión mini para la alfa)."""
import numpy as np, pandas as pd
from config import (ORIGIN, TEST_START, H, INPUT_SIZE, TFT_HIDDEN, TFT_HEADS, TFT_STEPS, TFT_LR, TFT_BATCH,
                    TFT_WINDOWS_BATCH, TFT_VAL_CHECK, TFT_PATIENCE, TFT_SEED)
from utils import log

def preparar_entradas(master):
    m = master.copy()
    m["precio_log"] = np.log1p(m["sell_price"].fillna(0)).astype("float32")
    for d in range(2, 8):                                   # día de la semana (wday 1..7); wday=1 es la categoría base
        m[f"dow_{d}"] = (m["wday"] == d).astype("int8")
    m["mes_sin"] = np.sin(2 * np.pi * m["month"] / 12).astype("float32"); m["mes_cos"] = np.cos(2 * np.pi * m["month"] / 12).astype("float32")
    futr = ["snap", "event_flag", "on_sale", "precio_log"] + [f"dow_{d}" for d in range(2, 8)] + ["mes_sin", "mes_cos"]
    est = m.drop_duplicates("unique_id")[["unique_id", "store_id", "dept_id"]]
    stat = pd.get_dummies(est, columns=["store_id", "dept_id"], dtype="int8")
    stat_cols = [c for c in stat.columns if c != "unique_id"]
    base = m[["unique_id", "ds", "y", "dnum"] + futr].copy(); base["y"] = base["y"].astype("float32")
    train = base[base.dnum <= ORIGIN].drop(columns="dnum")
    futr_df = base[base.dnum >= TEST_START].drop(columns=["dnum", "y"])
    return train, futr_df, stat, futr, stat_cols

def _mapear(df):
    cols = [c for c in df.columns if c.startswith("TFT")]
    def buscar(*claves):
        for c in cols:
            if any(k in c for k in claves):
                return c
        raise KeyError(f"No encontré columna con {claves} en {cols}")
    return buscar("lo-80", "q-0.1"), buscar("median", "q-0.5"), buscar("hi-80", "q-0.9")

def pronostico_tft(master, pasos=TFT_STEPS):
    from neuralforecast import NeuralForecast
    from neuralforecast.models import TFT
    from neuralforecast.losses.pytorch import MQLoss
    train, futr_df, stat, futr, stat_cols = preparar_entradas(master)
    log().info(f"TFT: {train.unique_id.nunique()} series, {len(train):,} filas de entrenamiento, entradas futuras {len(futr)}, estáticas {len(stat_cols)}")
    def ajustar(extra):
        modelo = TFT(h=H, input_size=INPUT_SIZE, hidden_size=TFT_HIDDEN, n_head=TFT_HEADS, rnn_type="lstm", loss=MQLoss(level=[80]),
                     futr_exog_list=futr, stat_exog_list=stat_cols, scaler_type="standard",
                     learning_rate=TFT_LR, max_steps=pasos, batch_size=TFT_BATCH, windows_batch_size=TFT_WINDOWS_BATCH,
                     inference_windows_batch_size=TFT_WINDOWS_BATCH, val_check_steps=TFT_VAL_CHECK,
                     early_stop_patience_steps=TFT_PATIENCE, random_seed=TFT_SEED, accelerator="cpu", **extra)
        nf = NeuralForecast(models=[modelo], freq="D")
        nf.fit(df=train, static_df=stat, val_size=H)
        return nf
    try:
        nf = ajustar(dict(enable_checkpointing=False, logger=False))
    except Exception as e:      # algunas versiones no aceptan esos argumentos extra
        log().info(f"TFT: reintento con argumentos mínimos por: {type(e).__name__}: {str(e)[:200]}")
        nf = ajustar({})
    try:
        from config import OUT_RES
        nf.save(path=str(OUT_RES / "modelo_tft"), overwrite=True, save_dataset=False)
    except Exception as e:
        log().info(f"TFT: no se pudo guardar el modelo: {type(e).__name__}: {str(e)[:150]}")
    pred = nf.predict(futr_df=futr_df)
    if "unique_id" not in pred.columns:
        pred = pred.reset_index()
    c10, c50, c90 = _mapear(pred)
    out = pred[["unique_id", "ds", c10, c50, c90]].rename(columns={c10: "p10", c50: "p50", c90: "p90"})
    v = np.sort(np.clip(out[["p10", "p50", "p90"]].to_numpy(float), 0, None), axis=1)
    out[["p10", "p50", "p90"]] = v
    return out
