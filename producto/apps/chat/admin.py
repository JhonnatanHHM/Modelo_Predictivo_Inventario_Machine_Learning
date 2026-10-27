from django.contrib import admin

from .models import MensajeChat, SesionChat


class MensajeInline(admin.TabularInline):
    model = MensajeChat
    extra = 0
    readonly_fields = ("rol", "texto", "intencion", "confianza", "entidades", "fuera_de_contexto", "creado")


@admin.register(SesionChat)
class SesionChatAdmin(admin.ModelAdmin):
    list_display = ("id", "titulo", "usuario", "creada", "actualizada")
    inlines = [MensajeInline]
