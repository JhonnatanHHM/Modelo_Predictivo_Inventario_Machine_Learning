# Laboratorio: modelos de pronóstico probabilístico (M5)

Scripts que construyen la tabla de datos, entrenan y evalúan los modelos, y producen los informes de resultados.
Todos los modelos entregan tres cuantiles diarios (P10, P50, P90) para un horizonte de 28 días.

| Modelo | Archivo | Qué es |
|---|---|---|
| Naive | `src/modelos_base.py` | Repite la última semana y obtiene el rango con sus errores pasados. Es la vara de comparación. |
| ETS | `src/modelos_base.py` | Suavizado exponencial (`statsforecast`). |
| LightGBM | `src/modelos_base.py` | Árboles de gradiente con objetivo de cuantil (un modelo por cuantil). |
| TFT | `src/modelo_tft.py` | Temporal Fusion Transformer (`neuralforecast`), la red neuronal del proyecto. |

Otros scripts: `metricas.py` (MASE, pinball, WQL, cobertura), `posproceso.py` (calibración conformal y simulación de reposición), `agregado.py` (cuantil de la demanda total),
`consolidar.py`, `ensamble.py` (promedio ETS + LightGBM), `interpretabilidad_tft.py` e `interp_grupos.py` (qué variables usa el TFT), y los orquestadores `run_alfa.py`, `run_completa.py` y `run_fase2.py`.

## Requisitos
Python 3.10 a 3.12. El TFT se entrena en CPU (unos 54 minutos por corrida con 1.500 pasos en un portátil de 12 hilos); no hace falta GPU.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Datos (no incluidos)
1. Descarga *M5 Forecasting - Accuracy* desde Kaggle con tu cuenta y deja `calendar.csv`, `sell_prices.csv` y `sales_train_evaluation.csv` en `m5-forecasting-accuracy/` en la **raíz del repositorio**
   (o apunta otra carpeta con la variable `M5_DATA_DIR`).
2. `datos_entrada/series_seleccionadas.csv` ya viene en el repositorio: es la lista de las 374 series elegidas (solo identificadores y características, no ventas).

## Pasos
Desde esta carpeta (`laboratorio/`):

```powershell
# 1) Tabla maestra de las 374 series (calendario, precios, SNAP, eventos). Crea datos_completa\tabla_maestra_alfa.parquet y series_alfa.csv (~10 s)
$env:M5_OUT_DATA = "datos_completa"
python src\run_alfa.py --solo-datos --series 1000

# 2) Una corrida de modelos base en la ventana que termina en el día 1913 (naive, ETS y LightGBM; minutos) o con el TFT (≈1 h)
$env:M5_OUT_RES = "resultados_completa\base_o1913"; $env:M5_OUT_DATA = "resultados_completa\base_o1913\datos"; $env:M5_TABLA_DIR = "datos_completa"
python src\run_alfa.py --reusar-tabla --sin-tft

# 3) El set completo de ventanas y semillas (varias horas) y los informes
python src\run_completa.py --limite 2026-10-30T08:00
python src\consolidar.py
python src\posproceso.py
python src\ensamble.py
python src\interpretabilidad_tft.py
```

Variables útiles: `M5_ORIGIN` (último día que ven los modelos), `M5_SEED`, `M5_STEPS`, `M5_HIDDEN`, `M5_INPUT`, `M5_LR`. Todas están en `src/config.py`.

Se verificó que el paso 1 reproduce exactamente la tabla usada en el informe (619.230 filas, 374 series, mismas ventas).

## Resultados publicados
En `resultados_publicados/` están los informes (`CONSOLIDADO.md`, `POSPROCESO.md`, `ENSAMBLE.md`, `INTERPRETABILIDAD_TFT.md`), dos gráficas y las tablas de métricas **agregadas**.
No se publican predicciones por serie ni tablas derivadas de M5 línea a línea.

## Protocolo de evaluación
- Ventanas de 28 días hacia atrás (orígenes 1773, 1801, 1829, 1857, 1885, 1913); el modelo nunca ve nada posterior al origen.
- MASE (error del P50 frente al del naive estacional en el historial), pinball escalada, WQL, cobertura del P10, P90 y del intervalo 80 %.
- Calibración conformal simple con la ventana anterior y simulación de reposición (política de 28 días y política semanal), sin costos.
