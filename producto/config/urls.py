from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("acceso/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="acceso"),
    path("salir/", auth_views.LogoutView.as_view(), name="salir"),
    path("chat/", include("apps.chat.urls")),
    path("", include("apps.panel.urls")),
]
