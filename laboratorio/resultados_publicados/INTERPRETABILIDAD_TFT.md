# Interpretabilidad del TFT

Qué mide: el TFT tiene un mecanismo de *selección de variables* (VSN) que asigna a cada variable un peso entre 0 y 1 que suma 1 en cada bloque; indica cuánto se apoyó la red en cada variable, **no** cuánto causa cada variable en las ventas ni cuánto empeoraría el error sin ella. Se promedia sobre las 374 series (bloques de 60) y sobre el tiempo. Modelos analizados: tft_o1913_h64, tft_o1913_s1.

## Variables conocidas del futuro

```
                        tft_o1913_h64  tft_o1913_s1
Día de la semana = lun         0.4096        0.0248
Día de la semana = mar         0.1089        0.4239
Día de la semana = mié         0.0951        0.0740
Precio (log)                   0.0950        0.0398
Mes (seno)                     0.0653        0.0531
Día de la semana = sáb         0.0456        0.0309
Día de la semana = jue         0.0423        0.0510
Evento del calendario          0.0347        0.0197
Día de la semana = vie         0.0317        0.0389
Días SNAP                      0.0314        0.0439
Producto en oferta             0.0218        0.1581
Mes (coseno)                   0.0187        0.0420
```

## Variables del pasado

```
                        tft_o1913_h64  tft_o1913_s1
Ventas pasadas (y)             0.8706        0.7597
Mes (coseno)                   0.0116        0.0340
Mes (seno)                     0.0115        0.0170
Precio (log)                   0.0114        0.0208
Producto en oferta             0.0112        0.0193
Día de la semana = sáb         0.0111        0.0188
Día de la semana = lun         0.0110        0.0201
Días SNAP                      0.0107        0.0205
Día de la semana = vie         0.0105        0.0169
Día de la semana = mar         0.0103        0.0162
Evento del calendario          0.0103        0.0160
Día de la semana = mié         0.0102        0.0198
Día de la semana = jue         0.0097        0.0209
```

## Variables estáticas

```
                          tft_o1913_h64  tft_o1913_s1
Departamento FOODS_3             0.1567        0.1838
Departamento HOUSEHOLD_1         0.1343        0.0903
Departamento HOUSEHOLD_2         0.1287        0.1039
Departamento FOODS_2             0.1253        0.1443
Departamento HOBBIES_2           0.1216        0.1803
Tienda WI_2                      0.1190        0.0477
Departamento FOODS_1             0.0794        0.0404
Tienda CA_1                      0.0562        0.0604
Tienda TX_2                      0.0446        0.0644
Departamento HOBBIES_1           0.0343        0.0845
```

## Atención temporal

El vector de atención tiene 84 posiciones (historia de entrada + horizonte). Las 8 posiciones con más atención (0 = más antigua): 0 (0.058), 1 (0.044), 2 (0.041), 3 (0.038), 4 (0.036), 5 (0.033), 6 (0.031), 7 (0.027). Si las posiciones altas coinciden con múltiplos de 7 contados desde el final de la historia, la red está usando la estacionalidad semanal.

Estabilidad entre bloques de series (desviación estándar de la importancia del futuro): máxima 0.0412.

## Importancia del futuro agrupada por concepto (suma de las variables que forman cada concepto)

```
                                  tft_o1913_h64  tft_o1913_s1
Día de la semana (6 indicadores)          0.733         0.643
Precio y oferta                           0.117         0.198
Mes del año (seno + coseno)               0.084         0.095
Evento del calendario                     0.035         0.020
Días SNAP                                 0.031         0.044
```

Los seis indicadores de día de la semana son un solo concepto codificado en columnas excluyentes; por eso el peso individual salta de un indicador a otro entre modelos (lunes en uno, martes en otro) y solo tiene sentido leerlos juntos. Atención sumada por bloques de 7 posiciones (de la más antigua a la más reciente): 0.280, 0.173, 0.133, 0.110, 0.094, 0.079, 0.068, 0.061, 0.001, 0.001, 0.000, 0.000. La atención decrece de forma casi monótona desde el inicio de la ventana; no se ven picos semanales claros, así que esta gráfica no demuestra por sí sola que la red use la estacionalidad semanal.
