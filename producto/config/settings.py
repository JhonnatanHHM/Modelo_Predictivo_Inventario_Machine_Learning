"""Configuración de Django. Todo lo que cambia entre equipos se lee de variables de entorno (archivo .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(nombre, defecto=None):
    return os.environ.get(nombre, defecto)


SECRET_KEY = env("DJANGO_SECRET_KEY", "clave-solo-para-desarrollo-cambiala")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.catalogo",
    "apps.pronosticos",
    "apps.panel",
    "apps.chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",   # todo el sitio pide el acceso simple (usuario y contraseña)
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.panel.contexto.perfil",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "inventario"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = []        # acceso simple de demostración

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "acceso"
LOGIN_REDIRECT_URL = "proyecciones"
LOGOUT_REDIRECT_URL = "acceso"

# ---- Rutas de datos y modelos (fuera del repositorio: los datos de M5 no se pueden redistribuir) ----
UNIDAD_DIR = BASE_DIR.parent
# El laboratorio (scripts de los modelos) puede llamarse "laboratorio" (repositorio) o "modelo_predictivo_inventario_alfa" (carpeta de trabajo original).
LAB_DIR = Path(env("LAB_DIR", next((p for p in (UNIDAD_DIR / "laboratorio", UNIDAD_DIR / "modelo_predictivo_inventario_alfa") if p.exists()), UNIDAD_DIR / "laboratorio")))
M5_DIR = Path(env("M5_DIR", UNIDAD_DIR / "m5-forecasting-accuracy"))
TABLA_MAESTRA = Path(env("TABLA_MAESTRA", LAB_DIR / "datos_completa" / "tabla_maestra_alfa.parquet"))
SERIES_CSV = Path(env("SERIES_CSV", LAB_DIR / "datos_completa" / "series_alfa.csv"))
MODELOS_DIR = Path(env("MODELOS_DIR", BASE_DIR / "modelos_guardados"))
RESULTADOS_LAB = Path(env("RESULTADOS_LAB", next((p for p in (LAB_DIR / "resultados_completa", LAB_DIR / "resultados_publicados") if (p / "consolidado_global_ventanas_comunes.csv").exists()), LAB_DIR / "resultados_completa")))
LOGS_DIR = Path(env("LOGS_DIR", BASE_DIR / "logs"))
