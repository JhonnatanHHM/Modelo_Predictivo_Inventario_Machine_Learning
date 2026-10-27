import json
from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Max, Min, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.catalogo.models import Categoria, Serie, Tienda, VentaDiaria
from apps.pronosticos import tareas
from apps.pronosticos.models import (CorridaModelo, EjecucionTarea, InventarioActual, MetricaModelo, Prediccion, PrediccionAgregada,
                                     SugerenciaReposicion)

NIVELES = (0.8, 0.9, 0.95)
ETIQUETAS_MODELO = {"naive": "Naive", "ets": "ETS", "lightgbm": "LightGBM", "tft_s1": "TFT base", "tft_h64": "TFT (hidden 64)",
                    "tft_in112": "TFT historia 112", "tft_p3000": "TFT 3.000 pasos", "tft_lr3e3": "TFT tasa 3e-3", "tft_p3000_lr3e3": "TFT 3.000 pasos y tasa 3e-3",
                    "tft_s2": "TFT base (semilla 2)", "tft_h64_sem2": "TFT hidden 64 (semilla 2)"}


def corrida_activa(tipo):
    return CorridaModelo.objects.filter(tipo=tipo, activa=True, es_futuro_real=True).order_by("-creada").first()


def _series_filtradas(request):
    tienda, categoria = request.GET.get("tienda", ""), request.GET.get("categoria", "")
    qs = Serie.objects.select_related("tienda", "departamento__categoria")
    if tienda:
        qs = qs.filter(tienda__codigo=tienda)
    if categoria:
        qs = qs.filter(departamento__categoria__codigo=categoria)
    return qs, tienda, categoria


def _opciones_filtros():
    return {"tiendas": Tienda.objects.all(), "categorias": Categoria.objects.all()}


def inicio(request):
    """La raíz del sitio abre Proyecciones (ya no hay página de inicio)."""
    return redirect("proyecciones")


# ----------------------------------------------------------------------------------------------- Proyecciones
def proyecciones(request):
    agg, lgbm, tft = corrida_activa("lgbm_agregado"), corrida_activa("lightgbm"), corrida_activa("tft")
    contexto = {"seccion": "proyecciones", "hay_datos": bool(agg and lgbm), **_opciones_filtros()}
    if not contexto["hay_datos"]:
        return render(request, "panel/proyecciones.html", contexto)

    series, tienda, categoria = _series_filtradas(request)
    ids = list(series.values_list("id", flat=True))
    base = PrediccionAgregada.objects.filter(corrida=agg, horizonte="28d", serie_id__in=ids)
    mediana = base.filter(tau=0.5).aggregate(t=Sum("unidades"))["t"] or 0
    alto = base.filter(tau=0.9).aggregate(t=Sum("unidades"))["t"] or 0
    por_categoria = list(base.filter(tau=0.5).values("serie__departamento__categoria__codigo").annotate(t=Sum("unidades")).order_by("-t"))
    top_qs = list(base.filter(tau=0.5).select_related("serie__tienda", "serie__departamento").order_by("-unidades")[:12])
    q90 = dict(base.filter(tau=0.9).values_list("serie_id", "unidades"))
    top = [{"serie": a.serie, "serie_id": a.serie_id, "mediana": a.unidades, "q90": q90.get(a.serie_id, 0)} for a in top_qs]

    # serie elegida (por defecto, la de mayor demanda esperada de la selección)
    try:
        serie_id = int(request.GET.get("serie", ""))
    except ValueError:
        serie_id = top[0]["serie_id"] if top else None
    serie = series.filter(id=serie_id).first() if serie_id else None
    if serie is None and top:
        serie = top[0]["serie"]
    grafica = None
    if serie:
        hist = list(VentaDiaria.objects.filter(serie=serie, fecha__gt=lgbm.fecha_origen - timedelta(days=84)).order_by("fecha").values_list("fecha", "unidades"))
        modelos = {}
        for nombre, c in (("lightgbm", lgbm), ("tft", tft)):
            if c:
                f = list(Prediccion.objects.filter(corrida=c, serie=serie).order_by("fecha").values_list("fecha", "p10", "p50", "p90"))
                modelos[nombre] = {"fechas": [x[0].isoformat() for x in f], "p10": [round(x[1], 2) for x in f], "p50": [round(x[2], 2) for x in f], "p90": [round(x[3], 2) for x in f]}
        grafica = {"hist": {"fechas": [h[0].isoformat() for h in hist], "y": [h[1] for h in hist]}, "modelos": modelos}
    contexto.update({"tienda": tienda, "categoria": categoria, "mediana": mediana, "alto": alto, "n_series": len(ids), "por_categoria": por_categoria, "top": top,
                     "serie": serie, "grafica": grafica, "tiene_tft": bool(tft), "fecha_origen": lgbm.fecha_origen,
                     "datos_categoria": {"etiquetas": [x["serie__departamento__categoria__codigo"] for x in por_categoria], "valores": [round(x["t"]) for x in por_categoria]}})
    return render(request, "panel/proyecciones.html", contexto)


