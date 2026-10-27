# Consolidado del set completo (374 series)

Ventanas con TFT: [1857, 1885, 1913]. Línea base en todas sus ventanas.

## MASE medio por modelo y ventana (origen = último día visto)

```
origen            1773   1801   1829   1857   1885   1913
modelo_id                                                
ets              0.968  0.904  0.952  0.929  0.944  0.981
lightgbm         0.762  0.729  0.761  0.770  0.776  0.831
naive            1.111  0.993  1.046  1.038  1.105  1.134
tft_h64            NaN    NaN  0.765  0.769  0.763  0.826
tft_h64_sem2       NaN    NaN    NaN    NaN    NaN  0.828
tft_in112          NaN    NaN    NaN    NaN    NaN  0.829
tft_lr3e3          NaN    NaN    NaN    NaN    NaN  0.839
tft_p3000          NaN    NaN    NaN    NaN    NaN  0.830
tft_p3000_lr3e3    NaN    NaN    NaN    NaN    NaN  0.830
tft_s1             NaN    NaN    NaN  0.764  0.772  0.833
tft_s2             NaN    NaN    NaN    NaN  0.768  0.834
```

## Global en las ventanas comunes

```
                       ventanas  MASE_medio  MASE_mediana  pinball_escalada_media    WQL  cobertura_p90  cobertura_80  ancho_medio  sesgo_relativo
modelo_id                                                                                                                                         
ets              1857,1885,1913       0.951         0.893                   0.300  1.630          0.897         0.876        3.021          -0.052
lightgbm         1857,1885,1913       0.792         0.744                   0.271  1.549          0.905         0.900        2.837          -0.427
naive            1857,1885,1913       1.093         1.015                   0.383  2.129          0.915         0.844        2.707          -0.065
tft_h64          1857,1885,1913       0.786         0.739                   0.271  1.557          0.893         0.815        2.744          -0.397
tft_h64_sem2               1913       0.828         0.749                   0.284  1.575          0.881         0.855        2.804          -0.470
tft_in112                  1913       0.829         0.751                   0.286  1.573          0.867         0.845        2.626          -0.462
tft_lr3e3                  1913       0.839         0.761                   0.288  1.594          0.878         0.776        2.740          -0.494
tft_p3000                  1913       0.830         0.755                   0.286  1.587          0.869         0.769        2.654          -0.462
tft_p3000_lr3e3            1913       0.830         0.754                   0.287  1.585          0.872         0.816        2.648          -0.468
tft_s1           1857,1885,1913       0.790         0.743                   0.272  1.559          0.901         0.813        2.816          -0.406
tft_s2                1885,1913       0.801         0.751                   0.275  1.560          0.880         0.783        2.742          -0.413
```

## MASE por rotación

```
tier              alta   baja  media
modelo_id                           
ets              0.836  1.033  0.982
lightgbm         0.792  0.724  0.861
naive            1.045  1.078  1.153
tft_h64          0.784  0.726  0.849
tft_h64_sem2     0.804  0.773  0.906
tft_in112        0.804  0.771  0.912
tft_lr3e3        0.808  0.789  0.919
tft_p3000        0.805  0.774  0.911
tft_p3000_lr3e3  0.805  0.779  0.907
tft_s1           0.788  0.722  0.859
tft_s2           0.793  0.738  0.872
```

## MASE por categoría

```
cat_id           FOODS  HOBBIES  HOUSEHOLD
modelo_id                                 
ets              0.950    0.986      0.920
lightgbm         0.826    0.754      0.779
naive            1.089    1.119      1.072
tft_h64          0.814    0.756      0.774
tft_h64_sem2     0.889    0.788      0.775
tft_in112        0.890    0.784      0.781
tft_lr3e3        0.900    0.801      0.784
tft_p3000        0.891    0.788      0.779
tft_p3000_lr3e3  0.891    0.790      0.778
tft_s1           0.820    0.753      0.780
tft_s2           0.838    0.760      0.785
```

## MASE por tienda

```
store_id          CA_1   TX_2   WI_2
modelo_id                           
ets              0.896  0.867  1.093
lightgbm         0.777  0.692  0.911
naive            1.054  1.002  1.225
tft_h64          0.766  0.693  0.902
tft_h64_sem2     0.824  0.710  0.952
tft_in112        0.826  0.706  0.958
tft_lr3e3        0.834  0.723  0.964
tft_p3000        0.829  0.709  0.956
tft_p3000_lr3e3  0.828  0.711  0.956
tft_s1           0.774  0.691  0.907
tft_s2           0.802  0.690  0.914
```

## Diferencias pareadas (MASE, negativo = el primero es mejor)

- lightgbm - ets: -0.167 (IC95 -0.181 a -0.154); lightgbm mejor en 78% de 1496 casos
- lightgbm - naive: -0.296 (IC95 -0.318 a -0.276); lightgbm mejor en 69% de 1496 casos
- tft_h64 - lightgbm: -0.004 (IC95 -0.008 a +0.001); tft_h64 mejor en 34% de 1496 casos
- tft_h64_sem2 - lightgbm: -0.003 (IC95 -0.010 a +0.003); tft_h64_sem2 mejor en 34% de 374 casos
- tft_in112 - lightgbm: -0.002 (IC95 -0.009 a +0.004); tft_in112 mejor en 34% de 374 casos
- tft_lr3e3 - lightgbm: +0.008 (IC95 +0.002 a +0.014); tft_lr3e3 mejor en 30% de 374 casos
- tft_p3000 - lightgbm: -0.001 (IC95 -0.007 a +0.005); tft_p3000 mejor en 33% de 374 casos
- tft_p3000_lr3e3 - lightgbm: -0.001 (IC95 -0.007 a +0.006); tft_p3000_lr3e3 mejor en 32% de 374 casos
- tft_s1 - lightgbm: -0.003 (IC95 -0.007 a +0.001); tft_s1 mejor en 31% de 1122 casos
- tft_s2 - lightgbm: -0.003 (IC95 -0.009 a +0.003); tft_s2 mejor en 29% de 748 casos
- tft_h64 - ets: -0.170 (IC95 -0.183 a -0.158); tft_h64 mejor en 79% de 1496 casos
- tft_h64 - tft_s1: -0.004 (IC95 -0.007 a -0.000); tft_h64 mejor en 52% de 1122 casos

## TFT en la ventana 1913 según variante (semilla, historia, tamaño)

```
      modelo_id  MASE_medio  pinball_escalada_media   WQL  cobertura_80  sesgo_relativo
        tft_h64       0.826                   0.286 1.586         0.864          -0.458
   tft_h64_sem2       0.828                   0.284 1.575         0.855          -0.470
      tft_in112       0.829                   0.286 1.573         0.845          -0.462
      tft_lr3e3       0.839                   0.288 1.594         0.776          -0.494
      tft_p3000       0.830                   0.286 1.587         0.769          -0.462
tft_p3000_lr3e3       0.830                   0.287 1.585         0.816          -0.468
         tft_s1       0.833                   0.288 1.596         0.815          -0.489
         tft_s2       0.834                   0.288 1.593         0.799          -0.419
```
