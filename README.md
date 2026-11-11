# Pronóstico probabilístico de demanda y reposición de inventario con LightGBM

Proyecto de la asignatura Electiva II (Inteligencia Artificial Avanzada), Tecnológica del Oriente. Autor: Jhonnatan Hernando Henao Montoya.

El problema: en el comercio minorista, pedir de menos deja estantes vacíos y pedir de más inmoviliza dinero. En lugar de predecir un solo número de ventas,
este proyecto predice un **rango** (P10, P50 y P90) de la demanda de los próximos 28 días y lo convierte en una sugerencia de reposición según el nivel de servicio que se quiera.
Se usa el conjunto público **M5 (Walmart)**: 3 tiendas, 3 categorías, 7 departamentos y 374 series (un producto en una tienda).

## Un solo modelo: LightGBM

La primera versión del proyecto (actividad de aprendizaje profundo) comparó naive, ETS, LightGBM y una red neuronal (Temporal Fusion Transformer, TFT).
LightGBM empató con el TFT (MASE 0,792 frente a 0,786) con unas 15 veces menos cómputo, así que **la red neuronal se retiró del repositorio** y el proyecto se concentró en mejorar LightGBM:

| Mejora | Qué se hizo |
|---|---|
| Variables | De 18 a 38: intermitencia (días desde la última venta, frecuencia de venta), mismos días de la semana anteriores, tendencia de la serie, la tienda y el grupo, precio y calendario. |
| Hiperparámetros | Ajuste con Optuna (TPE y poda) sobre 4 ventanas de validación: tasa de aprendizaje baja, mucha regularización y hojas con muchas filas. |
| Historia | Orígenes de entrenamiento cada 7 días durante 728 días (antes 364). |
| Protocolo | Entrenamiento, validación y prueba separados en el tiempo; las ventanas de prueba (orígenes 1885 y 1913) se usaron una sola vez. |
| Equidad | Métricas por tienda, rotación, categoría y departamento, antes y después. |

## Qué hay en este repositorio

| Carpeta | Qué es |
|---|---|
| [`laboratorio/`](laboratorio/) | El modelo LightGBM final, sus experimentos (variables, ajuste, historia, evaluación final), las comparaciones con naive y ETS y las métricas. Reproduce los resultados del informe. |
| [`producto/`](producto/) | Una aplicación web (Django + PostgreSQL) que usa ese modelo: panel de proyecciones, reposición sugerida, tarea de generación de predicciones y un chat acotado al aplicativo. Incluye pruebas automáticas. |

Los datos de M5 **no están en el repositorio** (Kaggle no permite redistribuirlos). Hay que descargarlos con una cuenta propia; las instrucciones están en cada carpeta.

## Cómo se integran el laboratorio y el producto

El laboratorio es donde se **investigó y se midió**; el producto es donde se **usó** lo que funcionó. No se importan entre sí: el producto reimplementa, leyendo de la base de datos, el modelo final del laboratorio con los mismos parámetros
(se comprobó que produce exactamente las mismas variables y las mismas métricas: MASE 0,8282 en la ventana de prueba 1913).

```
 M5 (Kaggle, descargado por cada persona)
        │
        ▼
 laboratorio/  etapa1_tabla_maestra.py ──► datos_completa/tabla_maestra_alfa.parquet + series_alfa.csv
        │                                     │
        │  (experimentos, métricas)           │  python manage.py cargar_datos
        ▼                                     ▼
 resultados_publicados/ (tablas agregadas)   producto/  PostgreSQL: series, ventas, calendario, precios
        │  python manage.py cargar_metricas        │
        └──────────────► pestaña «Modelos»         ├─ ml/diario.py   ◄── LightGBM de cuantiles diarios (lab_lgbm.py)
                                                   ├─ ml/agregado.py ◄── LightGBM del cuantil de la demanda total
                                                   ▼
                                       predicciones y reposición sugerida guardadas en la base
                                       → Proyecciones, Reposición, Chat
```

