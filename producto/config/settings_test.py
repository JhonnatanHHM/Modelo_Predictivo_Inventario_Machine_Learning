"""Configuración para las pruebas: base SQLite en memoria (no hace falta PostgreSQL) y modelos del chat en una carpeta temporal.
Uso: python manage.py test --settings=config.settings_test"""
import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MODELOS_DIR = Path(tempfile.mkdtemp(prefix="modelos_prueba_"))
LOGS_DIR = Path(tempfile.mkdtemp(prefix="logs_prueba_"))
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]      # más rápido; solo para pruebas
ALLOWED_HOSTS = ["testserver", "localhost"]
