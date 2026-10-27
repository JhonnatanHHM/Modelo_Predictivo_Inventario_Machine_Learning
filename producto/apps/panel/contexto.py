from .models import Perfil


def perfil(request):
    """Pone el perfil del usuario (nombre y avatar) en todas las plantillas."""
    if not request.user.is_authenticated:
        return {}
    p, _ = Perfil.objects.get_or_create(usuario=request.user)
    return {"perfil": p, "nombre_usuario": p.nombre_mostrado or request.user.get_username()}