# ----------------------------------------------------------------------------------------------- Reposición
def calcular_reposicion(objetivo, mediana, inventario):
    """Pedido sugerido = stock objetivo - inventario actual (si no hay inventario registrado, se asume 0)."""
    if inventario is None:
        return objetivo, "sin", "Sin inventario"
    pedido = max(0.0, objetivo - inventario)
    if inventario < mediana:
        return pedido, "riesgo", "Riesgo de quiebre"
    if inventario > 1.5 * objetivo:
        return pedido, "sobre", "Sobreinventario"
    return pedido, "ok", "Adecuado"


def reposicion(request):
    agg = corrida_activa("lgbm_agregado")
    contexto = {"seccion": "reposicion", "hay_datos": bool(agg), "niveles": NIVELES, **_opciones_filtros()}
    if not agg:
        return render(request, "panel/reposicion.html", contexto)
    try:
        nivel = float(str(request.GET.get("nivel", 0.9)).replace(",", "."))
    except ValueError:
        nivel = 0.9
    nivel = nivel if nivel in NIVELES else 0.9
    politica = request.GET.get("politica", "28d")
    politica = politica if politica in ("28d", "semanal") else "28d"
    estado, q = request.GET.get("estado", ""), request.GET.get("q", "").strip()

    series, tienda, categoria = _series_filtradas(request)
    if q:
        series = series.filter(item_id__icontains=q)
    sugerencias = {s.serie_id: s for s in SugerenciaReposicion.objects.filter(corrida=agg, politica=politica, nivel_servicio=nivel)}
    inventario = dict(InventarioActual.objects.values_list("serie_id", "unidades"))
    filas = []
    for s in series:
        sg = sugerencias.get(s.id)
        if not sg:
            continue
        inv = inventario.get(s.id)
        pedido, clave, etiqueta = calcular_reposicion(sg.stock_objetivo, sg.demanda_mediana, inv)
        filas.append({"serie": s, "mediana": sg.demanda_mediana, "objetivo": sg.stock_objetivo, "inventario": inv, "pedido": pedido, "clave": clave, "etiqueta": etiqueta})
    resumen = {"riesgo": sum(f["clave"] == "riesgo" for f in filas), "sobre": sum(f["clave"] == "sobre" for f in filas),
               "sin": sum(f["clave"] == "sin" for f in filas), "pedido": sum(f["pedido"] for f in filas), "total": len(filas)}
    if estado in ("riesgo", "sobre", "ok", "sin"):
        filas = [f for f in filas if f["clave"] == estado]
    filas.sort(key=lambda f: f["pedido"], reverse=True)
    pagina = Paginator(filas, 25).get_page(request.GET.get("pagina"))
    consulta = request.GET.copy(); consulta.pop("pagina", None)
    contexto.update({"tienda": tienda, "categoria": categoria, "nivel": nivel, "politica": politica, "estado": estado, "q": q, "pagina": pagina, "resumen": resumen,
                     "consulta": consulta.urlencode(), "fecha_origen": agg.fecha_origen, "hay_simulados": InventarioActual.objects.filter(simulado=True).exists()})
    return render(request, "panel/reposicion.html", contexto)


