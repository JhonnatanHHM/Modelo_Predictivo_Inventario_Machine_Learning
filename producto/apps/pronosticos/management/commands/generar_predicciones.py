"""Entrena los modelos con los datos de la base, pronostica los 28 días siguientes al origen y guarda todo en PostgreSQL.

Uso:
  python manage.py generar_predicciones                 # origen = último día con ventas reales -> pronóstico real hacia el futuro
  python manage.py generar_predicciones --origen 1913   # prueba hacia atrás: se pronostica un periodo ya conocido y se miden los errores
Genera dos corridas: LightGBM con cuantiles diarios (P10, P50, P90) y LightGBM del cuantil de la demanda total (semanal y de 28 días),
y de la segunda salen las sugerencias de reposición para varios niveles de servicio.
"""
import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.pronosticos import servicios
from apps.pronosticos.models import PrediccionAgregada, SugerenciaReposicion
from ml import agregado, datos, diario

NIVELES_SERVICIO = (0.8, 0.9, 0.95)


class Command(BaseCommand):
    help = "Entrena LightGBM (diario y agregado), pronostica 28 días y guarda predicciones y sugerencias de reposición."

    def add_arguments(self, parser):
        parser.add_argument("--origen", type=int, help="Último día observado (d_N). Por defecto, el último con ventas reales.")
        parser.add_argument("--activar", action="store_true", help="Marca las corridas como activas aunque sea una prueba hacia atrás.")

    def handle(self, *args, **opts):
        self.stdout.write("Leyendo datos de la base...")
        D = datos.cargar()
        origen = opts["origen"] or D.ultimo_dnum
        if origen > D.ultimo_dnum or origen < 400:
            raise CommandError(f"El origen debe estar entre 400 y {D.ultimo_dnum}.")
        futuro = origen == D.ultimo_dnum
        fecha_origen = D.fechas[origen - 1]
        self.stdout.write(f"{len(D.ids)} series. Origen d_{origen} ({fecha_origen}). {'Pronóstico real hacia el futuro' if futuro else 'Prueba hacia atrás'}.")
        carpeta = settings.MODELOS_DIR / f"d{origen}"

        self.stdout.write("Entrenando LightGBM diario (P10, P50, P90)...")
        Q = diario.pronosticar(D, origen, carpeta)
        self.stdout.write("Entrenando LightGBM de la demanda total (semanal y 28 días)...")
        Qsem, Q28 = agregado.pronosticar(D, origen, carpeta)

        metricas = {} if futuro else self.evaluar(D, origen, Q)
        with transaction.atomic():
            c_diaria = servicios.crear_corrida("LightGBM diario", "lightgbm", origen, fecha_origen, futuro, carpeta, metricas, opts["activar"])
            c_agreg = servicios.crear_corrida("LightGBM demanda total", "lgbm_agregado", origen, fecha_origen, futuro, carpeta, {"taus": list(agregado.TAUS)}, opts["activar"])
            servicios.guardar_diarias(D, c_diaria, origen, Q)
            self.guardar_agregadas(D, c_agreg, Qsem, Q28)
        self.stdout.write(self.style.SUCCESS(f"Listo: {len(D.ids) * diario.H} predicciones diarias y sugerencias de reposición guardadas."))
        if metricas:
            self.stdout.write("Verificación contra lo que realmente ocurrió: " + ", ".join(f"{k}={v}" for k, v in metricas.items()))

    def guardar_agregadas(self, D, corrida, Qsem, Q28):
        taus = agregado.TAUS
        agregadas, sugerencias = [], []
        for k, pk in enumerate(D.serie_pk):
            pk = int(pk)
            for j, tau in enumerate(taus):
                for s in range(4):
                    agregadas.append(PrediccionAgregada(corrida=corrida, serie_id=pk, horizonte=f"sem{s + 1}", tau=tau, unidades=float(Qsem[k, s, j])))
                agregadas.append(PrediccionAgregada(corrida=corrida, serie_id=pk, horizonte="28d", tau=tau, unidades=float(Q28[k, j])))
            mediana = taus.index(0.5)
            for nivel in NIVELES_SERVICIO:
                j = taus.index(nivel)
                sugerencias.append(SugerenciaReposicion(corrida=corrida, serie_id=pk, politica="28d", nivel_servicio=nivel,
                                                        stock_objetivo=float(Q28[k, j]), demanda_mediana=float(Q28[k, mediana])))
                sugerencias.append(SugerenciaReposicion(corrida=corrida, serie_id=pk, politica="semanal", nivel_servicio=nivel,
                                                        stock_objetivo=float(Qsem[k, 0, j]), demanda_mediana=float(Qsem[k, 0, mediana])))
        PrediccionAgregada.objects.bulk_create(agregadas, batch_size=5000)
        SugerenciaReposicion.objects.bulk_create(sugerencias, batch_size=5000)

    def evaluar(self, D, origen, Q):
        """Compara con las ventas reales cuando el origen es anterior al último día con datos (MASE y cobertura)."""
        Y = D.Y[:, origen:origen + diario.H]
        mase, cob10, cob90, cob80 = [], [], [], []
        for k in range(len(D.ids)):
            hist = D.Y[k, D.inicio[k]:origen]
            esc = np.abs(hist[7:] - hist[:-7]).mean()
            if not esc > 0:
                continue
            mase.append(np.abs(Y[k] - Q[k, :, 1]).mean() / esc)
            cob10.append((Y[k] <= Q[k, :, 0]).mean()); cob90.append((Y[k] <= Q[k, :, 2]).mean())
            cob80.append(((Y[k] >= Q[k, :, 0]) & (Y[k] <= Q[k, :, 2])).mean())
        return {"MASE": round(float(np.mean(mase)), 3), "cobertura_P90": round(float(np.mean(cob90)), 3), "cobertura_80": round(float(np.mean(cob80)), 3)}
