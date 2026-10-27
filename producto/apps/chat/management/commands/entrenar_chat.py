"""Entrena el clasificador de intenciones del chat y lo evalúa con frases de prueba escritas aparte.
Uso: python manage.py entrenar_chat"""
from django.core.management.base import BaseCommand

from apps.chat.nlp import modelo


class Command(BaseCommand):
    help = "Entrena y evalúa el clasificador de intenciones del chat."

    def handle(self, *args, **opts):
        _, m = modelo.entrenar_y_guardar()
        self.stdout.write(f"Ejemplos de entrenamiento: {m['n_entrenamiento']}. Frases de prueba: {m['n_prueba']}.")
        self.stdout.write(self.style.SUCCESS(f"Exactitud (prueba nueva): {m['exactitud'] * 100:.1f} % | estricta: {m['exactitud_estricta'] * 100:.1f} % | en las pruebas de desarrollo: {m['exactitud_desarrollo'] * 100:.1f} %"))
        for k, v in m["por_intencion"].items():
            self.stdout.write(f"  {k:20s} {v}")
        for e in m["errores"]:
            self.stdout.write(self.style.WARNING(f"  Error: «{e['texto']}» (contexto: {e['contexto']}) -> {e['predicha']} (esperada {e['esperada']}, confianza {e['confianza']})"))
