import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import SesionChat
from .nlp import datos, modelo, motor, respuestas


def _info_modelo():
    import json
    import os
    m = modelo.metricas_guardadas()
    ruta = os.path.join(os.path.dirname(modelo.__file__), "evaluacion_agentes.json")
    if m and os.path.exists(ruta):
        e = json.load(open(ruta, encoding="utf-8"))
        ult = e["rondas"][-1]
        m["agentes"] = {"n": ult["n"], "funcional": str(ult["funcional"]).replace(".", ","), "estricta": str(ult["estricta"]).replace(".", ","),
                        "cv": str(e["validacion_cruzada"]["funcional"]).replace(".", ","), "cv_estricta": str(e["validacion_cruzada"]["estricta"]).replace(".", ","),
                        "n_cv": e["validacion_cruzada"]["n"]}
    if m:
        m["pct"] = f"{m['exactitud'] * 100:.1f}".replace(".", ",")
        m["pct_estricta"] = f"{m.get('exactitud_estricta', m['exactitud']) * 100:.1f}".replace(".", ",")
    return m


def _sesiones(request):
    return SesionChat.objects.filter(usuario=request.user)


def inicio(request):
    """Abre la conversación más reciente o crea la primera."""
    sesion = _sesiones(request).first() or SesionChat.objects.create(usuario=request.user)
    return redirect("chat_sesion", sesion_id=sesion.id)


def sesion(request, sesion_id):
    actual = get_object_or_404(_sesiones(request), pk=sesion_id)
    mensajes = [{"rol": m.rol, "texto": m.texto, "extra": (m.entidades or {}).get("extra", {}) if m.rol == "asistente" else {},
                 "intencion": m.intencion, "confianza": m.confianza, "fuera": m.fuera_de_contexto} for m in actual.mensajes.all()]
    # La conversación que se abre solo muestra sugerencias si está vacía
    contexto = {"seccion": "chat", "actual": actual, "sesiones": _sesiones(request)[:30], "mensajes": mensajes, "ejemplos": respuestas.EJEMPLOS,
                "info_modelo": _info_modelo(), "recuerda": {k: v for k, v in (actual.contexto or {}).items() if k in ("tienda", "categoria", "departamento", "producto", "nivel", "horizonte", "pasado")}}
    return render(request, "chat/chat.html", contexto)


@require_POST
def nueva(request):
    return redirect("chat_sesion", sesion_id=SesionChat.objects.create(usuario=request.user).id)


@require_POST
def eliminar(request, sesion_id):
    get_object_or_404(_sesiones(request), pk=sesion_id).delete()
    return redirect("chat_inicio")


@require_POST
def olvidar(request, sesion_id):
    """Borra la memoria de la conversación (tienda, categoría, periodo...) sin borrar el historial."""
    actual = get_object_or_404(_sesiones(request), pk=sesion_id)
    actual.contexto = {}
    actual.save()
    return JsonResponse({"ok": True})


@require_POST
def enviar(request, sesion_id):
    actual = get_object_or_404(_sesiones(request), pk=sesion_id)
    try:
        cuerpo = json.loads(request.body)
        texto = str(cuerpo.get("texto", "")).strip()
        forzada = cuerpo.get("intencion") or None
    except (ValueError, TypeError):
        return JsonResponse({"error": "Mensaje no válido."}, status=400)
    if not texto:
        return JsonResponse({"error": "Escribe un mensaje."}, status=400)
    if forzada and forzada not in datos.INTENCIONES_DOMINIO:
        forzada = None
    respuesta = motor.responder(actual, texto, intencion_forzada=forzada)
    respuesta["titulo"] = actual.titulo
    return JsonResponse(respuesta)
