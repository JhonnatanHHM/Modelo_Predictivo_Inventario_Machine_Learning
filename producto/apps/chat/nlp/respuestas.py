"""Respuestas del chat. Cada intención llama a consultas ya escritas sobre la base de datos (el texto del usuario nunca se convierte en SQL)
y rellena una frase plantilla con los números reales. Cada función devuelve un dict: texto, y opcionalmente columnas/filas, enlace, sugerencias u opciones."""
import re
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Count, Max, Min, Sum
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import Categoria, Departamento, Serie, Tienda, VentaDiaria
from apps.pronosticos.models import (CorridaModelo, EjecucionTarea, InventarioActual, MetricaModelo, Prediccion, PrediccionAgregada, SugerenciaReposicion)

FUERA = "Disculpa, pero ese tema se sale del contexto del aplicativo, solo estoy autorizado para responder en contexto del aplicativo."
NOMBRES_INTENCION = {"catalogo": "Tiendas, categorías y datos disponibles", "accion_no_soportada": "Una acción (no disponible en el chat)", "ventas_pasadas": "Ventas ya registradas", "demanda_esperada": "Demanda esperada (futuro)", "rango_proyeccion": "Rango de la proyección", "cuanto_pedir": "Cuánto pedir",
                     "riesgo_quiebre": "Riesgo de quiebre", "sobreinventario": "Sobreinventario", "top_productos": "Productos con más demanda",
                     "comparar_modelos": "Comparación de modelos", "estado_modelo": "Estado de las predicciones", "inventario_actual": "Inventario actual", "glosario": "Qué significa un término"}
EJEMPLOS = ["¿Qué productos se vendieron más el último mes registrado?", "¿Cuánto se va a vender de FOODS_2_398 en WI_2 el próximo mes?", "¿Cuánto debo pedir de HOUSEHOLD con 95 % de servicio?", "¿Qué productos están en riesgo de quiebre en Texas?",
            "¿Cuáles son los 5 productos con más demanda en CA_1?", "¿Cuál modelo es mejor, el TFT o LightGBM?", "¿Qué significa nivel de servicio?", "¿Cuándo se actualizaron las predicciones?"]

GLOSARIO = {
    "p10": "P10 es el valor por debajo del cual cae la demanda diaria solo el 10 % de las veces. Como muchos días no se vende nada, el P10 suele ser 0.",
    "p50": "P50 (la mediana) es el valor que la demanda supera la mitad de las veces: el escenario más típico, aunque suele quedar por debajo del promedio porque hay días de ventas muy altas.",
    "p90": "P90 es el valor que la demanda solo supera el 10 % de las veces: un escenario alto. Sirve para decidir cuánto stock tener y evitar quedarse sin producto.",
    "nivel de servicio": "El nivel de servicio es la probabilidad de poder atender toda la demanda sin quedarse sin stock. Con 90 %, el stock objetivo es el valor que la demanda total solo supera el 10 % de las veces. Más servicio significa más unidades guardadas.",
    "stock objetivo": "El stock objetivo es la cantidad de unidades que conviene tener al inicio del periodo para cubrir la demanda con el nivel de servicio elegido (por ejemplo, el cuantil 0,9 de la demanda total).",
    "pedido sugerido": "El pedido sugerido es el stock objetivo menos el inventario actual (nunca menos de 0). Si no hay inventario registrado, se muestra el stock objetivo completo.",
    "quiebre": "Un quiebre de stock ocurre cuando se agota un producto y hay demanda que no se puede atender (ventas perdidas). En el panel se marca «riesgo de quiebre» cuando el inventario es menor que la demanda mediana del periodo.",
    "sobreinventario": "Hay sobreinventario cuando el inventario supera con mucho lo necesario (aquí, más de 1,5 veces el stock objetivo): capital inmovilizado y, en perecederos, desperdicio.",
    "cobertura": "La cobertura de un intervalo es el porcentaje de veces que la venta real cae dentro del rango pronosticado. Para el intervalo P10 a P90 lo ideal es 80 %.",
    "mase": "El MASE compara el error del modelo con el de una regla simple (repetir lo de la semana anterior). Menor es mejor y por debajo de 1 significa que el modelo supera esa regla.",
    "pinball": "La pérdida pinball mide qué tan buenos son los cuantiles pronosticados (P10, P50, P90): penaliza más quedarse corto en los altos y pasarse en los bajos. Menor es mejor.",
    "cuantil": "Un cuantil es un valor de corte: el cuantil 0,9 es el valor que deja por debajo al 90 % de los casos. El sistema pronostica varios cuantiles en vez de un solo número para medir la incertidumbre.",
    "mediana": "La mediana de la demanda es el valor central: la mitad de las veces se vende más y la otra mitad menos.",
    "tft": "El TFT (Temporal Fusion Transformer) es una red neuronal para series de tiempo que usa calendario, precios y eventos, y entrega los cuantiles P10, P50 y P90 de los próximos 28 días.",
    "lightgbm": "LightGBM es un modelo de árboles de decisión muy rápido. Aquí se entrena para predecir los cuantiles diarios y también el cuantil de la demanda total, que es el que se usa para reponer.",
    "ets": "ETS es un modelo estadístico clásico de suavizamiento exponencial; se usa como referencia para comparar.",
    "naive": "El modelo naive repite lo vendido en la misma fecha de la semana anterior; es la referencia más simple.",
    "demanda esperada": "La demanda esperada es la mediana de lo que se prevé vender en el periodo; junto a ella se muestran escenarios altos (P80, P90, P95).",
    "proyeccion": "La proyección es el pronóstico de ventas de los próximos 28 días, con su rango de incertidumbre.",
}
SINONIMOS_GLOSARIO = {"nivel de servicio": ["servicio"], "stock objetivo": ["objetivo"], "pedido sugerido": ["pedido", "reposicion"], "quiebre": ["quiebre", "agotarse", "faltante"],
                      "sobreinventario": ["sobreinventario", "exceso", "sobrestock"], "cobertura": ["cobertura"], "proyeccion": ["proyeccion", "pronostico"], "demanda esperada": ["demanda esperada"]}


def fmt(n):
    return f"{n:,.0f}".replace(",", ".")


def _activa(tipo):
    return CorridaModelo.objects.filter(tipo=tipo, activa=True, es_futuro_real=True).order_by("-creada").first()


def _sin_predicciones():
    return {"texto": "Todavía no hay predicciones guardadas. Ve a la pestaña Modelos y pulsa «Generar predicciones»; tarda cerca de un minuto.",
            "enlace": {"texto": "Ir a Modelos", "url": reverse("modelos")}}


