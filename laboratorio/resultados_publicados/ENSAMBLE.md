# Conjunto ETS + LightGBM (promedio de cuantiles)

Se promedian, cuantil a cuantil (P10, P50, P90), las predicciones guardadas de ETS y LightGBM con distintos pesos y se reordenan los cuantiles. No se entrena nada nuevo. Ventanas de 28 días con ambos modelos: [1773, 1801, 1829, 1857, 1885, 1913] (374 series cada una).

## 1) Calidad de la predicción (peso LGBM 0 = solo ETS, 1 = solo LightGBM)

```
                           ventanas    MASE  pinball_esc     WQL  cob_P90  cob_80  ancho_80
config                                                                                     
ETS+LGBM (peso LGBM 0.00)       6.0  0.9464       0.2988  1.6798   0.8996  0.8773    3.0226
ETS+LGBM (peso LGBM 0.25)       6.0  0.8969       0.2883  1.6309   0.9008  0.8731    2.9653
ETS+LGBM (peso LGBM 0.50)       6.0  0.8518       0.2793  1.5963   0.9002  0.8739    2.9080
ETS+LGBM (peso LGBM 0.75)       6.0  0.8100       0.2717  1.5750   0.8993  0.8736    2.8507
ETS+LGBM (peso LGBM 1.00)       6.0  0.7716       0.2656  1.5684   0.9018  0.8928    2.7933
```

**Mezcla 50/50 frente a LightGBM solo**, diferencia por serie (promedio de las ventanas), con remuestreo de las 374 series:
- pinball escalada (negativo = la mezcla es mejor): media +0.0137, intervalo 95 % [+0.0118, +0.0156]; la mezcla gana en 25 % de las series.
- MASE: media +0.0802, intervalo 95 % [+0.0704, +0.0902].
El intervalo solo mide la variación entre series; no incluye la incertidumbre de usar solo 6 ventanas ni un único periodo de M5.

## 2) Con tres modelos (ETS + LightGBM + TFT h64), solo ventanas donde existe el TFT

```
                                   ventanas    MASE  pinball_esc     WQL  cob_P90  cob_80  ancho_80
config                                                                                             
ETS [ventanas con TFT]                  4.0  0.9514       0.2998  1.6592   0.8958  0.8738    3.0289
ETS+LGBM (0,5) [ventanas con TFT]       4.0  0.8615       0.2818  1.5860   0.8970  0.8689    2.9200
ETS+LGBM+TFT (1/3 c/u)                  4.0  0.8332       0.2764  1.5683   0.8981  0.8146    2.8770
LightGBM [ventanas con TFT]             4.0  0.7845       0.2693  1.5612   0.9015  0.8902    2.8112
TFT h64 [ventanas con TFT]              4.0  0.7809       0.2695  1.5650   0.8971  0.8267    2.7908
```

## 3) Reposición (unidades; ver POSPROCESO.md para las reglas de la simulación)

Sobrante relativo a la demanda que hace falta para llegar a una tasa de servicio dada (interpolando en k de P50 + k x (P90 - P50)); menor es mejor.

### 2 modelos, todas las ventanas

```
                                    sobrante_para_95  sobrante_para_97  sobrante_para_98
politica config                                                                         
28d      ETS+LGBM (peso LGBM 0.00)             0.518             0.693             0.850
         ETS+LGBM (peso LGBM 0.25)             0.490             0.669             0.819
         ETS+LGBM (peso LGBM 0.50)             0.491             0.663             0.883
         ETS+LGBM (peso LGBM 0.75)             0.513             0.764             0.988
         ETS+LGBM (peso LGBM 1.00)             0.578             0.924             1.303
semanal  ETS+LGBM (peso LGBM 0.00)             0.913             1.198             1.383
         ETS+LGBM (peso LGBM 0.25)             0.901             1.171             1.394
         ETS+LGBM (peso LGBM 0.50)             0.920             1.155             1.433
         ETS+LGBM (peso LGBM 0.75)             0.956             1.267             1.549
         ETS+LGBM (peso LGBM 1.00)             1.008             1.468             1.961
```

### con TFT, ventanas comunes

```
                                            sobrante_para_95  sobrante_para_97  sobrante_para_98
politica config                                                                                 
28d      ETS [ventanas con TFT]                        0.509             0.704             0.839
         ETS+LGBM (0,5) [ventanas con TFT]             0.488             0.659             0.893
         ETS+LGBM+TFT (1/3 c/u)                        0.501             0.738             1.013
         LightGBM [ventanas con TFT]                   0.576             0.929             1.394
         TFT h64 [ventanas con TFT]                    0.738             1.964               NaN
semanal  ETS [ventanas con TFT]                        0.869             1.158             1.339
         ETS+LGBM (0,5) [ventanas con TFT]             0.900             1.131             1.423
         ETS+LGBM+TFT (1/3 c/u)                        0.932             1.239             1.553
         LightGBM [ventanas con TFT]                   1.005             1.531             2.281
         TFT h64 [ventanas con TFT]                    1.240               NaN               NaN
```