| Lo que se hizo en el laboratorio | Cómo lo usa el producto |
|---|---|
| Tabla maestra de 374 series (ventas, precio, SNAP, eventos, día de la semana). | `manage.py cargar_datos` la lee junto con el calendario y los precios y la guarda en PostgreSQL (app `catalogo`). |
| LightGBM de cuantiles diarios P10, P50 y P90: 38 variables, parámetros ajustados, orígenes cada 7 días durante 728 días. | `ml/diario.py` aplica la misma receta con datos de la base; comando `generar_predicciones` (botón «Generar predicciones»). |
| Cuantil de la demanda **total** de 28 días y por semana: el cuantil 0,9 se lee como «90 % de servicio». | `ml/agregado.py`; de ahí salen el stock objetivo y el pedido sugerido (`pedido = stock objetivo − inventario actual`) de la pestaña Reposición. |
| Evaluación final en dos ventanas de prueba, comparada con la primera versión. | `manage.py cargar_metricas` la guarda y la pestaña **Modelos** la muestra. |

Diferencia clave: el laboratorio **evalúa hacia atrás** (pronostica periodos ya conocidos para medir el error); el producto entrena con **todo el histórico** y pronostica el futuro real (del 23/05/2016 al 19/06/2016).

**Qué agrega el producto** frente al laboratorio: persistencia en PostgreSQL, un panel web con acceso simple (Proyecciones, Reposición editable, Modelos), una tarea larga lanzada desde la interfaz en un proceso aparte,
un chat en lenguaje natural acotado al aplicativo (sin APIs de modelos de lenguaje) con historial en la base, temas claro y oscuro, y pruebas automáticas.

## Datos de M5: qué se publica y qué no

- **No se publica ningún archivo de M5** ni tablas derivadas de ventas por serie: ni los CSV de Kaggle, ni la tabla maestra, ni predicciones por serie, ni modelos entrenados, ni volcados de la base (el `.gitignore` los bloquea).
- Sí se publica: código; `laboratorio/datos_entrada/series_seleccionadas.csv` (solo identificadores de las 374 series y su etiqueta de rotación alta/media/baja); tablas de **métricas agregadas** (errores promedio por modelo, ventana y segmento, coberturas, importancia de variables); y capturas de pantalla del producto.
- Cualquier persona que quiera reproducir debe descargar M5 con su propia cuenta de Kaggle y aceptar sus reglas (uso académico y no comercial).

## Resultados principales (ventanas de prueba, promedio de 2 ventanas de 28 días, 374 series; detalle en `laboratorio/resultados_publicados/`)

| Modelo | MASE (menor es mejor) | Pinball escalada | WQL | Cobertura del intervalo 80 % (ideal 0,80) |
|---|---|---|---|---|
| LightGBM primera versión (18 variables, parámetros fijos, 364 días) | 0,8034 | 0,2734 | 1,5486 | 0,898 |
| **LightGBM final (38 variables, ajustado, 728 días)** | **0,7981** | **0,2703** | **1,5292** | 0,866 |

La mejora es pequeña pero estadísticamente distinguible: diferencia pareada por serie en MASE −0,0053 (IC 95 % −0,0094 a −0,0016) y en pinball escalada −0,0031 (IC 95 % −0,0045 a −0,0018).
Referencia de la primera versión (3 ventanas hacia atrás, otras ventanas): naive 1,093, ETS 0,951, LightGBM 0,792 y TFT 0,786.

Limitaciones honestas:
- En 10 % a 16 % de las filas los cuantiles crudos del modelo final se cruzan (se corrige ordenándolos).
- Las brechas entre segmentos bajan un poco pero no se cierran; los peor atendidos son la tienda WI_2, la rotación media y el departamento FOODS_3.
- El sesgo del P50 sigue siendo negativo por la demanda intermitente (60,7 % de los días sin ventas) y la mejora en MASE se da en solo el 39 % de las series.
- Un solo periodo de M5, 3 tiendas, sin costos ni plazos de entrega, inventarios simulados en la demostración y un chat evaluado con frases escritas por agentes de IA, no por personas.

## Cómo reproducir todo (resumen)

1. Descargar M5 de Kaggle y dejarlo en `m5-forecasting-accuracy/` (raíz del repositorio).
2. `laboratorio/`: crear el entorno, construir la tabla maestra y correr los experimentos ([instrucciones](laboratorio/README.md)).
3. `producto/`: crear la base PostgreSQL, cargar los datos y levantar la aplicación ([instrucciones](producto/README.md)).
4. Pruebas del producto: `python manage.py test --settings=config.settings_test` (no necesita PostgreSQL).

## Licencia y datos

Código propio del proyecto: ver el archivo de licencia (si existe) en la raíz. Chart.js (incluido en `producto/static/js`) es MIT. Los datos de M5 son de uso académico y no comercial; su licencia es la de Kaggle.
