from django.conf import settings
from django.db import models


class Perfil(models.Model):
    """Datos de presentación del usuario: nombre para mostrar y sexo (define el avatar)."""
    SEXOS = [("F", "Femenino"), ("M", "Masculino"), ("N", "Prefiero no decirlo")]

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    nombre_mostrado = models.CharField(max_length=60, blank=True)
    sexo = models.CharField(max_length=1, choices=SEXOS, default="N")

    def __str__(self):
        return f"Perfil de {self.usuario}"
