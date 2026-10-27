from django.contrib import admin

from .models import CorridaModelo, MetricaModelo, Prediccion, PrediccionAgregada, SugerenciaReposicion


@admin.register(CorridaModelo)
class CorridaModeloAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "dnum_origen", "fecha_origen", "es_futuro_real", "activa", "creada")
    list_filter = ("tipo", "activa", "es_futuro_real")


admin.site.register([Prediccion, PrediccionAgregada, SugerenciaReposicion, MetricaModelo])