def _enlace(nombre, texto, **params):
    q = urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return {"texto": texto, "url": reverse(nombre) + (f"?{q}" if q else "")}


def _alcance(ctx):
    """Devuelve (queryset de series, descripción, error). Valida contra los datos reales."""
    tiendas = list(Tienda.objects.values_list("codigo", flat=True))
    tienda = ctx.get("tienda")
    if tienda and tienda not in tiendas:
        return None, "", f"No tengo datos de la tienda {tienda}. Las tiendas disponibles son {', '.join(tiendas)}."
    qs = Serie.objects.select_related("tienda", "departamento__categoria")
    partes = []
    if ctx.get("producto"):
        qs = qs.filter(item_id=ctx["producto"])
        if not qs.exists():
            return None, "", f"No encontré el producto {ctx['producto']} en los datos: el aplicativo trabaja con un subconjunto de {Serie.objects.count()} series (producto-tienda), así que ese puede no estar incluido. Pregúntame por los productos de un departamento y te muestro los que sí hay."
        partes.append(ctx["producto"])
    elif ctx.get("departamento"):
        qs = qs.filter(departamento__codigo=ctx["departamento"])
        if not qs.exists():
            return None, "", f"No encontré el departamento {ctx['departamento']} en los datos."
        partes.append(f"el departamento {ctx['departamento']}")
    elif ctx.get("categoria"):
        qs = qs.filter(departamento__categoria__codigo=ctx["categoria"])
        partes.append(f"la categoría {ctx['categoria']}")
    if tienda:
        qs = qs.filter(tienda__codigo=tienda)
        if not qs.exists():
            return None, "", f"No hay series de ese producto o categoría en la tienda {tienda}."
        partes.append(f"en {tienda}" if partes else f"la tienda {tienda}")
    return qs, " ".join(partes) if partes else "todas las tiendas y categorías", None


def _horizonte(ctx, agg):
    """(clave de PrediccionAgregada o None, texto del periodo, días si es parcial)."""
    h = ctx.get("horizonte") or {"tipo": "28d"}
    inicio = agg.fecha_origen + timedelta(days=1)
    f = lambda d: d.strftime("%d/%m/%Y")
    if h["tipo"] == "semana":
        n = min(max(h["n"], 1), 4)
        a = inicio + timedelta(days=7 * (n - 1))
        return f"sem{n}", f"de la semana {n} (del {f(a)} al {f(a + timedelta(days=6))})", None
    if h["tipo"] == "dias":
        k = min(h["n"], 28)
        return None, f"de los próximos {k} días (del {f(inicio)} al {f(inicio + timedelta(days=k - 1))})", k
    return "28d", f"de los próximos 28 días (del {f(inicio)} al {f(inicio + timedelta(days=27))})", None


def _suma_agregada(agg, ids, clave, tau):
    return PrediccionAgregada.objects.filter(corrida=agg, serie_id__in=ids, horizonte=clave, tau=tau).aggregate(t=Sum("unidades"))["t"] or 0


def _nivel(ctx):
    return ctx.get("nivel") or 0.9


# ------------------------------------------------------------------------------------------------ intenciones
MESES_NOMBRE = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo"}
GRUPOS = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}


def _periodo_pasado(pasado, primero, ultimo):
    """(desde, hasta, nombre, desde_previo, hasta_previo) según lo pedido: últimos N días, un mes, lo que va del mes, el año o todo el histórico."""
    import calendar
    from datetime import date
    pasado = pasado or {}
    if pasado.get("mes_anio"):
        import calendar
        from datetime import date
        m, y = pasado["mes_anio"]
        desde = date(y, m, 1)
        hasta = min(date(y, m, calendar.monthrange(y, m)[1]), ultimo)
        previo = desde - timedelta(days=1)
        return desde, hasta, f"{MESES_TODOS[m]} de {y}", previo.replace(day=1), previo
    if pasado.get("meses"):
        m = pasado["meses"][0]
        desde = date(ultimo.year, m, 1)
        hasta = min(date(ultimo.year, m, calendar.monthrange(ultimo.year, m)[1]), ultimo)
        previo = date(ultimo.year, m, 1) - timedelta(days=1)
        return desde, hasta, f"{MESES_NOMBRE[m]} de {ultimo.year}", previo.replace(day=1), previo
    if pasado.get("mtd"):
        desde = ultimo.replace(day=1)
        previo = desde - timedelta(days=1)
        return desde, ultimo, f"lo que va de {MESES_NOMBRE.get(ultimo.month, 'este mes')}", previo.replace(day=1), previo.replace(day=min(ultimo.day, previo.day))
    if pasado.get("anio"):
        y = pasado["anio"]
        hasta = ultimo if y == ultimo.year else date(y, 12, 31)
        return date(y, 1, 1), hasta, f"{y}" + (" hasta el último día registrado" if y == ultimo.year else ""), date(y - 1, 1, 1), date(y - 1, 12, 31)
    if pasado.get("todo"):
        return primero, ultimo, "todo el histórico", None, None
    n = min(pasado.get("n", 28), 365)
    desde = ultimo - timedelta(days=n - 1)
    nombre = "el último día registrado" if n == 1 else "la última semana" if n == 7 else "el último mes registrado" if n == 28 else "el último trimestre registrado" if n == 91 else f"los últimos {n} días"
    return desde, ultimo, nombre, desde - timedelta(days=n), desde - timedelta(days=1)


DIAS_SEMANA = {1: "domingo", 2: "lunes", 3: "martes", 4: "miércoles", 5: "jueves", 6: "viernes", 7: "sábado"}     # ExtractWeekDay de Django: 1 = domingo
MESES_TODOS = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}


def fmt1(x):
    """Promedios: dos decimales si son menores que 1 (0,05), uno en los demás (12,8)."""
    return (f"{x:,.2f}" if abs(x) < 1 else f"{x:,.1f}").replace(",", "§").replace(".", ",").replace("§", ".")


def unid(valor_texto, promedio=False):
    """«1 unidad» / «2 unidades» (y «por día en promedio» si es un promedio)."""
    sufijo = " por día en promedio" if promedio else ""
    return f"{valor_texto} unidad{sufijo}" if valor_texto == "1" else f"{valor_texto} unidades{sufijo}"


def en_(desc):
    """« en la tienda CA_1» o, si la selección es todo, nada (evita «en todas las tiendas y categorías» donde sobra)."""
    return "" if desc.startswith("todas las") else f" en {desc}"


