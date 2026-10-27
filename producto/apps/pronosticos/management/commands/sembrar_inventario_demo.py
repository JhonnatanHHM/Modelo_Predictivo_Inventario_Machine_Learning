"""Genera un inventario actual SIMULADO para poder demostrar la página de reposición (M5 no trae niveles de inventario).

Cada serie recibe entre 20 % y 160 % de su demanda mediana de los próximos 28 días, al azar con semilla fija.
Los registros quedan marcados como simulados. Uso: python manage.py sembrar_inventario_demo
"""
import numpy as np
from django.core.management.base import BaseCommand, CommandError

from apps.pronosticos.models import InventarioActual, PrediccionAgregada


class Command(BaseCommand):
    help = "Crea un inventario actual simulado (solo para demostración)."

    def handle(self, *args, **opts):
        med = {p.serie_id: p.unidades for p in PrediccionAgregada.objects.filter(corrida__tipo="lgbm_agregado", corrida__activa=True, horizonte="28d", tau=0.5)}
        if not med:
            raise CommandError("No hay predicciones activas. Ejecuta primero: python manage.py generar_predicciones")
        rng = np.random.default_rng(42)
        InventarioActual.objects.filter(simulado=True).delete()
        InventarioActual.objects.bulk_create([InventarioActual(serie_id=s, unidades=int(round(m * rng.uniform(0.2, 1.6))), simulado=True)
                                              for s, m in med.items() if not InventarioActual.objects.filter(serie_id=s).exists()])
        self.stdout.write(self.style.SUCCESS(f"Inventario simulado creado para {InventarioActual.objects.filter(simulado=True).count()} series."))
