"""Proceso auxiliar que ejecuta una tarea lanzada desde la web y deja su estado en la base. No se usa a mano: lo lanza apps/pronosticos/tareas.py."""
import os
import traceback

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.pronosticos.models import EjecucionTarea


class Command(BaseCommand):
    help = "Ejecuta una tarea registrada (EjecucionTarea) y actualiza su estado."

    def add_arguments(self, parser):
        parser.add_argument("tarea_id", type=int)

    def handle(self, *args, **opts):
        t = EjecucionTarea.objects.get(pk=opts["tarea_id"])
        t.estado, t.pid, t.inicio = "ejecutando", os.getpid(), t.inicio or timezone.now()
        t.save()
        try:
            call_command(t.comando, **t.parametros)
            t.estado, t.resumen = "ok", "Terminó correctamente."
        except BaseException as e:                       # el detalle completo queda en el registro de la tarea
            traceback.print_exc()
            t.estado, t.resumen = "error", f"{type(e).__name__}: {e}"[:300]
        finally:
            t.fin = timezone.now()
            t.save()
