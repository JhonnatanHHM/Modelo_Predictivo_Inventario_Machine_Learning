# Pronóstico probabilístico de demanda y reposición de inventario

Proyecto de la actividad *Diseño de algoritmos de aprendizaje profundo* (Electiva II, Inteligencia Artificial Avanzada, Tecnológica del Oriente).
Autor: Jhonnatan Hernando Henao Montoya.

El problema: en el comercio minorista, pedir de menos deja estantes vacíos y pedir de más inmoviliza dinero. En lugar de predecir un solo número de ventas,
este proyecto predice un **rango** (P10, P50 y P90) de la demanda de los próximos 28 días y lo convierte en una sugerencia de reposición según el nivel de servicio que se quiera.
Se usa el conjunto público **M5 (Walmart)**: 3 tiendas, 3 categorías, 7 departamentos y 374 series (un producto en una tienda).

## Qué hay en este repositorio

| Carpeta | Qué es |
|---|---|
| [`laboratorio/`](laboratorio/) | Los scripts de los modelos (naive, ETS, LightGBM y Temporal Fusion Transformer), las métricas, la calibración, la simulación de reposición, el conjunto de modelos y la interpretabilidad. Reproduce los resultados del informe. |
| [`producto/`](producto/) | Una aplicación web (Django + PostgreSQL) que usa esos modelos: panel de proyecciones, reposición sugerida, tareas de entrenamiento y un chat acotado al aplicativo. Incluye pruebas automáticas. |

Los datos de M5 **no están en el repositorio** (Kaggle no permite redistribuirlos). Hay que descargarlos con una cuenta propia; las instrucciones están en cada carpeta.

## Cómo se integran el laboratorio y el producto

El laboratorio es donde se **investigó y se midió**; el producto es donde se **usó** lo que funcionó. No se importan entre sí: el producto reimplementa, leyendo de la base de datos, las piezas del laboratorio que ganaron, con los mismos parámetros.

```
 M5 (Kaggle, descargado por cada persona)
        │
        ▼
 laboratorio/  etapa1_tabla_maestra.py ──► datos_completa/tabla_maestra_alfa.parquet + series_alfa.csv
        │                                     │
        │  (modelos, ventanas, métricas)      │  python manage.py cargar_datos
        ▼                                     ▼
 resultados (consolidado_*.csv)        producto/  PostgreSQL: series, ventas, calendario, precios
        │  python manage.py cargar_metricas        │
        └──────────────► pestaña «Modelos»         ├─ ml/diario.py   ◄── LightGBM de cuantiles (modelos_base.py)
                                                   ├─ ml/agregado.py ◄── cuantil de la demanda total (agregado.py)
                                                   ├─ ml/tft.py      ◄── Temporal Fusion Transformer (modelo_tft.py)
                                                   ▼
                                       predicciones y reposición sugerida guardadas en la base
                                       → Proyecciones, Reposición, Chat
```

| Lo que se hizo en el laboratorio | Cómo lo usa el producto |
|---|---|
| Tabla maestra de 374 series (ventas, precio, SNAP, eventos, día de la semana). | `manage.py cargar_datos` la lee junto con el calendario y los precios y la guarda en PostgreSQL (app `catalogo`). |
| LightGBM de cuantiles diarios P10, P50 y P90 (un origen cada 7 días durante 364 días). | `ml/diario.py` aplica la misma receta con datos de la base; comando `generar_predicciones` (botón «Generar predicciones»). |
| Cuantil de la demanda **total** de 28 días y por semana (`agregado.py`): el cuantil 0,9 se lee como «90 % de servicio». | `ml/agregado.py`; de ahí salen el stock objetivo y el pedido sugerido (`pedido = stock objetivo − inventario actual`) de la pestaña Reposición. |
| TFT: se probaron 6 configuraciones (varias con 2 semillas); la mejor fue la de 64 neuronas ocultas, historia de 56 días y 1.500 pasos. | `ml/tft.py` usa esa configuración; comando `entrenar_tft` (botón «Entrenar TFT», cerca de 1 hora en CPU). |
| Métricas de 6 ventanas hacia atrás. | `manage.py cargar_metricas` las guarda y la pestaña **Modelos** las compara. |

Diferencia clave: el laboratorio **evalúa hacia atrás** (pronostica periodos ya conocidos para medir el error); el producto entrena con **todo el histórico** y pronostica el futuro real (del 23/05/2016 al 19/06/2016).
Lo que se quedó solo en el laboratorio: naive, ETS, calibración conformal, simulación de reposición, conjunto de modelos e interpretabilidad del TFT.

**Qué agrega el producto** frente al laboratorio: persistencia en PostgreSQL, un panel web con acceso simple (Proyecciones, Reposición editable, Modelos), tareas largas lanzadas desde la interfaz en procesos aparte, un chat en lenguaje natural acotado al aplicativo (sin APIs de modelos de lenguaje) con historial en la base, temas claro y oscuro, y pruebas automáticas.

## Datos de M5: qué se publica y qué no

- **No se publica ningún archivo de M5** ni tablas derivadas de ventas por serie: ni los CSV de Kaggle, ni la tabla maestra, ni predicciones por serie, ni modelos entrenados, ni volcados de la base (el `.gitignore` los bloquea).
- Sí se publica: código; `laboratorio/datos_entrada/series_seleccionadas.csv` (solo identificadores de las 374 series y su etiqueta de rotación alta/media/baja); informes y tablas de **métricas agregadas** (errores promedio por modelo y ventana, coberturas); y capturas de pantalla del producto, que muestran unas pocas cifras y una gráfica de ejemplo.
- Cualquier persona que quiera reproducir debe descargar M5 con su propia cuenta de Kaggle y aceptar sus reglas (uso académico y no comercial).

## Resultados principales (3 ventanas de 28 días hacia atrás con todos los modelos, 374 series; detalle en `laboratorio/resultados_publicados/`)

| Modelo | MASE medio (menor es mejor) | Cobertura del intervalo 80 % (ideal 0,80) |
|---|---|---|
| Naive (repite la última semana) | 1,093 | 0,844 |
| ETS (suavizado exponencial) | 0,951 | 0,876 |
| LightGBM (cuantiles) | 0,792 | 0,900 |
| TFT (hidden 64) | 0,786 | 0,815 |

Ventanas 1857, 1885 y 1913 (naive, ETS y LightGBM se evaluaron además en otras 3 ventanas). LightGBM y el TFT quedan prácticamente empatados y ambos superan claramente a ETS y al naive.
El conjunto ETS + LightGBM no mejora la exactitud, pero sí reduce el sobrante de inventario necesario para un mismo nivel de servicio en la simulación de reposición.
Limitaciones honestas: un solo periodo de M5, 3 tiendas, sin costos ni plazos de entrega, inventarios simulados en la demostración y un chat evaluado con frases escritas por agentes de IA, no por personas.

## Cómo reproducir todo (resumen)

1. Descargar M5 de Kaggle y dejarlo en `m5-forecasting-accuracy/` (raíz del repositorio).
2. `laboratorio/`: crear el entorno, construir la tabla maestra y correr los modelos ([instrucciones](laboratorio/README.md)).
3. `producto/`: crear la base PostgreSQL, cargar los datos y levantar la aplicación ([instrucciones](producto/README.md)).
4. Pruebas del producto: `python manage.py test --settings=config.settings_test` (no necesita PostgreSQL).

## Licencia y datos

Código propio del proyecto: ver el archivo `LICENSE` en la raíz. Chart.js (incluido en `producto/static/js`) es MIT. Los datos de M5 son de uso académico y no comercial; su licencia es la de Kaggle.
