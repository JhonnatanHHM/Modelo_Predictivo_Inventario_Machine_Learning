import uuid

from django.conf import settings
from django.db import models


class SesionChat(models.Model):
    """Una conversación. El historial completo y la memoria de contexto (tienda, categoría, etc.) viven aquí."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sesiones_chat")
    titulo = models.CharField(max_length=120, blank=True)
    contexto = models.JSONField(default=dict, blank=True)          # última intención, tienda, categoría, serie, horizonte...
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizada"]

    def __str__(self):
        return self.titulo or str(self.id)


class MensajeChat(models.Model):
    ROLES = [("usuario", "Usuario"), ("asistente", "Asistente")]

    sesion = models.ForeignKey(SesionChat, on_delete=models.CASCADE, related_name="mensajes")
    rol = models.CharField(max_length=10, choices=ROLES)
    texto = models.TextField()
    intencion = models.CharField(max_length=40, blank=True)
    confianza = models.FloatField(null=True, blank=True)
    entidades = models.JSONField(default=dict, blank=True)
    fuera_de_contexto = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado", "id"]
