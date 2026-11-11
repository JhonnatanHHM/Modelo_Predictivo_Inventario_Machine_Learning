"""Carga a la base las métricas de la evaluación final (para la comparación de modelos de la pestaña Modelos).

Uso: python manage.py cargar_metricas
Lee exp4_ventanas_prueba.csv de RESULTADOS_LAB (ver .env.example): LightGBM de la primera versión y LightGBM final en las dos ventanas de prueba (promedio).
"""
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.pronosticos.models import MetricaModelo

COLUMNAS = {"MASE": "MASE_medio", "pinball_esc": "pinball_escalada_media", "WQL": "WQL", "cob_p90": "cobertura_p90", "cob80": "cobertura_80", "ancho": "ancho_medio", "sesgo": "sesgo_relativo"}
MODELOS = {"unidad1": "lightgbm_v1", "final": "lightgbm"}


class Command(BaseCommand):
    help = "Carga las métricas de la evaluación final del laboratorio."

    def handle(self, *args, **opts):
        ruta = settings.RESULTADOS_LAB / "exp4_ventanas_prueba.csv"
        if not ruta.exists():
            raise CommandError(f"No encuentro {ruta}. Revisa RESULTADOS_LAB en tu archivo .env.")
        df = pd.read_csv(ruta).groupby("modelo")[list(COLUMNAS)].mean()
        MetricaModelo.objects.filter(segmento="global").delete()
        filas = [MetricaModelo(modelo=MODELOS[m], ventana_origen=None, segmento="global", metrica=nombre, valor=float(df.loc[m, col]))
                 for m in df.index if m in MODELOS for col, nombre in COLUMNAS.items()]
        MetricaModelo.objects.bulk_create(filas)
        self.stdout.write(self.style.SUCCESS(f"Métricas cargadas: {len(filas)} valores de {len(MODELOS)} modelos."))