@require_POST
def actualizar_inventario(request):
    """Guarda el inventario actual de una serie y devuelve el nuevo pedido sugerido (sin recalcular ningún modelo)."""
    try:
        datos = json.loads(request.body)
        serie_id, unidades = int(datos["serie_id"]), datos.get("unidades")
        nivel, politica = float(datos["nivel"]), datos["politica"]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Datos no válidos."}, status=400)
    agg = corrida_activa("lgbm_agregado")
    sg = get_object_or_404(SugerenciaReposicion, corrida=agg, serie_id=serie_id, politica=politica, nivel_servicio=nivel) if agg else None
    if sg is None:
        raise Http404
    if unidades in (None, ""):
        InventarioActual.objects.filter(serie_id=serie_id).delete()
        inv = None
    else:
        inv = max(0, int(float(unidades)))
        InventarioActual.objects.update_or_create(serie_id=serie_id, defaults={"unidades": inv, "simulado": False})
    pedido, clave, etiqueta = calcular_reposicion(sg.stock_objetivo, sg.demanda_mediana, inv)
    return JsonResponse({"pedido": round(pedido), "clave": clave, "etiqueta": etiqueta})


# ----------------------------------------------------------------------------------------------- Modelos
def _tarea_a_dict(t, con_registro=False):
    d = {"id": t.id, "comando": t.comando, "titulo": t.get_comando_display(), "estado": t.estado, "estado_texto": t.get_estado_display(),
         "inicio": timezone.localtime(t.inicio).strftime("%d/%m %H:%M") if t.inicio else "", "resumen": t.resumen, "parametros": t.parametros,
         "duracion": str(t.duracion).split(".")[0] if t.duracion else ""}
    if con_registro:
        d["registro"] = tareas.cola_del_registro(t)
    return d


def modelos(request):
    ultimas = [tareas.refrescar(t) for t in EjecucionTarea.objects.all()[:8]]
    metricas = {}
    for m in MetricaModelo.objects.filter(segmento="global"):
        metricas.setdefault(m.modelo, {})[m.metrica] = m.valor
    tabla = [{"modelo": k, "etiqueta": ETIQUETAS_MODELO.get(k, k), **v} for k, v in metricas.items()]
    tabla.sort(key=lambda r: r.get("MASE_medio", 99))
    contexto = {"seccion": "modelos", "tareas": [_tarea_a_dict(t) for t in ultimas], "corridas": CorridaModelo.objects.all()[:12], "tabla": tabla,
                "grafica_mase": {"etiquetas": [r["etiqueta"] for r in tabla], "valores": [round(r.get("MASE_medio", 0), 3) for r in tabla]},
                "en_curso": {c: bool(tareas.en_curso(c)) for c in tareas.COMANDOS}}
    return render(request, "panel/modelos.html", contexto)


@require_POST
def lanzar_tarea(request):
    comando = request.POST.get("comando", "")
    if comando not in tareas.COMANDOS:
        return JsonResponse({"error": "Comando no permitido."}, status=400)
    try:
        pasos = int(request.POST.get("pasos", 1500))
    except ValueError:
        pasos = 1500
    t, nueva = tareas.lanzar(comando, pasos)
    return JsonResponse({"id": t.id, "nueva": nueva})


@require_GET
def estado_tareas(request):
    ultimas = [tareas.refrescar(t) for t in EjecucionTarea.objects.all()[:8]]
    return JsonResponse({"tareas": [_tarea_a_dict(t, con_registro=t.estado == "ejecutando") for t in ultimas]})


@require_GET
def registro_tarea(request, tarea_id):
    t = get_object_or_404(EjecucionTarea, pk=tarea_id)
    return JsonResponse(_tarea_a_dict(t, con_registro=True))


def perfil_usuario(request):
    """Perfil del usuario: nombre para mostrar, sexo (define el avatar) y cambio de contraseña."""
    from django.contrib import messages
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.forms import PasswordChangeForm

    from .models import Perfil
    p, _ = Perfil.objects.get_or_create(usuario=request.user)
    form_clave = PasswordChangeForm(request.user)
    if request.method == "POST":
        if request.POST.get("accion") == "clave":
            form_clave = PasswordChangeForm(request.user, request.POST)
            if form_clave.is_valid():
                update_session_auth_hash(request, form_clave.save())
                messages.success(request, "Contraseña actualizada.")
                return redirect("perfil")
        else:
            p.nombre_mostrado = request.POST.get("nombre", "").strip()[:60]
            if request.POST.get("sexo") in ("F", "M", "N"):
                p.sexo = request.POST["sexo"]
            p.save()
            messages.success(request, "Perfil guardado.")
            return redirect("perfil")
    return render(request, "panel/perfil.html", {"seccion": "perfil", "form_clave": form_clave, "sexos": Perfil.SEXOS})
