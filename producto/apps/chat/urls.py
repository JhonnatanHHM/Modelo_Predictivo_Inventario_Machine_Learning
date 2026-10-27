from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="chat_inicio"),
    path("nueva/", views.nueva, name="chat_nueva"),
    path("<uuid:sesion_id>/", views.sesion, name="chat_sesion"),
    path("<uuid:sesion_id>/enviar/", views.enviar, name="chat_enviar"),
    path("<uuid:sesion_id>/eliminar/", views.eliminar, name="chat_eliminar"),
    path("<uuid:sesion_id>/olvidar/", views.olvidar, name="chat_olvidar"),
]
