"""Configuración central de la prueba alfa. Todo lo que se pueda ajustar está aquí."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # carpeta modelo_predictivo_inventario_alfa
UNIDAD = ROOT.parent                                # carpeta UNIDAD 1
SINTETICO = os.environ.get("M5_SINTETICO", "0") == "1"

if SINTETICO:
    DATA_DIR = ROOT / "datos_sinteticos"
    SERIES_CSV = DATA_DIR / "series_seleccionadas.csv"
else:
    DATA_DIR = Path(os.environ["M5_DATA_DIR"]) if os.environ.get("M5_DATA_DIR") else UNIDAD / "m5-forecasting-accuracy"     # carpeta con los CSV de Kaggle (no se sube al repositorio)
    _series = [UNIDAD / "subconjunto_M5" / "series_seleccionadas.csv", ROOT / "datos_entrada" / "series_seleccionadas.csv"]
    SERIES_CSV = next((p for p in _series if p.exists()), _series[1])

OUT_DATA = Path(os.environ["M5_OUT_DATA"]) if os.environ.get("M5_OUT_DATA") else ROOT / ("datos_procesados_sinteticos" if SINTETICO else "datos_procesados")
OUT_RES = Path(os.environ["M5_OUT_RES"]) if os.environ.get("M5_OUT_RES") else ROOT / ("resultados_sinteticos" if SINTETICO else "resultados")
TABLA_DIR = Path(os.environ["M5_TABLA_DIR"]) if os.environ.get("M5_TABLA_DIR") else OUT_DATA   # donde está la tabla maestra a reutilizar

# ---- Protocolo de la alfa (1 ventana de prueba) ----
LAST_DAY = 1941            # último día con datos públicos (d_1941)
H = 28                     # horizonte en días
ORIGIN = int(os.environ.get("M5_ORIGIN", LAST_DAY - H))   # por defecto 1913: último día que ven los modelos
TEST_START = ORIGIN + 1    # 1914
VAL_START = ORIGIN - H + 1 # 1886 (validación = d_1886..d_1913)
TRAIN_END = ORIGIN - H     # 1885

# ---- Muestra de la alfa ----
N_POR_ESTRATO = 2          # series por tienda x departamento (3 tiendas x 7 deptos x 2 = 42)
SEMILLA = 42
QUANTILES = (0.1, 0.5, 0.9)

# ---- TFT (NeuralForecast) ----
INPUT_SIZE = int(os.environ.get("M5_INPUT", 56))            # días de historia que ve la red
TFT_HIDDEN = int(os.environ.get("M5_HIDDEN", 32))
TFT_HEADS = 2
TFT_STEPS = int(os.environ.get("M5_STEPS", 200))            # pasos de entrenamiento (muy pocos: es una prueba de humo)
TFT_LR = float(os.environ.get("M5_LR", 1e-3))
TFT_BATCH = 32
TFT_WINDOWS_BATCH = 256
TFT_VAL_CHECK = 50
TFT_PATIENCE = int(os.environ.get("M5_PATIENCE", 3))
TFT_SEED = int(os.environ.get("M5_SEED", 1))

# ---- LightGBM ----
LGBM_ORIGIN_STEP = 7       # un origen de entrenamiento cada 7 días
LGBM_ORIGIN_SPAN = 364     # usar los últimos 364 días de orígenes
LGBM_PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50,
                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=SEMILLA)
