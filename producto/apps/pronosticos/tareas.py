"""Lanzamiento de tareas largas (generar predicciones, entrenar el TFT) desde la web, sin Celery:
cada tarea corre en un proceso aparte (manage.py ejecutar_tarea) y escribe su registro en LOGS_DIR."""
import os
import subprocess
import sys

import psutil
from django.conf import settings
from django.utils import timezone

from .models import EjecucionTarea

PASOS_PERMITIDOS = (20, 1500)       # prueba rápida o configuración completa
COMANDOS = {
    "generar_predicciones": {"titulo": "Generar predicciones", "parametros": lambda p: {}},
    "entrenar_tft": {"titulo": "Entrenar TFT", "parametros": lambda p: {"pasos": p if p in PASOS_PERMITIDOS else 1500}},
}


def refrescar(tarea):
    """Si el proceso ya no existe y la tarea seguía 'ejecutando', se marca como interrumpida."""
    if tarea.estado in ("pendiente", "ejecutando") and tarea.pid and not psutil.pid_exists(tarea.pid):
        tarea.estado, tarea.fin, tarea.resumen = "interrumpida", timezone.now(), "El proceso terminó sin avisar (¿se cerró el equipo o el servidor?)."
        tarea.save(update_fields=["estado", "fin", "resumen"])
    return tarea


def en_curso(comando):
    for t in EjecucionTarea.objects.filter(comando=comando, estado__in=["pendiente", "ejecutando"]):
        if refrescar(t).estado in ("pendiente", "ejecutando"):
            return t
    return None


def lanzar(comando, pasos=None):
    if comando not in COMANDOS:
        raise ValueError("Comando no permitido.")
    previa = en_curso(comando)
    if previa:
        return previa, False
    t = EjecucionTarea.objects.create(comando=comando, parametros=COMANDOS[comando]["parametros"](pasos), estado="pendiente")
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    t.ruta_log = str(settings.LOGS_DIR / f"tarea_{t.id}_{comando}.log")
    banderas = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    entorno = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    with open(t.ruta_log, "w", encoding="utf-8") as log:
        proceso = subprocess.Popen([sys.executable, str(settings.BASE_DIR / "manage.py"), "ejecutar_tarea", str(t.id)],
                                   stdout=log, stderr=subprocess.STDOUT, cwd=str(settings.BASE_DIR), env=entorno, creationflags=banderas, close_fds=True)
    t.pid, t.estado, t.inicio = proceso.pid, "ejecutando", timezone.now()
    t.save()
    return t, True


def cola_del_registro(tarea, lineas=60):
    """Últimas líneas del registro; las barras de progreso (que usan retorno de carro) se reducen a su último estado."""
    try:
        with open(tarea.ruta_log, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 60000))
            texto = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    filas = [ln.split(chr(13))[-1] for ln in texto.splitlines()]
    return chr(10).join([ln for ln in filas if ln.strip()][-lineas:])
