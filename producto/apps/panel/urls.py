from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("proyecciones/", views.proyecciones, name="proyecciones"),
    path("reposicion/", views.reposicion, name="reposicion"),
    path("reposicion/inventario/", views.actualizar_inventario, name="actualizar_inventario"),
    path("perfil/", views.perfil_usuario, name="perfil"),
    path("perfil/", views.perfil_usuario, name="perfil"),
    path("modelos/", views.modelos, name="modelos"),
    path("modelos/lanzar/", views.lanzar_tarea, name="lanzar_tarea"),
    path("modelos/estado/", views.estado_tareas, name="estado_tareas"),
    path("modelos/registro/<int:tarea_id>/", views.registro_tarea, name="registro_tarea"),
]
