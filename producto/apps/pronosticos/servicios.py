"""Funciones compartidas por los comandos que guardan predicciones."""
from .models import CorridaModelo, Prediccion


def crear_corrida(nombre, tipo, origen, fecha_origen, futuro, carpeta, parametros, activar=False):
    """Reemplaza la corrida del mismo tipo y origen. Si es un pronóstico real (o se pide), pasa a ser la activa de su tipo."""
    CorridaModelo.objects.filter(tipo=tipo, dnum_origen=origen).delete()
    c = CorridaModelo.objects.create(nombre=f"{nombre} d_{origen}", tipo=tipo, dnum_origen=origen, fecha_origen=fecha_origen,
                                     es_futuro_real=futuro, parametros=parametros, ruta_modelo=str(carpeta))
    if futuro or activar:
        CorridaModelo.objects.filter(tipo=tipo).exclude(pk=c.pk).update(activa=False)
        c.activa = True
        c.save(update_fields=["activa"])
    return c


def guardar_diarias(D, corrida, origen, Q):
    """Q: arreglo (n_series, 28, 3) con P10, P50 y P90."""
    filas = []
    for k, pk in enumerate(D.serie_pk):
        for h in range(Q.shape[1]):
            p10, p50, p90 = (float(x) for x in Q[k, h])
            filas.append(Prediccion(corrida=corrida, serie_id=int(pk), fecha=D.fechas[origen + h], p10=p10, p50=p50, p90=p90))
    Prediccion.objects.bulk_create(filas, batch_size=5000)