def ventas_pasadas(ctx, info):
    """Ventas reales ya registradas (no proyecciones): total o promedio por día de un periodo, rankings de lo que más o menos vendió (productos, tiendas,
    categorías, departamentos) y de qué día de la semana, mes o fecha se vendió más o menos."""
    from django.db.models import Count
    from django.db.models.functions import ExtractMonth, ExtractWeekDay
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    limites = VentaDiaria.objects.aggregate(m=Max("fecha"), p=Min("fecha"))
    ultimo = limites["m"]
    if not ultimo:
        return {"texto": "No hay ventas cargadas en la base. Ejecuta «python manage.py cargar_datos»."}
    f = lambda d: d.strftime("%d/%m/%Y")
    ents = info["entidades"]
    pasado = ctx.get("pasado") or {}
    ids = list(qs.values_list("id", flat=True))
    buscar = ents.get("buscar")
    asc = ents.get("orden") == "asc"
    promedio = ents.get("metrica") == "promedio"
    agrupar = ents.get("agrupar")
    tiempo_dim = agrupar in ("dia_semana", "mes", "fecha")
    explicito = ents.get("pasado") and not ents["pasado"].get("generico")                     # «se vendió» o «ese día» solos no fijan el periodo
    if (promedio or tiempo_dim) and not explicito and not pasado.get("fecha"):               # sin un periodo explícito, un promedio o un «qué mes / qué día» mira todo el histórico
        pasado = {"todo": True}
    if pasado.get("anio") and not (limites["p"].year <= pasado["anio"] <= ultimo.year):
        return {"texto": f"Mis ventas van del {f(limites['p'])} al {f(ultimo)}; no hay datos de {pasado['anio']}."}
    if pasado.get("ultima_venta"):                                   # «el último día que haya vendido algo»: la última fecha con ventas de la selección
        d = VentaDiaria.objects.filter(serie_id__in=ids, unidades__gt=0).aggregate(m=Max("fecha"))["m"]
        pasado = {"fecha": (d or ultimo).isoformat(), "etiqueta": "el último día con ventas"}
    if pasado.get("fecha"):                                          # un día exacto (también el que se recuerda como «ese día»)
        from datetime import date
        d = date.fromisoformat(pasado["fecha"])
        desde, ultimo_p, nombre, desde_prev, hasta_prev = d, d, pasado.get("etiqueta", "ese día"), d - timedelta(days=1), d - timedelta(days=1)
    else:
        desde, ultimo_p, nombre, desde_prev, hasta_prev = _periodo_pasado(pasado, limites["p"], ultimo)
    n = (ultimo_p - desde).days + 1
    if n < 1 or desde > limites["m"]:
        return {"texto": f"Ese periodo queda fuera de mis datos: las ventas registradas van del {f(limites['p'])} al {f(limites['m'])}."}
    fijar = {"_ctx": {"pasado": {"fecha": desde.isoformat(), "etiqueta": "ese día"}}} if n == 1 else {}
    if len(pasado.get("meses") or []) == 2:                          # comparación de dos meses: "abril contra marzo"
        a, b = pasado["meses"]
        tot = lambda m: VentaDiaria.objects.filter(serie_id__in=ids, fecha__year=ultimo.year, fecha__month=m).aggregate(t=Sum("unidades"))["t"] or 0
        ta, tb = tot(a), tot(b)
        cambio = f"{abs(round(100 * (ta - tb) / tb))} % {'más' if ta >= tb else 'menos'}" if tb else "sin base de comparación"
        return {"texto": f"En {desc}: en {MESES_NOMBRE[a]} se vendieron {fmt(ta)} unidades y en {MESES_NOMBRE[b]} {fmt(tb)}; {MESES_NOMBRE[a]} fue {cambio} que {MESES_NOMBRE[b]}.",
                "enlace": _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"))}
    ventas = VentaDiaria.objects.filter(serie_id__in=ids, fecha__range=(desde, ultimo_p))
    total = ventas.aggregate(t=Sum("unidades"))["t"] or 0
    if not ventas.exists():
        return {"texto": f"No hay ventas registradas de {desc} entre el {f(desde)} y el {f(ultimo_p)}."}
    previo = VentaDiaria.objects.filter(serie_id__in=ids, fecha__range=(desde_prev, hasta_prev)).aggregate(t=Sum("unidades"))["t"] or 0 if desde_prev else 0
    cambio = f" Frente al periodo anterior ({fmt(previo)} unidades), es un {abs(round(100 * (total - previo) / previo))} % {'más' if total >= previo else 'menos'}." if previo and n > 1 else ""
    ultimo = ultimo_p
    rango = f"del {f(desde)} al {f(ultimo)}" if desde != ultimo else f"el {f(ultimo)}"
    # El aviso solo aporta si el periodo no termina en el último día cargado; si termina ahí, basta con decir que son ventas reales.
    aviso = " (Son ventas reales registradas.)" if ultimo == limites["m"] else f" (Son ventas reales registradas; el último día cargado es el {f(limites['m'])}.)"
    cant = min(ents.get("cantidad") or (5 if buscar and buscar.get("plural") else 1 if buscar else 5), 15)
    mas_menos = "menos" if asc else "más"
    enlace = _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"))

    # ---- qué día de la semana, qué mes o qué fecha
    if tiempo_dim:
        if agrupar == "fecha":
            g = list(ventas.values("fecha").annotate(t=Sum("unidades")).order_by("t" if asc else "-t")[:cant])
            filas = [[f(x["fecha"]), fmt(x["t"])] for x in g]
            return {"texto": f"En {nombre} ({rango}), el día con {mas_menos} ventas{en_(desc)} fue el {filas[0][0]}, con {unid(filas[0][1])}.{aviso}", "columnas": ["Día", "Unidades vendidas"], "filas": filas, "enlace": enlace}
        campo, nombres, etiqueta = (ExtractWeekDay("fecha"), DIAS_SEMANA, "día de la semana") if agrupar == "dia_semana" else (ExtractMonth("fecha"), MESES_TODOS, "mes")
        g = list(ventas.annotate(g=campo).values("g").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
        usar_promedio = promedio or agrupar == "dia_semana"           # un total por día de la semana depende de cuántos hay de cada uno: se compara el promedio por día
        medida = lambda x: x["t"] / x["d"] if usar_promedio else x["t"]
        g.sort(key=medida, reverse=not asc)
        filas = [[nombres[x["g"]].capitalize(), fmt1(medida(x)) if usar_promedio else fmt(medida(x))] for x in g]
        unidad = "unidades por día en promedio" if usar_promedio else "unidades en total (sumando todos los años)" if agrupar == "mes" else "unidades"
        return {"texto": f"En {nombre} ({rango}), el {etiqueta} con {mas_menos} ventas{en_(desc)} es {filas[0][0].lower()}, con {filas[0][1]} {unidad}.{aviso}",
                "columnas": [etiqueta.capitalize(), "Promedio por día" if usar_promedio else "Unidades vendidas"], "filas": filas, "enlace": enlace}

    # ---- qué tienda, categoría o departamento
    if agrupar in GRUPOS and not buscar and not ctx.get({"tienda": "tienda", "categoria": "categoria", "departamento": "departamento"}[agrupar]):
        g = list(ventas.values(GRUPOS[agrupar]).annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
        medida = lambda x: x["t"] / x["d"] if promedio else x["t"]
        g.sort(key=medida, reverse=not asc)
        etiqueta = {"categoria": "categoría"}.get(agrupar, agrupar)
        filas = [[x[GRUPOS[agrupar]], fmt1(medida(x)) if promedio else fmt(medida(x))] for x in g]
        return {"texto": f"En {nombre} ({rango}), la {etiqueta} que {mas_menos} vendió{en_(desc)} fue {filas[0][0]}, con {unid(filas[0][1], promedio)}.{aviso}",
                "columnas": [etiqueta.capitalize(), "Promedio por día" if promedio else "Unidades vendidas"], "filas": filas, "enlace": enlace}

    # ---- «promedio de ventas por día de HOBBIES»: la cifra agregada, no un ranking
    pide_ranking = bool(ents.get("orden") or ents.get("cantidad") or buscar or re.search(r"\b(?:mas|menos|top|mejor|mejores|peor|peores|cada|ranking|productos|articulos)\b", info["normalizado"]))
    if promedio and len(ids) > 1 and not pide_ranking:
        dias = ventas.values("fecha").distinct().count() or 1
        sujeto = "se vendieron en total" if desc.startswith("todas las") else f"{desc} vendió"
        return {"texto": f"En {nombre} ({rango}), {sujeto} unas {fmt1(total / dias)} unidades por día en promedio ({fmt(total)} unidades en {fmt(dias)} días).{aviso}", "enlace": enlace}

    # ---- una sola serie
    if len(ids) == 1:
        por_dia = f", unas {fmt1(total / n)} por día" if n > 1 else ""                  # el promedio diario no aporta nada si el periodo es un solo día
        texto = f"En {nombre} ({rango}), {desc} vendió {fmt(total)} unidades{por_dia}.{cambio}{aviso}"
        return {"texto": texto, "columnas": None, "filas": None, **fijar,
                "enlace": _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"), serie=qs.first().id)}

    # ---- ranking de productos (más o menos vendidos, por total o por promedio diario)
    series = {s.id: s for s in qs}
    g = list(ventas.values("serie_id").annotate(t=Sum("unidades"), d=Count("id")))
    medida = lambda x: x["t"] / x["d"] if promedio else x["t"]
    g.sort(key=medida, reverse=not asc)
    g = g[:cant]
    filas = [[series[x["serie_id"]].item_id, series[x["serie_id"]].tienda.codigo, fmt1(medida(x)) if promedio else fmt(medida(x)), series[x["serie_id"]].departamento.codigo] for x in g]
    if cant == 1 and filas:
        texto = (f"El producto que {mas_menos} {'vendió' if promedio else 'se vendió'} en {nombre} ({rango}){en_(desc)} fue {filas[0][0]}, en la tienda {filas[0][1]}, con {unid(filas[0][2], promedio)}. "
                 f"En total, {desc} vendió {fmt(total)} unidades en ese periodo.{aviso}")
    else:
        texto = (f"En {nombre} ({rango}), {desc} vendió {fmt(total)} unidades ({len(ids)} series).{cambio}{aviso} "
                 f"Los {len(filas)} productos que {mas_menos} vendieron" + (" (promedio por día)" if promedio else "") + ":")
    return {"texto": texto, "columnas": ["Producto", "Tienda", "Promedio por día" if promedio else "Unidades vendidas", "Departamento"], "filas": filas, **fijar, "enlace": enlace}


def demanda_esperada(ctx, info):
    agg = _activa("lgbm_agregado")
    if not agg:
        return _sin_predicciones()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    clave, periodo, dias = _horizonte(ctx, agg)
    if dias:
        lg = _activa("lightgbm")
        pred = Prediccion.objects.filter(corrida=lg, serie_id__in=ids, fecha__lte=lg.fecha_origen + timedelta(days=dias))
        med, alto = (pred.aggregate(t=Sum("p50"))["t"] or 0), (pred.aggregate(t=Sum("p90"))["t"] or 0)
        nota = "Es la suma de los pronósticos diarios (mediana y P90)."
    else:
        med, alto = _suma_agregada(agg, ids, clave, 0.5), _suma_agregada(agg, ids, clave, _nivel(ctx))
        nota = ""
    filas = None
    if ctx.get("producto") and not ctx.get("tienda") and len(ids) > 1:                  # el mismo producto en varias tiendas
        filas = [[s.tienda.codigo, fmt(_suma_agregada(agg, [s.id], clave, 0.5) if clave else 0), fmt(_suma_agregada(agg, [s.id], clave, _nivel(ctx)) if clave else 0)] for s in qs]
    if len(ids) == 1:
        texto = f"Para {desc}, la demanda esperada {periodo} es de unas {fmt(med)} unidades (mediana). Con {round((_nivel(ctx) if clave else 0.9) * 100)} % de servicio conviene contar con {fmt(alto)}."
    else:
        texto = (f"Para {desc} ({len(ids)} series), la demanda esperada {periodo} es de unas {fmt(med)} unidades (suma de las medianas). "
                 f"Sumando el escenario de {round((_nivel(ctx) if clave else 0.9) * 100)} % de servicio de cada serie, {fmt(alto)}. {nota}").strip()
    return {"texto": texto, "columnas": ["Tienda", "Mediana", f"{round(_nivel(ctx) * 100)} % de servicio"] if filas else None, "filas": filas,
            "enlace": _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"), categoria=ctx.get("categoria") or (qs.first().departamento.categoria.codigo if ctx.get("departamento") or ctx.get("producto") else None),
                              serie=qs.first().id if len(ids) == 1 else None)}


def rango_proyeccion(ctx, info):
    agg = _activa("lgbm_agregado")
    if not agg:
        return _sin_predicciones()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    clave, periodo, dias = _horizonte(ctx, agg)
    if dias:
        clave, periodo = "28d", "de los próximos 28 días"
    filas = [[f"{round(t * 100)} %", fmt(_suma_agregada(agg, ids, clave, t))] for t in (0.5, 0.8, 0.9, 0.95)]
    filas[0][0] = "Más probable (mediana)"
    texto = (f"Para {desc}, el rango de la demanda {periodo}: lo más probable es {filas[0][1]} unidades; con 80 % de probabilidad no pasará de {filas[1][1]}, "
             f"con 90 % de {filas[2][1]} y con 95 % de {filas[3][1]}.")
    if len(ids) > 1:
        texto += " Con varias series se suman los valores de cada una, lo que da una cota conservadora."
    return {"texto": texto, "columnas": ["Escenario (probabilidad de no superarlo)", "Unidades"], "filas": filas,
            "enlace": _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"), serie=qs.first().id if len(ids) == 1 else None)}


def _inventarios(ids):
    return dict(InventarioActual.objects.filter(serie_id__in=ids).values_list("serie_id", "unidades"))


def cuanto_pedir(ctx, info):
    agg = _activa("lgbm_agregado")
    if not agg:
        return _sin_predicciones()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    nivel = _nivel(ctx)
    ids = list(qs.values_list("id", flat=True))
    h = ctx.get("horizonte") or {}
    clave, periodo, dias = _horizonte({"horizonte": h if h.get("tipo") in ("semana", "28d") else {"tipo": "28d"}}, agg)
    objetivos = dict(PrediccionAgregada.objects.filter(corrida=agg, serie_id__in=ids, horizonte=clave, tau=nivel).values_list("serie_id", "unidades"))
    usa_inventario = clave in ("28d", "sem1")
    inv = _inventarios(ids) if usa_inventario else {}
    objetivo_total = sum(objetivos.values())
    pedidos = {s: max(0.0, o - inv.get(s, 0)) for s, o in objetivos.items()}
    pedido_total = sum(pedidos.values())
    sin_inv = sum(1 for s in objetivos if s not in inv)
    nota_nivel = f"{round(nivel * 100)} % de servicio"
    if len(ids) == 1:
        s = qs.first()
        if s.id in inv:
            texto = (f"Para {desc}, para cubrir la demanda {periodo} con {nota_nivel} conviene tener {fmt(objetivo_total)} unidades. Tienes {fmt(inv[s.id])} registradas, "
                     f"así que el pedido sugerido es de {fmt(pedido_total)} unidades.")
        else:
            texto = (f"Para {desc}, para cubrir la demanda {periodo} con {nota_nivel} conviene tener {fmt(objetivo_total)} unidades. "
                     + ("No hay inventario registrado, así que el pedido sugerido sería ese total." if usa_inventario else "El inventario actual solo se descuenta en el primer periodo."))
        filas = None
    else:
        orden = sorted(pedidos, key=pedidos.get, reverse=True)[:5]
        series = {s.id: s for s in qs}
        filas = [[series[i].item_id, series[i].tienda.codigo, fmt(objetivos[i]), fmt(inv[i]) if i in inv else "—", fmt(pedidos[i])] if usa_inventario
                 else [series[i].item_id, series[i].tienda.codigo, fmt(objetivos[i])] for i in orden]
        texto = (f"Para {desc} ({len(ids)} series), para cubrir la demanda {periodo} con {nota_nivel} el stock objetivo total es de {fmt(objetivo_total)} unidades"
                 + (f" y el pedido sugerido de {fmt(pedido_total)}" if usa_inventario else "") + ".")
        if usa_inventario and sin_inv:
            texto += f" {sin_inv} series no tienen inventario registrado y se toman con 0 unidades."
        texto += " Estas son las 5 con mayor " + ("pedido:" if usa_inventario else "stock objetivo:")
    return {"texto": texto, "columnas": (["Producto", "Tienda", "Stock objetivo", "Inventario", "Pedido"] if usa_inventario else ["Producto", "Tienda", "Stock objetivo"]) if filas else None, "filas": filas,
            "enlace": _enlace("reposicion", "Ver en Reposición", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"), nivel=nivel, q=ctx.get("producto"))}


def _riesgos(ctx, info, sobre):
    agg = _activa("lgbm_agregado")
    if not agg:
        return _sin_predicciones()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    inv = _inventarios(ids)
    if not inv:
        return {"texto": "No hay inventarios registrados para esa selección, así que no puedo evaluar el riesgo. Registra el inventario actual en la pestaña Reposición (o usa el comando de demostración).",
                "enlace": _enlace("reposicion", "Ir a Reposición", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"))}
    sug = {s.serie_id: s for s in SugerenciaReposicion.objects.filter(corrida=agg, serie_id__in=inv, politica="28d", nivel_servicio=0.9)}
    series = {s.id: s for s in qs}
    casos = []
    for sid, u in inv.items():
        sg = sug.get(sid)
        if not sg:
            continue
        if sobre and u > 1.5 * sg.stock_objetivo:
            casos.append((u - 1.5 * sg.stock_objetivo, sid, u, sg))
        elif not sobre and u < sg.demanda_mediana:
            casos.append((sg.demanda_mediana - u, sid, u, sg))
    casos.sort(reverse=True)
    n = info["entidades"].get("cantidad") or 5
    if not casos:
        return {"texto": f"Para {desc}, no veo productos con {'sobreinventario' if sobre else 'riesgo de quiebre'} según los inventarios registrados ({len(inv)} series con inventario)."}
    filas = [[series[sid].item_id, series[sid].tienda.codigo, fmt(u), fmt(sg.demanda_mediana), fmt(sg.stock_objetivo)] for _, sid, u, sg in casos[:n]]
    titulo = "con sobreinventario (más de 1,5 veces el stock objetivo)" if sobre else "en riesgo de quiebre (inventario menor que la demanda mediana de 28 días)"
    return {"texto": f"Para {desc}, {len(casos)} de {len(inv)} series con inventario registrado están {titulo}. Estas son las {min(n, len(casos))} más críticas:",
            "columnas": ["Producto", "Tienda", "Inventario", "Demanda mediana", "Stock objetivo"], "filas": filas,
            "enlace": _enlace("reposicion", "Ver en Reposición", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"), estado="sobre" if sobre else "riesgo")}


def riesgo_quiebre(ctx, info):
    return _riesgos(ctx, info, sobre=False)


def sobreinventario(ctx, info):
    return _riesgos(ctx, info, sobre=True)


def top_productos(ctx, info):
    agg = _activa("lgbm_agregado")
    if not agg:
        return _sin_predicciones()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    buscar = info["entidades"].get("buscar")
    n = min(info["entidades"].get("cantidad") or (5 if buscar and buscar.get("plural") else 1 if buscar else 5), 15)
    h = ctx.get("horizonte") or {}
    clave, periodo, _ = _horizonte({"horizonte": h if h.get("tipo") in ("semana", "28d") else {"tipo": "28d"}}, agg)
    agrupar = info["entidades"].get("agrupar")
    if agrupar in GRUPOS and not ctx.get(agrupar):
        campo = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}[agrupar]
        grupos = list(PrediccionAgregada.objects.filter(corrida=agg, serie__in=qs, horizonte=clave, tau=0.5).values(campo).annotate(t=Sum("unidades")).order_by("-t"))
        filas = [[g[campo], fmt(g["t"])] for g in grupos]
        etiqueta = {"categoria": "categoría"}.get(agrupar, agrupar)
        return {"texto": f"La {etiqueta} con mayor demanda esperada {periodo} en {desc} es {filas[0][0]}, con unas {filas[0][1]} unidades (suma de medianas).", "columnas": [etiqueta.capitalize(), "Demanda esperada"], "filas": filas,
                "enlace": _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"))}
    asc = info["entidades"].get("orden") == "asc"
    filas = list(PrediccionAgregada.objects.filter(corrida=agg, serie__in=qs, horizonte=clave, tau=0.5).select_related("serie__tienda").order_by("unidades" if asc else "-unidades")[:n])
    texto = (f"El producto con {'menor' if asc else 'mayor'} demanda esperada {periodo} en {desc} es {filas[0].serie.item_id}" + ("" if ctx.get("tienda") else f", en la tienda {filas[0].serie.tienda.codigo}") + f", con unas {fmt(filas[0].unidades)} unidades (mediana)."
             if n == 1 and filas else f"Los {len(filas)} productos con {'menor' if asc else 'mayor'} demanda esperada {periodo} en {desc}:")
    return {"texto": texto, "columnas": ["Producto", "Tienda", "Mediana", "Departamento"],
            "filas": [[f.serie.item_id, f.serie.tienda.codigo, fmt(f.unidades), f.serie.departamento.codigo] for f in filas],
            "enlace": _enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"))}


def comparar_modelos(ctx, info):
    metricas = {}
    for m in MetricaModelo.objects.filter(segmento="global", metrica__in=["MASE_medio", "cobertura_80"]):
        metricas.setdefault(m.modelo, {})[m.metrica] = m.valor
    if not metricas:
        return {"texto": "Aún no hay métricas cargadas. Ejecuta «python manage.py cargar_metricas» para traer los resultados de las pruebas.", "enlace": {"texto": "Ir a Modelos", "url": reverse("modelos")}}
    etiquetas = {"naive": "Naive", "ets": "ETS", "lightgbm": "LightGBM", "tft_s1": "TFT base", "tft_h64": "TFT (hidden 64)"}
    ranking = sorted(((k, v) for k, v in metricas.items() if k in etiquetas), key=lambda kv: kv[1].get("MASE_medio", 99))
    pedido = info["entidades"].get("modelo")
    mejor, segundo = ranking[0], ranking[1]
    texto = (f"Según las pruebas (3 ventanas de 28 días, 374 series), el menor error (MASE) es el de {etiquetas[mejor[0]]}: {mejor[1]['MASE_medio']:.3f}. "
             f"Le sigue {etiquetas[segundo[0]]} con {segundo[1]['MASE_medio']:.3f}")
    texto += ", una diferencia muy pequeña: están prácticamente empatados." if segundo[1]["MASE_medio"] - mejor[1]["MASE_medio"] < 0.01 else "."
    if pedido in metricas:
        texto += f" El modelo que mencionas ({etiquetas.get(pedido, pedido)}) tiene un MASE de {metricas[pedido]['MASE_medio']:.3f}."
    return {"texto": texto, "columnas": ["Modelo", "MASE (menor es mejor)", "Cobertura del 80 %"],
            "filas": [[etiquetas[k], f"{v['MASE_medio']:.3f}", f"{v.get('cobertura_80', 0):.3f}"] for k, v in ranking], "enlace": {"texto": "Ver en Modelos", "url": reverse("modelos")}}


def estado_modelo(ctx, info):
    activas = {t: _activa(t) for t in ("lightgbm", "lgbm_agregado", "tft")}
    if not any(activas.values()):
        return _sin_predicciones()
    lg = activas["lightgbm"] or activas["lgbm_agregado"]
    inicio = lg.fecha_origen + timedelta(days=1)
    partes = [f"Las predicciones activas usan datos hasta el {lg.fecha_origen.strftime('%d/%m/%Y')} y cubren del {inicio.strftime('%d/%m/%Y')} al {(inicio + timedelta(days=27)).strftime('%d/%m/%Y')}."]
    partes.append("Modelos activos: " + ", ".join(f"{c.get_tipo_display()} (generado el {timezone.localtime(c.creada).strftime('%d/%m/%Y %H:%M')})" for c in activas.values() if c) + ".")
    if not activas["tft"]:
        partes.append("Todavía no hay un TFT entrenado; puedes lanzarlo desde la pestaña Modelos.")
    ult = EjecucionTarea.objects.first()
    if ult:
        partes.append(f"Última tarea: {ult.get_comando_display()} ({ult.get_estado_display().lower()}).")
    return {"texto": " ".join(partes), "enlace": {"texto": "Ir a Modelos", "url": reverse("modelos")}}


def inventario_actual(ctx, info):
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    inv = _inventarios(ids)
    simulados = InventarioActual.objects.filter(serie_id__in=ids, simulado=True).exists()
    if not inv:
        return {"texto": f"No hay inventario registrado para {desc}. Puedes registrarlo en la pestaña Reposición.", "enlace": _enlace("reposicion", "Ir a Reposición", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"))}
    if len(ids) == 1:
        texto = f"El inventario registrado de {desc} es de {fmt(next(iter(inv.values())))} unidades."
    else:
        texto = f"Para {desc} hay inventario registrado en {len(inv)} de {len(ids)} series, con un total de {fmt(sum(inv.values()))} unidades."
    if simulados:
        texto += " Ojo: hay inventarios simulados (de demostración), no son datos reales."
    return {"texto": texto, "enlace": _enlace("reposicion", "Ver en Reposición", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"), q=ctx.get("producto"))}


def terminos_glosario(info):
    """Términos del glosario mencionados en el texto (vacío si no se pregunta por ninguno)."""
    t = info["normalizado"]
    hallados = [k for k in GLOSARIO if k in t]
    for k, sinonimos in SINONIMOS_GLOSARIO.items():
        if k not in hallados and any(s in t for s in sinonimos):
            hallados.append(k)
    for k in ("p10", "p50", "p90"):
        if k not in hallados and (f"percentil {k[1:]}" in t or f"p {k[1:]}" in t):
            hallados.append(k)
    return hallados


def glosario(ctx, info):
    t = info["normalizado"]
    hallados = terminos_glosario(info)
    for k, sinonimos in SINONIMOS_GLOSARIO.items():
        if k not in hallados and any(s in t for s in sinonimos):
            hallados.append(k)
    for k in ("p10", "p50", "p90"):                                   # "p 90" o "percentil 90"
        if k not in hallados and (f"percentil {k[1:]}" in t or f"p {k[1:]}" in t):
            hallados.append(k)
    if not hallados:
        return {"texto": "Puedo explicarte términos como P10, P50, P90, nivel de servicio, stock objetivo, pedido sugerido, quiebre, sobreinventario, cobertura, MASE, pinball, cuantil, TFT, LightGBM y ETS. ¿Cuál te interesa?",
                "sugerencias": ["¿Qué es el nivel de servicio?", "¿Qué significa P90?", "¿Qué es un quiebre de stock?", "¿Qué mide el MASE?"]}
    return {"texto": " ".join(GLOSARIO[k] for k in hallados[:2])}


def catalogo(ctx, info):
    """Qué datos hay en el aplicativo: tiendas (sedes), categorías, departamentos, número de productos y periodo cubierto."""
    t = info["normalizado"]
    ents = info["entidades"]
    qs = Serie.objects.all()
    if ents.get("tienda"):
        qs = qs.filter(tienda__codigo=ents["tienda"])
    if ents.get("categoria"):
        qs = qs.filter(departamento__categoria__codigo=ents["categoria"])
    if ents.get("departamento"):
        qs = qs.filter(departamento__codigo=ents["departamento"])
    fechas = VentaDiaria.objects.aggregate(a=Min("fecha"), b=Max("fecha"))
    f = lambda d: d.strftime("%d/%m/%Y")
    tiendas = Tienda.objects.annotate(n=Count("series")).order_by("codigo")
    categorias = Categoria.objects.annotate(n=Count("departamentos__series")).order_by("codigo")
    if any(w in t for w in ("fecha", "desde cuando", "hasta cuando", "historia", "periodo", "dias de")):
        return {"texto": f"Las ventas registradas van del {f(fechas['a'])} al {f(fechas['b'])}." + (" Las proyecciones cubren los 28 días siguientes." if _activa("lgbm_agregado") else "")}
    if any(w in t for w in ("departamento",)):
        deptos = Departamento.objects.filter(series__in=qs).annotate(n=Count("series", distinct=True)).order_by("codigo")
        return {"texto": f"Hay {deptos.count()} departamentos con datos.", "columnas": ["Departamento", "Categoría", "Series"], "filas": [[d.codigo, d.categoria.codigo, fmt(d.n)] for d in deptos]}
    if any(w in t for w in ("categoria",)) and not (ents.get("tienda") and "cuantos" in t):
        return {"texto": f"Hay {categorias.count()} categorías de productos.", "columnas": ["Categoría", "Series"], "filas": [[c.codigo, fmt(c.n)] for c in categorias]}
    if any(w in t for w in ("cuantos", "cuantas", "numero de")) and (any(w in t for w in ("producto", "serie", "referencia", "articulo")) or ents.get("tienda") or ents.get("categoria") or ents.get("departamento")):
        return {"texto": f"Hay {fmt(qs.count())} series (un producto en una tienda) en la selección, de {qs.values('item_id').distinct().count()} productos distintos."}
    return {"texto": f"El aplicativo tiene {tiendas.count()} tiendas (sedes), {categorias.count()} categorías y {fmt(Serie.objects.count())} series (un producto en una tienda), "
                     f"con ventas del {f(fechas['a'])} al {f(fechas['b'])}.", "columnas": ["Tienda", "Estado", "Series"], "filas": [[x.codigo, x.estado, fmt(x.n)] for x in tiendas],
            "sugerencias": ["¿Qué departamentos hay?", "¿Cuántos productos hay en Texas?"]}


def accion_no_soportada(ctx, info):
    return {"texto": "Todavía no puedo hacer cambios ni ejecutar acciones desde el chat: solo consulto datos. Lo que pides se hace desde las pestañas: el inventario actual se edita en Reposición "
                     "y las tareas (generar predicciones, entrenar el TFT) se lanzan en Modelos. Aquí sí puedo consultarte ventas, proyecciones, reposición, riesgos y modelos.",
            "enlace": {"texto": "Ir a Modelos", "url": reverse("modelos")}, "sugerencias": EJEMPLOS[:3]}


def saludo(ctx, info):
    return {"texto": "¡Hola! Soy el asistente del aplicativo de inventario predictivo. Puedo darte proyecciones de demanda, sugerencias de reposición, riesgo de quiebre y comparar modelos. Escribe «ayuda» para ver ejemplos.",
            "sugerencias": EJEMPLOS[:4]}


GUIAS_APP = [
    (("pedido", "reposicion", "sugerid", "stock objetivo", "nivel de servicio", "surtir", "reabastec"),
     "Los pedidos sugeridos están en la pestaña Reposición: arriba eliges tienda, categoría, nivel de servicio (80, 90 o 95 %), política (28 días o semanal), estado y buscas un producto. "
     "La tabla muestra demanda mediana, stock objetivo, inventario actual y pedido sugerido. Para cambiar el nivel de servicio usa ese selector.", "reposicion", "Ir a Reposición"),
    (("inventario", "existencia", "stock"),
     "El inventario actual se ve y se edita en la pestaña Reposición, en la columna «Inventario actual»: escribes las unidades y el pedido y el estado se recalculan al instante. "
     "Aquí en el chat puedes consultarlo, por ejemplo «¿cuánto inventario tengo de FOODS en Texas?».", "reposicion", "Ir a Reposición"),
    (("entrena", "tft", "generar", "genera", "prediccion", "predicciones", "actualiz", "corrida", "modelo", "boton"),
     "Las predicciones y el entrenamiento se lanzan en la pestaña Modelos: el botón «Generar predicciones» entrena LightGBM y guarda el pronóstico (~1 min) y «Entrenar TFT» entrena la red neuronal (~1 h; hay una prueba rápida). "
     "Ahí también ves el estado de las tareas, las corridas guardadas y la comparación de modelos.", "modelos", "Ir a Modelos"),
    (("grafica", "proyeccion", "rango", "banda", "p10", "linea", "interpreto"),
     "La pestaña Proyecciones muestra, para una serie, las ventas reales de las últimas 12 semanas, la mediana proyectada de los próximos 28 días y la banda entre P10 y P90 (el rango razonable). "
     "Si la banda es ancha, la demanda es más incierta; puedes comparar con el TFT marcando «Comparar con TFT».", "proyecciones", "Ir a Proyecciones"),
    (("tienda", "categoria", "filtro", "filtrar", "seleccion", "producto"),
     "Los filtros están arriba en Proyecciones y Reposición: Tienda y Categoría (y en Reposición también nivel de servicio, política, estado y un buscador de producto). "
     "En el chat basta decirlo con palabras, por ejemplo «ventas de FOODS en Texas», y después «¿y en California?».", "reposicion", "Ir a Reposición"),
    (("pestana", "pestanas", "inicio", "chat", "para que sirve", "primer dia", "empezar", "orienta"),
     "El aplicativo tiene cinco secciones: Inicio (estado de los datos), Proyecciones (demanda esperada y su rango), Reposición (cuánto pedir y editar el inventario), Modelos (lanzar tareas y comparar modelos) y Chat (preguntas en lenguaje natural sobre todo lo anterior).", "inicio", "Ir a Inicio"),
]


def ayuda(ctx, info):
    t = info["normalizado"]
    for palabras, texto, destino, etiqueta in GUIAS_APP:
        if any(p in t for p in palabras) and re.search(r"donde|pestana|filtro|boton|como (cambio|selecciono|uso|veo|hago)|en que|para que sirve|primer dia|empezar|orient|interpreto|explicame|que (es|hay)", t):
            return {"texto": texto, "enlace": {"texto": etiqueta, "url": reverse(destino)}}
    return ayuda_general(ctx, info)


def ayuda_general(ctx, info):
    return {"texto": "Puedo responder sobre: las ventas ya registradas (pasado: «¿qué se vendió más el último mes?») y la demanda esperada a futuro con su rango de incertidumbre, cuánto pedir (con nivel de servicio de 80, 90 o 95 %), productos en riesgo de quiebre o con sobreinventario, "
                     "los productos con más demanda, el inventario registrado, el estado y la comparación de los modelos, y el significado de los términos. Puedes filtrar por tienda (CA_1, TX_2, WI_2), "
                     "categoría (FOODS, HOBBIES, HOUSEHOLD), departamento o producto, y por semana o 28 días. Recuerdo el contexto de la conversación: después de una pregunta puedes decir «¿y en Texas?». Por ejemplo:",
            "sugerencias": EJEMPLOS}


def cierre(ctx, info):
    return {"texto": "¡Con gusto! Si necesitas algo más sobre inventario o proyecciones, aquí estaré."}


TEMAS_UNA_PALABRA = {"ventas": ["¿Qué se vendió más el último mes registrado?", "¿Cuánto se va a vender el próximo mes?"], "venta": ["¿Qué se vendió más el último mes registrado?", "¿Cuánto se va a vender el próximo mes?"],
                     "inventario": ["¿Cuánto inventario tengo?", "¿Qué productos tienen sobreinventario?"], "stock": ["¿Cuánto stock tengo?", "¿Qué productos están en riesgo de quiebre?"],
                     "pedido": ["¿Cuánto debo pedir?", "¿Cuánto debo pedir con 95 % de servicio?"], "quiebre": ["¿Qué productos están en riesgo de quiebre?", "¿Qué significa quiebre de stock?"],
                     "modelos": ["¿Cuál modelo es mejor?", "¿Cuándo se actualizaron las predicciones?"], "modelo": ["¿Cuál modelo es mejor?", "¿Cuándo se actualizaron las predicciones?"],
                     "demanda": ["¿Cuánto se va a vender el próximo mes?", "¿Qué productos tendrán más demanda?"], "proyeccion": ["¿Cuánto se va a vender el próximo mes?", "¿Cuál es el rango de la proyección?"],
                     "predicciones": ["¿Cuánto se va a vender el próximo mes?", "¿Cuándo se actualizaron las predicciones?"]}


def ambigua(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    if ents and len(t.split()) <= 4:                                  # solo menciona entidades («FOODS_2_398 WI_2», «hogar texas»)
        partes = " ".join(str(v) for k, v in ents.items() if k in ("producto", "departamento", "categoria", "tienda"))
        return {"texto": f"¿Qué quieres saber de {partes}? Por ejemplo:", "sugerencias": [f"¿Qué se vendió más el último mes registrado en {partes}?", f"¿Cuánto se va a vender de {partes} el próximo mes?", f"¿Cuánto debo pedir de {partes}?"]}
    palabra = next((w for w in re.findall(r"[a-z]+", t) if w in TEMAS_UNA_PALABRA), None)
    if palabra and len(t.split()) <= 2:
        return {"texto": f"¿Qué quieres saber sobre «{palabra}»? Por ejemplo:", "sugerencias": TEMAS_UNA_PALABRA[palabra]}
    return {"texto": "¿Puedes darme un poco más de detalle? Indica qué quieres saber (demanda, cuánto pedir, riesgo de quiebre...) y de qué producto, tienda o categoría.",
            "sugerencias": EJEMPLOS[:3]}


def fuera_de_contexto(ctx, info):
    return {"texto": FUERA}


def no_entendida(ctx, info):
    return {"texto": "No logré entender la pregunta. Intenta con una frase como estas:", "sugerencias": EJEMPLOS[:4]}


FUNCIONES = {"catalogo": catalogo, "ventas_pasadas": ventas_pasadas, "demanda_esperada": demanda_esperada, "rango_proyeccion": rango_proyeccion, "cuanto_pedir": cuanto_pedir, "riesgo_quiebre": riesgo_quiebre, "sobreinventario": sobreinventario,
             "top_productos": top_productos, "comparar_modelos": comparar_modelos, "estado_modelo": estado_modelo, "inventario_actual": inventario_actual, "glosario": glosario,
             "saludo": saludo, "accion_no_soportada": accion_no_soportada, "ayuda": ayuda, "cierre": cierre, "ambigua": ambigua, "fuera_de_contexto": fuera_de_contexto, "no_entendida": no_entendida}
