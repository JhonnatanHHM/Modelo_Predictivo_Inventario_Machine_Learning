"""Entrena el Temporal Fusion Transformer con los datos de la base, pronostica los 28 días siguientes y lo guarda todo.

Uso:
  python manage.py entrenar_tft                  # configuración completa: 1.500 pasos (~1 h en CPU)
  python manage.py entrenar_tft --pasos 20       # prueba rápida para verificar que todo funciona (~2 min)
El modelo entrenado queda en MODELOS_DIR; las predicciones, en PostgreSQL (corrida de tipo TFT).
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.pronosticos import servicios
from ml import datos, tft


class Command(BaseCommand):
    help = "Entrena el TFT, pronostica 28 días y guarda las predicciones."

    def add_arguments(self, parser):
        parser.add_argument("--origen", type=int, help="Último día observado (d_N). Por defecto, el último con ventas reales.")
        parser.add_argument("--pasos", type=int, default=1500, help="Pasos de entrenamiento (1500 = configuración completa).")
        parser.add_argument("--hidden", type=int, default=64, help="Tamaño de la red.")
        parser.add_argument("--activar", action="store_true", help="Marca la corrida como activa aunque sea una prueba hacia atrás.")

    def handle(self, *args, **opts):
        D = datos.cargar()
        origen = opts["origen"] or D.ultimo_dnum
        if origen > D.ultimo_dnum or origen < 400:
            raise CommandError(f"El origen debe estar entre 400 y {D.ultimo_dnum}.")
        futuro = origen == D.ultimo_dnum
        fecha_origen = D.fechas[origen - 1]
        self.stdout.write(f"{len(D.ids)} series. Origen d_{origen} ({fecha_origen}). Entrenando el TFT con {opts['pasos']} pasos...")
        carpeta = settings.MODELOS_DIR / f"d{origen}" / "tft"
        Q = tft.entrenar_y_pronosticar(D, origen, pasos=opts["pasos"], hidden=opts["hidden"], carpeta=carpeta)
        with transaction.atomic():
            corrida = servicios.crear_corrida("TFT", "tft", origen, fecha_origen, futuro, carpeta,
                                              {"pasos": opts["pasos"], "hidden": opts["hidden"], "historia": tft.INPUT_SIZE}, opts["activar"])
            servicios.guardar_diarias(D, corrida, origen, Q)
        self.stdout.write(self.style.SUCCESS(f"Listo: {len(D.ids) * tft.H} predicciones guardadas y modelo en {carpeta}."))
