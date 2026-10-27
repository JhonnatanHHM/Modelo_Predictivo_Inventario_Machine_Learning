"""Carga a la base las métricas de las pruebas de laboratorio (para la comparación de modelos de la pestaña Modelos).

Uso: python manage.py cargar_metricas
Lee resultados_completa/consolidado_global_ventanas_comunes.csv de RESULTADOS_LAB (ver .env.example).
"""
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.pronosticos.models import MetricaModelo

METRICAS = ["MASE_medio", "MASE_mediana", "pinball_escalada_media", "WQL", "cobertura_p90", "cobertura_80", "ancho_medio", "sesgo_relativo"]


class Command(BaseCommand):
    help = "Carga las métricas de las pruebas de laboratorio."

    def handle(self, *args, **opts):
        ruta = settings.RESULTADOS_LAB / "consolidado_global_ventanas_comunes.csv"
        if not ruta.exists():
            raise CommandError(f"No encuentro {ruta}. Revisa RESULTADOS_LAB en tu archivo .env.")
        df = pd.read_csv(ruta)
        MetricaModelo.objects.filter(segmento="global").delete()
        filas = [MetricaModelo(modelo=r.modelo_id, ventana_origen=None, segmento="global", metrica=m, valor=float(getattr(r, m)))
                 for r in df.itertuples() for m in METRICAS if hasattr(r, m)]
        MetricaModelo.objects.bulk_create(filas)
        self.stdout.write(self.style.SUCCESS(f"Métricas cargadas: {len(filas)} valores de {df.modelo_id.nunique()} modelos."))
