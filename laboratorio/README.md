# Laboratorio: LightGBM de cuantiles para el pronóstico probabilístico de demanda (M5)

Scripts que construyen la tabla de datos, entrenan y evalúan el modelo y reproducen los experimentos del informe.
El modelo entrega tres cuantiles diarios (P10, P50, P90) para un horizonte de 28 días, con una familia de árboles de gradiente (**LightGBM**, un modelo por cuantil).
La red neuronal (Temporal Fusion Transformer) que se probó en la primera versión del proyecto **ya no forma parte del repositorio**: LightGBM la igualó en exactitud (MASE 0,792 frente a 0,786) con unas 15 veces menos cómputo,
y en esta versión se mejoró con variables nuevas, ajuste de hiperparámetros y más historia de entrenamiento.

| Pieza | Archivo | Qué es |
|---|---|---|
| Modelo final y biblioteca | `src/lab_lgbm.py` | Construye las 38 variables (18 de la primera versión y 20 nuevas), las tablas de entrenamiento, validación y prueba, ajusta los tres cuantiles con parada temprana y evalúa. |
| Comparaciones | `src/modelos_base.py` | Naive estacional, ETS (`statsforecast`) y LightGBM de la primera versión (18 variables, parámetros fijos). |
| Métricas | `src/metricas.py` | MASE, pinball escalada, WQL, cobertura del P10, P90 y del intervalo 80 %, sesgo. |
| Datos | `src/etapa1_tabla_maestra.py` | Tabla maestra de las 374 series (calendario, precios, SNAP, eventos). |

## Experimentos (cada script escribe en `resultados/`, que no se sube; las tablas agregadas están en `resultados_publicados/`)

| Script | Qué responde |
|---|---|
| `exp1_variables.py` | ¿Ayudan las variables nuevas (intermitencia, días de la semana, tendencia, precio y calendario)? Ablación por grupos. |
| `exp2_ajuste.py <base\|todas_nuevas> <pruebas> [minutos]` | Ajuste de hiperparámetros con Optuna (TPE y poda) sobre 4 ventanas de validación. |
| `exp2c_barrido.py` | Barrido dirigido de `min_child_samples` (con 728 días de historia). |
| `exp3_origenes.py` | ¿Cuánta historia y cada cuántos días conviene generar orígenes de entrenamiento? |
| `exp4_final.py` | Evaluación final, **una sola vez**, en las ventanas de prueba (orígenes 1885 y 1913): comparación contra la primera versión, intervalos de confianza por remuestreo de series, métricas y brechas por segmento, cruce de cuantiles e importancia de variables (SHAP nativo de LightGBM). |

## Requisitos
Python 3.10 a 3.12, solo CPU (el modelo final entrena en pocos minutos).

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
# 1) Tabla maestra de las 374 series. Crea datos_completa\tabla_maestra_alfa.parquet y series_alfa.csv (~10 s)
$env:M5_OUT_DATA = "datos_completa"
python src\run_alfa.py --solo-datos --series 1000

# 2) Experimentos (los parámetros ajustados quedan en resultados\exp2_mejor_todas_nuevas.json; copia publicada en resultados_publicados\)
python src\exp1_variables.py
python src\exp2_ajuste.py todas_nuevas 40 240
python src\exp3_origenes.py
python src\exp4_final.py

# 3) Opcional: comparación con naive y ETS en una ventana (minutos)
$env:M5_OUT_RES = "resultados\base_o1913"; $env:M5_OUT_DATA = "resultados\base_o1913\datos"; $env:M5_TABLA_DIR = "datos_completa"
python src\run_alfa.py --reusar-tabla
```

Nota: `exp4_final.py` lee los mejores parámetros de `resultados\exp2_mejor_todas_nuevas.json`; si no corres el paso 2, copia ese archivo desde `resultados_publicados\` a `resultados\`.
`lab_lgbm.py` busca la tabla maestra en `datos_completa/` (variable `M5_TABLA_DIR` para cambiarla).

## Protocolo de evaluación
- Tres conjuntos separados en el tiempo. **Entrenamiento:** orígenes cada 7 días sobre 728 días que terminan 56 días antes del origen. **Validación** (parada temprana y ajuste): los 28 días anteriores al origen,
  en las ventanas 1773, 1801, 1829 y 1857. **Prueba:** ventanas de 28 días con orígenes 1885 y 1913, que se usan una sola vez.
- El modelo nunca ve nada posterior al origen. MASE (error del P50 frente al del naive estacional de rezago 7), pinball escalada, WQL, cobertura y sesgo.
- Diferencias entre versiones con remuestreo de series (5.000 veces) y métricas por tienda, rotación, categoría y departamento (equidad).

## Resultados (ventanas de prueba, promedio de 2; detalle en `resultados_publicados/`)

| Modelo | MASE | Pinball escalada | WQL | Cobertura 80 % |
|---|---|---|---|---|
| LightGBM primera versión (18 variables, parámetros fijos, 364 días) | 0,8034 | 0,2734 | 1,5486 | 0,898 |
| **LightGBM final (38 variables, ajustado, 728 días)** | **0,7981** | **0,2703** | **1,5292** | 0,866 |

La mejora es pequeña pero estadísticamente distinguible (MASE −0,0053, IC95 −0,0094 a −0,0016; pinball escalada −0,0031, IC95 −0,0045 a −0,0018).
Limitaciones: en 10 % a 16 % de las filas los cuantiles crudos se cruzan (se corrigen ordenándolos), las brechas entre segmentos se reducen un poco pero no se cierran (peores: tienda WI_2, rotación media, departamento FOODS_3),
el sesgo del P50 sigue siendo negativo por la demanda intermitente (60,7 % de los días sin ventas) y solo hay un periodo de M5 y 3 tiendas.
