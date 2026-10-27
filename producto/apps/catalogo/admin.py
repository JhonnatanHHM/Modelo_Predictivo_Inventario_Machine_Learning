from django.contrib import admin

from .models import Calendario, Categoria, Departamento, PrecioSemanal, Serie, Tienda, VentaDiaria


@admin.register(Serie)
class SerieAdmin(admin.ModelAdmin):
    list_display = ("id_m5", "item_id", "tienda", "departamento", "rotacion")
    list_filter = ("tienda", "departamento", "rotacion")
    search_fields = ("id_m5", "item_id")


@admin.register(VentaDiaria)
class VentaDiariaAdmin(admin.ModelAdmin):
    list_display = ("serie", "fecha", "unidades", "precio")
    list_filter = ("fecha",)
    raw_id_fields = ("serie",)


admin.site.register([Tienda, Categoria, Departamento, Calendario, PrecioSemanal])
