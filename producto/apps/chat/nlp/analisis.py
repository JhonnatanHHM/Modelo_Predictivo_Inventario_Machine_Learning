"""Preguntas analíticas del día a día que se resuelven con reglas y consultas directas (no con el clasificador): fin de semana frente a entre semana, días SNAP, eventos del
calendario, precios, ingresos aproximados, participación en el total, crecimiento entre años, primera venta, días sin ventas y cobertura de inventario.
También responde, con honestidad, a lo que el aplicativo no tiene (costos, proveedores, clientes...) y a periodos, tiendas o productos que no existen."""
import re
from datetime import date, timedelta

from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Max, Min, Sum
from django.db.models.functions import ExtractWeekDay, ExtractYear

from apps.catalogo.models import Calendario, PrecioSemanal, Serie, Tienda, VentaDiaria
from apps.pronosticos.models import InventarioActual, SugerenciaReposicion

from . import respuestas as R

LO_QUE_HAY = ("Lo que sí tengo: ventas diarias en unidades, precios de venta semanales, el calendario con eventos y días SNAP, las proyecciones de demanda a 28 días, "
              "las sugerencias de reposición, el inventario registrado y la comparación de modelos.")

# --------------------------------------------------------------------------------------------- datos que el aplicativo no tiene
NO_TIENE = [
    (r"margen|ganancia|utilidad|rentabil|rentable|\bganamos\b|cuanto gano|beneficio neto|lucro", "márgenes, costos ni ganancias",
     "Con los precios y las unidades vendidas puedo darte ingresos aproximados (unidades × precio de venta), pero no cuánto se gana."),
    (r"\bcost[oa]s?\b|cuesta (?:reponer|mantener|enviar|el pedido|tener|el inventario)|inmoviliz|valor del inventario|vale en dinero|costo de (?:quiebre|reposicion|mantener)|\bflete|envi(?:ar|o) mercancia", "costos",
     "Sí puedo darte las unidades del stock objetivo o del pedido sugerido, y el precio de venta de los productos."),
    (r"proveedor|plazo(?:s)? de entrega|tiempo(?:s)? de entrega|tarda(?:n)? en entregar|lead ?time|cuando llega el pedido|dias de entrega|retras\w+ (?:el|mi) proveedor|proveedor se retras", "proveedores ni plazos de entrega",
     "El pedido sugerido cubre la demanda de los próximos 28 días (o por semana); el plazo de entrega tendrías que sumarlo tú al decidir cuándo pedir."),
    (r"\bclientes?\b|compradores?|consumidores?|personas que compran|trafico de la tienda", "clientes ni visitas a la tienda",
     "Solo registro unidades vendidas por producto y día, no quién compró ni cuántas personas entraron."),
    (r"empleados?|personal necesario|trabajadores?|salario|nomina|\bturnos?\b|horarios? de", "empleados, turnos ni salarios",
     "Puedo mostrarte la demanda esperada por día y por tienda para que tú dimensiones el equipo."),
    (r"producto favorito|articulo favorito|mis favoritos|mis preferencias|mis gustos", "tus preferencias ni favoritos", "Puedo decirte qué productos son los más vendidos o los de mayor demanda esperada."),
    (r"vence\b|vencen|vencimiento|caduc|vida util|perecedero|fecha de expiracion|\blotes?\b", "fechas de vencimiento, lotes ni vida útil",
     "Puedo darte la demanda esperada y el stock objetivo en unidades."),
    (r"pasillo|ubicacion en (?:la )?bodega|donde esta (?:almacenad|guardad)|espacio de bodega|espacio en bodega|metros cuadrados|capacidad de (?:la )?bodega", "la ubicación física ni la capacidad de la bodega",
     "Solo registro cuántas unidades hay de cada producto (inventario actual)."),
    (r"devoluci|devuelven|devuelto|reembols", "devoluciones", "Solo registro las unidades vendidas."),
    (r"competencia|competidor|precios de otras|otra tienda de la competencia", "datos de la competencia",
     "Sí tengo los precios propios de cada producto a lo largo del tiempo."),
    (r"publicidad|marketing|campana publicitaria|\banuncios?\b|redes sociales", "publicidad ni marketing", "Sí puedo mostrarte cómo se movieron las ventas en las fechas que quieras."),
    (r"\biva\b|impuesto|arancel", "impuestos", "Los precios que tengo son los de venta registrados, sin detalle de impuestos."),
    (r"\bmarcas?\b|nombre del producto|nombre de producto|descripcion del producto|que producto es|que es (?:el )?(?:foods|hobbies|household)|fabricante|codigo de barras", "marcas, nombres ni descripciones de los productos",
     "Los productos solo se identifican por su código (por ejemplo FOODS_2_398), su departamento y su tienda."),
    (r"\bclima\b|llover|lluvia|tormenta|temperatura|nevada|\bcalor\b|\bfrio\b", "datos del clima",
     "Sí puedo mostrarte cómo varían las ventas por día de la semana, mes o evento del calendario."),
    (r"habr[ae] (?:descuentos?|promociones?|ofertas?)|promociones? (?:futuras?|planeadas?|programadas?)|descuentos? (?:futuros?|planeados?)|rebajas? (?:futuras?|del mes)", "promociones o descuentos planeados",
     "Sí tengo los precios históricos de cada producto, para ver cuándo cambiaron."),
]
NO_TIENE = [(re.compile(p), q, a) for p, q, a in NO_TIENE]
ESCENARIOS = re.compile(r"deberia (?:hacer |lanzar |aplicar )?(?:una )?(?:promocion|oferta|rebaja|descuento)|que pasaria si|si las ventas (?:suben|bajan|crecen|caen|aumentan)|ventas? \d+ ?% (?:por encima|mas|menos|arriba|por debajo)|escenario de ventas \d+|cuanto subirian|cuanto bajarian|"
                        r"me conviene (?:subir|bajar)|si (?:hago|hiciera|lanzo) (?:una )?(?:promocion|oferta)|promocion con \d+|\bsimul\w+|si subo el precio|si baja(?:ra)? el precio")
PERIODO_VENTAS = re.compile(r"\bvend|\bventa|\bingres|\bunidades\b")


def _limites():
    return VentaDiaria.objects.aggregate(p=Min("fecha"), m=Max("fecha"))


def _f(d):
    return d.strftime("%d/%m/%Y")


def no_disponible(info):
    t = info["normalizado"]
    if NO_CONVERSACION.search(t):
        return {"texto": "No puedo resumir la conversación. Todo lo que hemos hablado queda guardado en el historial de la lista de conversaciones; y puedo repetirte cualquier dato si me lo preguntas de nuevo."}
    if ESCENARIOS_DESCUENTO.search(t):
        return {"texto": "No recomiendo descuentos: el aplicativo no tiene costos ni márgenes ni mide cómo responden las ventas a una rebaja. Sí puedo mostrarte cómo se vendió un producto a distintos precios.",
                "sugerencias": ["¿Vendimos más cuando bajó el precio de HOUSEHOLD_1_096?"]}
    for rx, que, alternativa in NO_TIENE:
        if rx.search(t):
            return {"texto": f"Eso no lo puedo responder: el aplicativo no tiene {que}. {alternativa}",
                    "sugerencias": R.EJEMPLOS[:3]}
    return None


# --------------------------------------------------------------------------------------------- detección
def _anios(t):
    return [int(a) for a in re.findall(r"\b(20[0-3]\d)\b", t)]


CLIMA_CAUSA = re.compile(r"por (?:el|la) (?:clima|lluvia|tormenta|temperatura|nieve)|afecta(?:n)? (?:el|la) (?:clima|lluvia)|(?:clima|lluvia|tormenta)s? (?:afecta|influye)|influye (?:el|la) (?:clima|lluvia)")
NO_CONVERSACION = re.compile(r"resum\w+ (?:de )?(?:todo )?(?:lo que )?(?:hemos|vimos|hablamos)|resume (?:la |esta )?conversacion|resumen de (?:toda )?(?:la |esta )?conversacion|en tres puntos de todo")
ESCENARIOS_DESCUENTO = re.compile(r"que descuento (?:recomiendas|me recomiendas|aplico|debo)|cuanto descuento")


def _detectar(info, ctx=None):
    """Devuelve la clave del análisis que corresponde a la pregunta, o None si la debe resolver el clasificador."""
    ctx = ctx or {}
    t = info["normalizado"]
    ents = info["entidades"]
    palabras = len(t.split())
    if re.search(r"\b(?:julio|agosto|septiembre|octubre|noviembre|diciembre) (?:de |del )?2016\b", t):
        return "periodo_sin_datos"
    if ctx.get("rank_fs") and ctx.get("clave_analisis") == "fin_semana" and re.search(r"^\W*(?:y )?(?:el|la|los|las) (?:que |producto )?(?:mas|menos)", t):
        return "fin_semana"
    if ctx.get("clave_analisis") == "snap" and re.search(r"esos dias|esas fechas|esos dias snap|tambien hay|considera|tiene en cuenta|toma en cuenta", t) and not re.search(r"\bsnap\b", t):
        return "snap"
    if re.search(r"d?e?l? ?(?:producto|articulo) favorito|mis (?:favoritos|preferencias|gustos)", t):
        return "no_disponible"
    if re.search(r"cuanto (?:tarda|demora|toma)(?:n)? (?:en )?entrenar|tiempo de entrenamiento|cuanto dura el entrenamiento|que tan rapido (?:entrena|es)|cuanto tiempo (?:tarda|toma|demora)", t):
        return "tiempo_entrenamiento"
    if (re.search(r"que (?:categoria|departamento|tienda|producto)s? (?:explica|aporta|influye|pesa|jalona|impulsa|empuja|tiene que ver)|explica(?:n)? (?:mas )?esa diferencia|esa diferencia|responsable de (?:la|esa) (?:diferencia|caida|subida)", t)
            and ctx.get("periodos_cmp")):
        return "explica_dif"
    if re.search(r"compar\w*|frente a|contra|\bvs\b|respecto a|con relacion a", t) and ents.get("pasado") and not ents["pasado"].get("generico") and info.get("pasado_prev") and not _menciones_rapido(t) \
            and not _anios(t) and info["pasado_prev"] != ents["pasado"]:
        return "comparar_periodos"
    if re.search(r"(?:dia|fecha)s? (?:con |de )?(?:mayor|menor|mas|menos) (?:demanda|ventas)|que dia (?:se )?(?:espera|va a)|dia pico|pico de demanda|(?:cual|que) (?:es )?el dia", t) and (R_FUTURO.search(t) or ents.get("horizonte")) \
            and not re.search(r"semana", t.replace("dia de la semana", "")):
        return "dia_pico_futuro"
    if ctx.get("dia_ref") and re.search(r"ese (?:mismo )?dia|esa fecha", t) and re.search(r"rango|pesimista|optimista|escenario|p10|p90|minimo|maximo|incertidumbre", t):
        return "rango_dia"
    if re.search(r"ese dia|esa fecha|dicho dia|ese mismo dia", t) and re.search(r"evento|feriado|snap|cae en|festiv|es dia|que dia|calendario", t) and not re.search(r"vendi|ventas", t):
        return "dia_info"
    if re.search(r"\b(30|31) de febrero\b|\b29 de febrero de 201[1235]\b", t):
        return "fecha_invalida"
    if any(a < 2011 or a > 2016 for a in _anios(t)):
        return "periodo_sin_datos"
    if re.search(r"\b(?:tienda|sede|sucursal)s? (?:de|en) (?!california|texas|wisconsin|ca_|tx_|wi_|todas|cada|la |el |los |las |mi |nuestra|este|esta|ese|esa)[a-z]{3,}", t) and not ents.get("tienda"):
        return "tienda_desconocida"
    if re.search(r"\b(?:foods|hobbies|household)[ _-]?\d[ _-]?\d{3}\b", t) and not ents.get("producto"):
        return "producto_desconocido"
    if re.search(r"\bnueva york\b|\bnew york\b|\bflorida\b|\bchicago\b", t) and re.search(r"\btienda|\bsede|\bventas|\bsucursal", t):
        return "tienda_desconocida"
    if CLIMA_CAUSA.search(t) or NO_CONVERSACION.search(t) or ESCENARIOS_DESCUENTO.search(t):
        return "no_disponible"
    if any(rx.search(t) for rx, _, _ in NO_TIENE) and not re.search(r"\bsnap\b", t):
        if not (re.search(r"\bclima\b|llover|lluvia|tormenta|temperatura|\bfrio\b|\bcalor\b", t) and not re.search(r"vend|venta|pedido|inventario|stock|demanda|producto|tienda", t)):
            return "no_disponible"
    if ESCENARIOS.search(t):
        return "escenarios"
    futuro = bool(ents.get("horizonte")) or bool(R_FUTURO.search(t))
    if re.search(r"\bsnap\b", t):
        return "snap"
    if _menciones_rapido(t) and re.search(r"compar|\bvs\b|versus|contra|\bo\b|mejor|peor|\bmas\b|\bmenos\b|diferencia|cual|que (?:tienda|categoria|departamento)", t) and not futuro \
            and not re.search(r"cada (?:tienda|categoria|departamento)|por (?:tienda|categoria|departamento)", t) and re.search(r"vend|venta|compar|ingres|precio|mejor|peor", t):
        return "comparar"
    if re.search(r"(?:tres|todas las) (?:tiendas|sedes)", t) and re.search(r"compar|vend|venta", t) and not futuro:
        return "comparar"
    if len(set(re.findall(r"\b(domingo|lunes|martes|miercoles|jueves|viernes|sabado)s?\b", t))) >= 2 and re.search(r"compar|\bvs\b|versus|contra|\bo\b|\by\b|mas|menos", t) and not futuro:
        return "dias_comparar"
    if re.search(r"cuando (?:debo|tengo que|toca|conviene) (?:hacer )?(?:el )?(?:proximo )?(?:pedido|pedir|reponer)|cuando (?:pido|pedir|repongo)", t):
        return "cuando_pedir"
    if re.search(r"semana", t) and re.search(r"mas (?:segura|confiable|incierta|precisa)|menos (?:segura|incierta|confiable)|mas certeza|mas riesgo", t):
        return "incertidumbre_semanas"
    if re.search(r"(?:proyecci\w+|pronostico|prediccion).*(?:real|realmente|vendio|vendido)|(?:real|realmente|vendido).*(?:proyecci\w+|pronostic\w+)|cambio de tendencia.*proyect|recientes? (?:versus|vs|contra|frente a).*proyect|como le fue a la proyeccion", t) \
            and not re.search(r"\bmodelo\b|\balgoritmo\b", t):
        return "real_vs_proyeccion"
    if re.search(r"(?:subir|pasar|aumentar|cambiar|llevar)\w* (?:de|el nivel de servicio de) (?:80|90) ?%? (?:a|hasta) (?:90|95) ?%?|de (?:80|90) ?% a (?:90|95) ?%|(?:90|80) ?% a (?:95|90) ?%", t):
        return "subir_nivel"
    if re.search(r"nivel de servicio (?:estoy|tengo|actual|real|cubierto)|con que nivel|que nivel de servicio estoy|nivel de servicio.*actualmente", t):
        return "nivel_actual"
    if re.search(r"cuantos dias (?:de inventario|me (?:quedan|dura|alcanza)|dura)|dias de inventario|dias de cobertura|cobertura|para cuantos dias|me alcanzan? para|cuantos dias me|me dura|hasta cuando me alcanza|alcanza(?:n)? para (?:las |los |el |la )?(?:proxim|\d|semana|mes|junio|fin)|dias de venta", t) and not re.search(r"cobertura de los datos", t):
        return "cobertura"
    if re.search(r"fin(?:es)? de semana|entre semana|findes?\b|dias laborales|dias habiles|sabados? y domingos?", t) and re.search(r"vend|venta|demanda|pedir|stock|inventario|mas|menos|necesito|cubrir|conviene", t) and not ents.get("producto") or \
            re.search(r"(?:vend|venta)\w* (?:mas )?(?:en |los )?(?:fin(?:es)? de semana|findes)", t):
        return "fin_semana"
    if re.search(r"navidad|christmas|accion de gracias|thanksgiving|super ?bowl|halloween|pascua|easter|4 de julio|independencia|black friday|viernes negro|ano nuevo|dia de las madres|dia del padre|"
                 r"san valentin|memorial|dia de los caidos|labor day|dia del trabajo|evento|feriado|festivo|festividad|fecha especial|dia especial|dias especiales|religios|deportivo|nba|ramadan|cinco de mayo|st patrick|san patricio|veterans|columbus|presidentes", t) \
            and not ents.get("buscar") and not re.search(r"\bproducto\b.*(?:mas|menos) vendid|(?:mas|menos) vendid.*\bproducto\b", t):
        return "eventos"
    if re.search(r"por que\b.*(?:cero|bajo|baj\w+|cayo|subio|alto|poco|no hubo|0)|por que (?:es|fue|esta)", t) and palabras <= 9:
        return "por_que"
    if re.search(r"irregular|volatil|variab\w+ en sus ventas|con picos|dias en cero|mas estable|menos estable|ventas estables|intermitent|erratic", t) and re.search(r"producto|series?|ventas", t) and not re.search(r"precio", t):
        return "irregular"
    if re.search(r"estacional(?!idad)|solo en una epoca|una epoca del ano|algunos meses del ano|mejor en verano|mejor en invierno|verano que en invierno|invierno que en verano|mas en verano|mas en invierno", t):
        return "estacional"
    if re.search(r"\babc\b|pareto|concentran? el \d+ ?%|80 ?/ ?20|que parte de los productos", t):
        return "abc"
    if re.search(r"parecid\w+|similar\w*|equivalente|sustituto|alternativa a", t) and ents.get("producto"):
        return "parecidos"
    if re.search(r"(?:de|por) cada (?:categoria|tienda|departamento)|por (?:categoria|tienda|departamento)", t) and re.search(r"productos?.*(?:mas|menos) vendid|(?:mas|menos) vendid.*productos?|top ?\d|\d productos", t) and not futuro:
        return "top_por_grupo"
    if re.search(r"ingres|dinero|dolares|facturacion|facturamos|plata|\bpesos\b|monto vendido|valor de las ventas|\bgenera(?:n)? mas|deja(?:n)? mas dinero", t) and not re.search(r"inventario|pedido|stock", t):
        return "ingresos"
    sin_contexto = palabras <= 3 and not ents
    if re.search(r"\bprecio|\bcuesta\b|\bcuestan\b|\bcuanto (?:vale|valen)\b|\bvale (?:el|la|este|ese)\b|\bcaro\b|\bcara\b|\bcaros\b|\bbarato|\bbarata|\beconomic|\bcostoso|promocion|rebaja|oferta", t) and not futuro \
            and not re.search(r"nivel de servicio|inventario|pedido|stock|reposicion|quiebre|me cuesta en", t) and not sin_contexto:
        return "precio"
    if re.search(r"dias? sin ventas|no (?:vendio|vendieron|vendimos|registr\w+) (?:nada|ventas)|sin ninguna venta|ventas? (?:en|igual a) cero|vendio 0|dejaron de venderse|dejo de venderse|sin movimiento|no se vendio nada|ventas? en 0|dias en cero|cero ventas|en cero ayer|productos? con ventas en cero", t):
        return "sin_ventas"
    if re.search(r"cuando (?:empezo|comenzo|inicio|arranco|salio)|desde cuando se vende|primera venta|primer dia de venta|productos? nuevos?|empezaron a venderse|se lanzo", t):
        return "primera_venta"
    if re.search(r"cuantos (?:productos|series|articulos|items) (?:\w+ ){0,3}(?:mas|menos|mayor|menor) de \d|cuantos (?:productos|series) (?:superan|pasan|vendieron mas|vendieron menos|venden mas|venden menos)|cuantos dias (?:\w+ ){0,4}(?:mas|menos|encima|debajo|mayor|menor|superior) (?:de|a) \d", t):
        return "umbral"
    if re.search(r"estacionalidad", t):
        return "estacionalidad"
    if re.search(r"crec\w+|cayo|cayeron|caida|variacion|subio|subieron|bajo mas|bajaron|aumento|disminuy\w+|tendencia|a la baja|al alza|evolucion|evoluciono|por ano|cada ano|anual\w*|ano con mas|ano se vendio|que ano|"
                 r"frente al ano|respecto al ano|comparado con el ano|contra el ano|vs\.? 20\d\d|resumen de ventas por|trimestre|semestre|el que mas (?:creci|cayo)|compar\w+ .*(?:20\d\d)|mensual", t) and not futuro:
        return "tendencia"
    if re.search(r"porcentaje|participacion|\bpeso\b.*\b(?:ventas|total)\b|que % |representa|proporcion|\bshare\b|que parte de las ventas|cuanto aporta|aporta(?:n)? (?:mas|menos)|concentra", t) and not re.search(r"servicio|confianza|cobertura", t):
        return "participacion"
    if re.search(r"mejor semana|peor semana|semana con mas|semana con menos|que semana", t) and not futuro:
        return "semana"
    return None


def _menciones_rapido(t):
    """True si se nombran dos o más tiendas, departamentos o categorías distintos."""
    from . import analisis_extra
    m = analisis_extra.menciones(t)
    return any(len(v) >= 2 for v in m.values())


R_FUTURO = re.compile(r"\b(?:va|van|vamos|iran|ira|sera|seran|vaya|vayan)\b|\bproxim\w*|\bsemana [1-4]\b|\bjunio\b|\bproyecc\w*|\bpronostic\w*|\bespera\w*|\bfuturo\b|\bestim\w*")


# --------------------------------------------------------------------------------------------- utilidades
def _periodo(ctx, info, limites, defecto="todo"):
    """(desde, hasta, nombre, desde_previo, hasta_previo) a partir de lo que dice la pregunta; sin periodo explícito, todo el histórico."""
    p = info["entidades"].get("pasado")
    if p and not p.get("generico"):
        pasado = p
    elif defecto == "mes":
        pasado = {"n": 28}
    elif defecto == "anio":
        pasado = {"n": 365}
    else:
        pasado = {"todo": True}
    if pasado.get("fecha"):
        d = date.fromisoformat(pasado["fecha"])
        return d, d, pasado.get("etiqueta", "ese día"), d - timedelta(days=1), d - timedelta(days=1)
    if pasado.get("mes_anio") and date(pasado["mes_anio"][1], pasado["mes_anio"][0], 1) > limites["m"]:
        return None
    return R._periodo_pasado(pasado, limites["p"], limites["m"])


def _rango(desde, hasta):
    return f"del {_f(desde)} al {_f(hasta)}" if desde != hasta else f"el {_f(desde)}"


def _pct(a, b):
    return f"{abs(round(100 * (a - b) / b))} % {'más' if a >= b else 'menos'}" if b else "sin base de comparación"


def _tabla(titulos, filas):
    return {"columnas": titulos, "filas": filas}


def _alcance(ctx):
    qs, desc, error = R._alcance(ctx)
    return qs, desc, error


SNAP_TIENDA = {"CA": "snap_ca", "TX": "snap_tx", "WI": "snap_wi"}


# --------------------------------------------------------------------------------------------- respuestas de aviso
def fecha_invalida(ctx, info):
    return {"texto": "Esa fecha no existe en el calendario (febrero no tiene 30 ni 31 días). Dime otra fecha y te cuento qué se vendió ese día."}


def periodo_sin_datos(ctx, info):
    lim = _limites()
    return {"texto": f"No tengo datos de ese año: las ventas registradas van del {_f(lim['p'])} al {_f(lim['m'])} y las proyecciones cubren del {_f(lim['m'] + timedelta(days=1))} al "
                     f"{_f(lim['m'] + timedelta(days=28))}. Puedes preguntarme por cualquier periodo dentro de ese rango.",
            "sugerencias": ["¿Cuánto se vendió en 2015?", "¿Cuánto se va a vender el próximo mes?"]}


def tienda_desconocida(ctx, info):
    tiendas = ", ".join(Tienda.objects.order_by("codigo").values_list("codigo", flat=True))
    return {"texto": f"No tengo datos de esa tienda. Las tiendas del aplicativo son {tiendas} (California, Texas y Wisconsin).", "sugerencias": ["¿Cuánto vendió CA_1 el último mes?", "¿Cuáles son nuestras sedes?"]}


def producto_desconocido(ctx, info):
    m = re.search(r"\b((?:foods|hobbies|household)[ _-]?\d[ _-]?\d{3})\b", info["normalizado"])
    cod = re.sub(r"[ -]", "_", m[1]).upper() if m else "ese código"
    return {"texto": f"No encontré el producto {cod}: ese código no existe en el catálogo (los departamentos son FOODS_1 a 3, HOBBIES_1 y 2, HOUSEHOLD_1 y 2). Puedo buscarte los productos más vendidos de un departamento.",
            "sugerencias": ["¿Qué productos son los más vendidos de FOODS_2?"]}


def escenarios(ctx, info):
    return {"texto": "No simulo escenarios «qué pasaría si» en el chat. Lo más cercano: el rango de la proyección (P10, P50, P90) muestra qué tan alta o baja podría ser la demanda, "
                     "y el stock objetivo al 95 % de servicio cubre un escenario de ventas alto. ¿Quieres ver alguno de los dos?",
            "sugerencias": ["¿Cuál es el rango de la proyección?", "¿Cuánto debo pedir con 95 % de servicio?"]}


# --------------------------------------------------------------------------------------------- análisis con datos
def snap(ctx, info):
    """Ventas en días SNAP frente a días normales (pasado) o los días SNAP de las fechas pronosticadas (futuro)."""
    t = info["normalizado"]
    lim = _limites()
    estado = (ctx.get("tienda") or "")[:2]
    if R_FUTURO.search(t) or info["entidades"].get("horizonte") or re.search(r"cuantos dias|que dias|dias snap hay|hay snap", t):
        ini, fin = lim["m"] + timedelta(days=1), lim["m"] + timedelta(days=28)
        if ctx.get("snap_rango") and re.search(r"esos dias|esas fechas|tambien hay|hay snap|tambien", t):
            ini, fin = date.fromisoformat(ctx["snap_rango"][0]), date.fromisoformat(ctx["snap_rango"][1])
        elif re.search(r"\bmayo\b", t):
            ini, fin = date(2016, 5, 1), date(2016, 5, 31)
        elif re.search(r"\bjunio\b", t):
            ini, fin = date(2016, 6, 1), date(2016, 6, 30)
        campos = {estado: SNAP_TIENDA[estado]} if estado in SNAP_TIENDA else {"CA": "snap_ca", "TX": "snap_tx", "WI": "snap_wi"}
        cal = list(Calendario.objects.filter(fecha__range=(ini, fin)).order_by("fecha"))
        if not cal:
            return {"texto": "No tengo calendario para ese periodo."}
        partes = []
        for e, campo in campos.items():
            dias = [c.fecha for c in cal if getattr(c, campo)]
            partes.append(f"{e}: {len(dias)} días" + (f" ({', '.join(d.strftime('%d/%m') for d in dias)})" if dias and len(dias) <= 12 else ""))
        return {"texto": f"Días con ayuda SNAP entre el {_f(ini)} y el {_f(min(fin, cal[-1].fecha))} (el calendario llega hasta el {_f(cal[-1].fecha)}): " + "; ".join(partes) + ". "
                         "Las proyecciones de LightGBM y TFT usan el calendario SNAP como variable, así que ya lo consideran.", "_ctx": {"snap_rango": [ini.isoformat(), fin.isoformat()]}}
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    desde, hasta, nombre, _, _ = _periodo(ctx, info, lim) or (lim["p"], lim["m"], "todo el histórico", None, None)
    base = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta))
    g = list(base.values("snap").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
    por = {x["snap"]: x for x in g}
    if True not in por or False not in por:
        return {"texto": f"En {nombre} no hay días SNAP y no SNAP para comparar en {desc}."}
    s, n = por[True], por[False]
    ps, pn = s["t"] / s["d"], n["t"] / n["d"]
    nota = "" if ctx.get("tienda") else " (cada fila usa el calendario SNAP de su estado: CA, TX o WI)"
    return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {desc} vendió unas {R.fmt1(ps)} unidades por día en días SNAP y {R.fmt1(pn)} en días sin SNAP: en días SNAP se vende un {_pct(ps, pn)}{nota}.",
            **_tabla(["Tipo de día", "Días", "Unidades por día"], [["SNAP", R.fmt(s["d"]), R.fmt1(ps)], ["Sin SNAP", R.fmt(n["d"]), R.fmt1(pn)]])}


def fin_semana(ctx, info):
    t = info["normalizado"]
    lim = _limites()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    futuro = (R_FUTURO.search(t) or info["entidades"].get("horizonte")) and not info["entidades"].get("pasado")
    if futuro:
        from apps.pronosticos.models import Prediccion
        corrida = R._activa("lightgbm")
        if not corrida:
            return R._sin_predicciones()
        filas = list(Prediccion.objects.filter(corrida=corrida, serie__in=qs).annotate(dsem=ExtractWeekDay("fecha")).values("dsem").annotate(t=Sum("p50"), d=Count("fecha", distinct=True)))
        fin = [x for x in filas if x["dsem"] in (1, 7)]
        sem = [x for x in filas if x["dsem"] not in (1, 7)]
        tf, tw = sum(x["t"] for x in fin), sum(x["t"] for x in sem)
        df, dw = sum(x["d"] for x in fin), sum(x["d"] for x in sem)
        if not df or not dw:
            return {"texto": "No tengo proyección diaria para ese periodo."}
        return {"texto": f"Según la proyección diaria (mediana) de los próximos 28 días, {desc} venderá unas {R.fmt(tf)} unidades en los {df} días de fin de semana ({R.fmt1(tf / df)} por día) "
                         f"y unas {R.fmt(tw)} entre semana ({R.fmt1(tw / dw)} por día). Un fin de semana típico (sábado y domingo) suma unas {R.fmt(2 * tf / df)} unidades.",
                **_tabla(["Tipo de día", "Días", "Unidades por día"], [["Fin de semana", str(df), R.fmt1(tf / df)], ["Entre semana", str(dw), R.fmt1(tw / dw)]])}
    per = _periodo(ctx, info, lim)
    desde, hasta, nombre, _, _ = per or (lim["p"], lim["m"], "todo el histórico", None, None)
    g = list(VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).annotate(dsem=ExtractWeekDay("fecha")).values("dsem").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
    fin = [x for x in g if x["dsem"] in (1, 7)]
    sem = [x for x in g if x["dsem"] not in (1, 7)]
    if not fin or not sem:
        return {"texto": f"En {nombre} no hay suficientes días para comparar fin de semana y entre semana."}
    pf = sum(x["t"] for x in fin) / sum(x["d"] for x in fin)
    pw = sum(x["t"] for x in sem) / sum(x["d"] for x in sem)
    mas = "los fines de semana" if pf >= pw else "entre semana"
    return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {desc} vendió unas {R.fmt1(pf)} unidades por día en fin de semana (sábado y domingo) y {R.fmt1(pw)} entre semana: se vende más {mas} (un {_pct(max(pf, pw), min(pf, pw))}).",
            **_tabla(["Tipo de día", "Unidades por día"], [["Fin de semana", R.fmt1(pf)], ["Entre semana", R.fmt1(pw)]]), "enlace": R._enlace("proyecciones", "Ver en Proyecciones", tienda=ctx.get("tienda"))}


EVENTOS = [  # (patrón en la pregunta, nombre del evento en el calendario, nombre en español)
    (r"navidad|christmas", ["Christmas"], "Navidad"), (r"accion de gracias|thanksgiving", ["Thanksgiving"], "Acción de Gracias"), (r"super ?bowl", ["SuperBowl"], "Super Bowl"),
    (r"halloween", ["Halloween"], "Halloween"), (r"pascua|easter", ["Easter"], "Pascua"), (r"4 de julio|independencia|independence", ["IndependenceDay"], "4 de julio"),
    (r"ano nuevo|new ?year", ["NewYear"], "Año Nuevo"), (r"dia de las madres|mother", ["Mother's day"], "Día de las Madres"), (r"dia del padre|father", ["Father's day"], "Día del Padre"),
    (r"san valentin|valentine", ["ValentinesDay"], "San Valentín"), (r"memorial|dia de los caidos", ["MemorialDay"], "Memorial Day"), (r"labor day|dia del trabajo", ["LaborDay"], "Labor Day"),
    (r"cinco de mayo", ["Cinco De Mayo"], "Cinco de Mayo"), (r"san patricio|st patrick", ["StPatricksDay"], "San Patricio"), (r"veterans|veteranos", ["VeteransDay"], "Día de los Veteranos"),
    (r"columbus|colon", ["ColumbusDay"], "Día de Colón"), (r"presidentes|presidents", ["PresidentsDay"], "Día de los Presidentes"), (r"ramadan", ["Ramadan starts"], "inicio del Ramadán"),
    (r"nba", ["NBAFinalsStart", "NBAFinalsEnd"], "finales de la NBA"), (r"luther king", ["MartinLutherKingDay"], "Martin Luther King"),
]


def eventos(ctx, info):
    t = info["normalizado"]
    lim = _limites()
    ents = info["entidades"]
    futuro = R_FUTURO.search(t) or ents.get("horizonte")
    if re.search(r"que eventos|cuales eventos|hay (?:algun )?(?:evento|feriado|festivo)|eventos? (?:del calendario|hay|en el)|proxim\w+ (?:eventos|feriados)|fechas especiales|dias especiales", t) and (futuro or not _anios(t)) \
            and not any(re.search(rx, t) for rx, _, _ in EVENTOS):
        ini, fin = (lim["m"] + timedelta(days=1), lim["m"] + timedelta(days=28)) if futuro else (lim["m"] - timedelta(days=27), lim["m"])
        filas = [[_f(c.fecha), c.evento, c.tipo_evento] for c in Calendario.objects.filter(fecha__range=(ini, fin)).exclude(evento="").order_by("fecha")]
        if not filas:
            return {"texto": f"Entre el {_f(ini)} y el {_f(fin)} el calendario no marca ningún evento."}
        return {"texto": f"Eventos del calendario entre el {_f(ini)} y el {_f(fin)}:", **_tabla(["Fecha", "Evento", "Tipo"], filas)}
    elegidos = [(nombres, esp) for rx, nombres, esp in EVENTOS if re.search(rx, t)]
    black = re.search(r"black friday|viernes negro", t)
    if black:
        elegidos = [(["Thanksgiving"], "Black Friday (el día siguiente a Acción de Gracias)")]
    if not elegidos:
        tipo = "Religious" if re.search(r"religios", t) else "Sporting" if re.search(r"deportiv|nba|super ?bowl", t) else None
        if tipo:
            nombres = list(Calendario.objects.filter(tipo_evento=tipo).values_list("evento", flat=True).distinct())
            elegidos = [(nombres, "los eventos religiosos" if tipo == "Religious" else "los eventos deportivos")]
        elif re.search(r"que evento|cual evento|mas impacto|mayor impacto|evento .*mas ventas|eventos? .*(?:suben|aumentan)", t) or (ctx.get("ranking_eventos") and len(t.split()) <= 6):
            return ranking_eventos(ctx, info)
        else:
            return {"texto": "Puedo comparar las ventas en eventos del calendario como Navidad, Acción de Gracias, Super Bowl, Halloween, Pascua, el 4 de julio, Año Nuevo, Día de las Madres, "
                             "San Valentín o Memorial Day. ¿Cuál te interesa?", "sugerencias": ["¿Cuánto se vendió en el Super Bowl frente a un día normal?"]}
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    anios = _anios(t)
    if len(elegidos) > 1:                                            # «¿qué evento vendió más: Pascua, Día de los Caídos o 4 de julio?»
        ventas_ev = VentaDiaria.objects.filter(serie__in=qs)
        filas, medias = [], {}
        for nombres_ev, esp_ev in elegidos:
            fechas_ev = [d for d in Calendario.objects.filter(evento__in=nombres_ev).values_list("fecha", flat=True) if lim["p"] <= d <= lim["m"] and (not anios or d.year in anios)]
            tot = {x["fecha"]: x["t"] for x in ventas_ev.filter(fecha__in=fechas_ev).values("fecha").annotate(t=Sum("unidades"))}
            if fechas_ev:
                medias[esp_ev] = sum(tot.get(d, 0) for d in fechas_ev) / len(fechas_ev)
                filas.append([esp_ev, str(len(fechas_ev)), R.fmt(medias[esp_ev])])
        if not medias:
            return {"texto": "No encuentro esos eventos en las fechas registradas."}
        filas.sort(key=lambda f: -medias[f[0]])
        return {"texto": f"Entre esos eventos, el de más ventas por día fue {filas[0][0]}, con unas {filas[0][2]} unidades de {desc} en promedio.", **_tabla(["Evento", "Fechas", "Unidades por día (promedio)"], filas)}
    nombres, esp = elegidos[0]
    fechas = sorted(Calendario.objects.filter(evento__in=nombres).values_list("fecha", flat=True))
    if black:
        fechas = [d + timedelta(days=1) for d in fechas]
    fechas = [d for d in fechas if d <= lim["m"] and d >= lim["p"] and (not anios or d.year in anios)]
    if not fechas:
        return {"texto": f"No encuentro {esp} en las fechas registradas (del {_f(lim['p'])} al {_f(lim['m'])})."}
    ventas = VentaDiaria.objects.filter(serie__in=qs)
    agrupar = ents.get("agrupar")
    if agrupar in ("tienda", "categoria", "departamento") and not ctx.get(agrupar) and len(fechas) <= 3:
        campo = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}[agrupar]
        g = list(ventas.filter(fecha__in=fechas).values(campo).annotate(u=Sum("unidades")).order_by("-u"))
        fch = " y ".join(_f(d) for d in fechas)
        return {"texto": f"Ventas en {esp} ({fch}) por {agrupar if agrupar != 'categoria' else 'categoría'}: la mayor fue {g[0][campo]} con {R.fmt(g[0]['u'])} unidades.",
                "columnas": [agrupar.capitalize() if agrupar != "categoria" else "Categoría", "Unidades"], "filas": [[x[campo], R.fmt(x["u"])] for x in g]}
    por_dia = {x["fecha"]: x["t"] for x in ventas.filter(fecha__range=(min(fechas), max(fechas))).values("fecha").annotate(t=Sum("unidades"))}
    filas, difs = [], []
    for d in fechas:
        ref = ventas.filter(fecha__range=(d - timedelta(days=28), d + timedelta(days=28)), fecha__week_day=d.isoweekday() % 7 + 1).exclude(fecha=d).values("fecha").annotate(t=Sum("unidades"))
        prom = sum(x["t"] for x in ref) / len(ref) if ref else 0
        v = por_dia.get(d, 0)
        filas.append([_f(d), R.fmt(v), R.fmt(prom), (f"{round(100 * (v - prom) / prom):+d} %" if prom else "—")])
        if prom:
            difs.append((v - prom) / prom)
    media = sum(difs) / len(difs) if difs else None
    resumen = (f" En promedio, ese día se vendió un {abs(round(100 * media))} % {'más' if media >= 0 else 'menos'} que el mismo día de la semana en las 4 semanas de alrededor." if media is not None else "")
    if len(fechas) == 1:
        v = por_dia.get(fechas[0], 0)
        base = filas[0][2]
        texto = f"En {esp} ({_f(fechas[0])}), {desc} vendió {R.fmt(v)} unidades, frente a unas {base} en un mismo día de la semana normal.{resumen and ''}"
        if v == 0:
            texto += " Ese día las tiendas no registran ventas (suele ser un día cerrado)."
        return {"texto": texto, **_tabla(["Fecha", "Unidades", "Día normal (referencia)", "Diferencia"], filas), "_ctx": {"pasado": {"fecha": fechas[0].isoformat(), "etiqueta": "ese día"}, "dia_ref": fechas[0].isoformat()}}
    if all(por_dia.get(d, 0) == 0 for d in fechas):
        resumen += " Ese día las tiendas no registran ventas (suele ser un día cerrado)."
    return {"texto": f"Ventas de {desc} en {esp} ({len(fechas)} fechas registradas) frente a un día equivalente normal.{resumen}",
            **_tabla(["Fecha", "Unidades", "Día normal (referencia)", "Diferencia"], filas)}


def ranking_eventos(ctx, info):
    """Qué eventos del calendario suben o bajan más las ventas respecto a un día equivalente normal."""
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    lim = _limites()
    anios = [a for a in _anios(info["normalizado"]) if 2011 <= a <= 2016]
    ventas = VentaDiaria.objects.filter(serie__in=qs)
    cal = [(c.fecha, c.evento) for c in Calendario.objects.exclude(evento="").filter(fecha__range=(lim["p"], lim["m"])) if not anios or c.fecha.year in anios]
    por_evento = {}
    for d, ev in cal:
        total = ventas.filter(fecha=d).aggregate(t=Sum("unidades"))["t"] or 0
        ref = list(ventas.filter(fecha__range=(d - timedelta(days=28), d + timedelta(days=28)), fecha__week_day=d.isoweekday() % 7 + 1).exclude(fecha=d).values("fecha").annotate(t=Sum("unidades")))
        if ref:
            prom = sum(x["t"] for x in ref) / len(ref)
            if prom:
                por_evento.setdefault(ev, []).append((total - prom) / prom)
    if not por_evento:
        return {"texto": "No encuentro eventos en ese periodo."}
    medias = sorted(((sum(v) / len(v), ev, len(v)) for ev, v in por_evento.items()), reverse=True)
    filas = [[ev, str(n), f"{100 * m:+.0f} %"] for m, ev, n in medias]
    return {"_ctx": {"ranking_eventos": True}, "texto": f"Efecto de los eventos del calendario en las ventas de {desc}" + (f" en {', '.join(str(a) for a in anios)}" if anios else "") +
                     f" (frente al mismo día de la semana en las 4 semanas de alrededor): suben más con {medias[0][1]} ({100 * medias[0][0]:+.0f} %) y bajan más con {medias[-1][1]} ({100 * medias[-1][0]:+.0f} %).",
            "columnas": ["Evento", "Fechas", "Diferencia promedio"], "filas": filas}


def _precio_actual(ids):
    ultimo = PrecioSemanal.objects.aggregate(m=Max("wm_yr_wk"))["m"]
    return {x["serie_id"]: float(x["precio"]) for x in PrecioSemanal.objects.filter(serie_id__in=ids, wm_yr_wk=ultimo).values("serie_id", "precio")}, ultimo


def precio(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    lim = _limites()
    actual, ult = _precio_actual(ids)
    usd = lambda x: f"${x:,.2f}"
    if len(ids) == 1:
        s = qs.first()
        sem = {c["wm_yr_wk"]: c["anio"] for c in Calendario.objects.values("wm_yr_wk", "anio").distinct()}
        hist = list(PrecioSemanal.objects.filter(serie=s).order_by("wm_yr_wk").values_list("wm_yr_wk", "precio"))
        if not hist:
            return {"texto": f"No tengo precios registrados para {desc}."}
        p_act = float(hist[-1][1])
        p_min, p_max = min(float(p) for _, p in hist), max(float(p) for _, p in hist)
        hace_ano = [float(p) for w, p in hist if w <= ult - 52]
        cambios = sum(1 for (_, a), (_, b) in zip(hist, hist[1:]) if a != b)
        texto = f"El precio actual de {desc} es {usd(p_act)}. En el histórico osciló entre {usd(p_min)} y {usd(p_max)} y cambió {cambios} veces."
        if hace_ano:
            texto += f" Hace un año costaba {usd(hace_ano[-1])}: {'subió' if p_act > hace_ano[-1] else 'bajó' if p_act < hace_ano[-1] else 'no cambió'}" + (f" un {abs(round(100 * (p_act - hace_ano[-1]) / hace_ano[-1]))} %." if p_act != hace_ano[-1] else ".")
        if re.search(r"promedio", t) and ents.get("pasado") and ents["pasado"].get("anio"):
            y = ents["pasado"]["anio"]
            ps = [float(p) for w, p in hist if sem.get(w) == y]
            if ps:
                texto = f"El precio promedio de {desc} en {y} fue {usd(sum(ps) / len(ps))}. " + texto
        return {"texto": texto}
    asc = ents.get("orden") == "asc" or re.search(r"\bbarat|\beconomic|\bmenor precio", t)
    if ents.get("agrupar") in ("categoria", "tienda", "departamento") or re.search(r"departamento|categoria|tienda", t) and re.search(r"promedio|mas (?:caro|cara)|mas barat", t) and not ents.get("buscar"):
        clave = ents.get("agrupar") or ("departamento" if "departamento" in t else "categoria" if "categoria" in t else "tienda")
        campo = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}[clave]
        g = list(PrecioSemanal.objects.filter(serie_id__in=ids, wm_yr_wk=ult).values(campo).annotate(p=Avg("precio")).order_by("p" if asc else "-p"))
        filas = [[x[campo], usd(float(x["p"]))] for x in g]
        return {"texto": f"El precio promedio actual más {'bajo' if asc else 'alto'} está en {filas[0][0]}, con {filas[0][1]}.", **_tabla([clave.capitalize(), "Precio promedio actual"], filas)}
    series = {s.id: s for s in qs}
    orden = sorted(actual.items(), key=lambda kv: kv[1], reverse=not asc)[:min(ents.get("cantidad") or 5, 15)]
    filas = [[series[i].item_id, series[i].tienda.codigo, usd(p)] for i, p in orden]
    return {"texto": f"Los productos de {desc} con el precio actual más {'bajo' if asc else 'alto'} (última semana de precios cargada):", **_tabla(["Producto", "Tienda", "Precio actual"], filas)}


def ingresos(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    lim = _limites()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    futuro = (R_FUTURO.search(t) or (ents.get("horizonte") and not ctx.get("pasado"))) and not ents.get("pasado")
    ingreso = ExpressionWrapper(F("unidades") * F("precio"), output_field=FloatField())
    usd = lambda x: f"${x:,.0f}"
    if futuro:
        corrida = R._activa("lightgbm")
        if not corrida:
            return R._sin_predicciones()
        ult, _ = _precio_actual(list(qs.values_list("id", flat=True)))
        from apps.pronosticos.models import Prediccion
        tot = sum(x["u"] * ult.get(x["serie_id"], 0) for x in Prediccion.objects.filter(corrida=corrida, serie__in=qs).values("serie_id").annotate(u=Sum("p50")))
        return {"texto": f"Ingresos estimados de {desc} para los próximos 28 días: unos {usd(tot)} (demanda mediana proyectada × precio actual; es una aproximación sin descuentos ni cambios de precio)."}
    per = _periodo(ctx, info, lim, defecto="mes")
    if per is None:
        return periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    base = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta), precio__isnull=False)
    total = base.aggregate(t=Sum(ingreso))["t"] or 0
    agrupar = ents.get("agrupar")
    if agrupar in ("categoria", "tienda", "departamento") and not ctx.get(agrupar):
        campo = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}[agrupar]
        g = list(base.values(campo).annotate(i=Sum(ingreso)).order_by("-i"))
        filas = [[x[campo], usd(x["i"]), f"{round(100 * x['i'] / total)} %" if total else "—"] for x in g]
        return {"texto": f"En {nombre} ({_rango(desde, hasta)}) los ingresos aproximados (unidades × precio) fueron de {usd(total)}; el mayor aporte es de {filas[0][0]} ({usd(g[0]['i'])}).",
                **_tabla([agrupar.capitalize(), "Ingresos aproximados", "Participación"], filas)}
    if (ents.get("buscar") or ents.get("cantidad") or re.search(r"\bproductos?\b|\bproducto\b", t)) and len(qs) > 1:
        cant = min(ents.get("cantidad") or (10 if ents.get("buscar", {}).get("plural") or re.search(r"productos", t) else 1), 15)
        g = list(base.values("serie__item_id", "serie__tienda__codigo").annotate(i=Sum(ingreso)).order_by("-i")[:cant])
        filas = [[x["serie__item_id"], x["serie__tienda__codigo"], usd(x["i"])] for x in g]
        if len(filas) == 1:
            return {"texto": f"En {nombre} ({_rango(desde, hasta)}), el producto con más ingresos aproximados de {desc} fue {filas[0][0]} en la tienda {filas[0][1]}, con {filas[0][2]} (de {usd(total)} en total).", **_tabla(["Producto", "Tienda", "Ingresos aproximados"], filas)}
        return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {desc} generó unos {usd(total)}. Los {len(filas)} productos con más ingresos aproximados:", **_tabla(["Producto", "Tienda", "Ingresos aproximados"], filas)}
    return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {desc} generó ingresos aproximados de {usd(total)} (unidades vendidas × precio de venta; no incluye costos, impuestos ni descuentos que no estén en el precio)."}


def participacion(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    lim = _limites()
    per = _periodo(ctx, info, lim)
    if per is None:
        return periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    base = VentaDiaria.objects.filter(fecha__range=(desde, hasta))
    total = base.aggregate(t=Sum("unidades"))["t"] or 0
    if not total:
        return {"texto": "No hay ventas en ese periodo."}
    campos = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}
    agrupar = ents.get("agrupar") or next((k for k in ("categoria", "tienda", "departamento") if re.search(rf"cada {k}|por {k}|las {k}s|los {k}s|{k}s\b", t) and not ctx.get(k)), None)
    if agrupar is None and re.search(r"cada categoria|por categoria", t):
        agrupar = "categoria"
    if agrupar and not ctx.get(agrupar):
        g = list(base.values(campos[agrupar]).annotate(u=Sum("unidades")).order_by("-u"))
        filas = [[x[campos[agrupar]], R.fmt(x["u"]), f"{100 * x['u'] / total:.1f} %".replace(".", ",")] for x in g]
        return {"texto": f"En {nombre} ({_rango(desde, hasta)}) se vendieron {R.fmt(total)} unidades en total. Participación por {agrupar if agrupar != 'categoria' else 'categoría'}:", **_tabla([agrupar.capitalize() if agrupar != 'categoria' else 'Categoría', "Unidades", "Participación"], filas)}
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    parte = base.filter(serie__in=qs).aggregate(t=Sum("unidades"))["t"] or 0
    if desc.startswith("todas las"):
        return {"texto": f"En {nombre} ({_rango(desde, hasta)}) se vendieron {R.fmt(total)} unidades en total. Dime de qué tienda, categoría o producto quieres la participación."}
    return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {desc} vendió {R.fmt(parte)} de las {R.fmt(total)} unidades totales: el {f'{100 * parte / total:.1f}'.replace('.', ',')} % de las ventas."}


def primera_venta(ctx, info):
    t = info["normalizado"]
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    lim = _limites()
    if qs.count() == 1:
        s = qs.first()
        if not s.primera_venta:
            return {"texto": f"No tengo la fecha de la primera venta de {desc}."}
        return {"texto": f"{desc} se empezó a vender el {_f(s.primera_venta)}" + (" (desde el primer día del histórico)." if s.primera_venta <= lim["p"] + timedelta(days=1) else ".")}
    desde = lim["m"] - timedelta(days=365)
    nuevos = list(qs.filter(primera_venta__gt=desde).order_by("-primera_venta")[:15])
    if not nuevos:
        return {"texto": f"En {desc} no hay productos que hayan empezado a venderse en el último año: todos se vendían ya antes del {_f(desde)}."}
    filas = [[s.item_id, s.tienda.codigo, _f(s.primera_venta)] for s in nuevos]
    return {"texto": f"En {desc}, estos son los productos que empezaron a venderse en el último año (desde el {_f(desde)}):", **_tabla(["Producto", "Tienda", "Primera venta"], filas)}


def sin_ventas(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    lim = _limites()
    if qs.count() == 1:
        s = qs.first()
        per = _periodo(ctx, info, lim)
        if per is None:
            return periodo_sin_datos(ctx, info)
        desde, hasta, nombre, _, _ = per
        desde = max(desde, s.primera_venta or desde)
        base = VentaDiaria.objects.filter(serie=s, fecha__range=(desde, hasta))
        dias = base.count()
        ceros = base.filter(unidades=0).count()
        if not dias:
            return {"texto": f"No tengo ventas de {desc} en ese periodo."}
        return {"texto": f"{desc} no vendió nada en {R.fmt(ceros)} de {R.fmt(dias)} días ({f'{100 * ceros / dias:.1f}'.replace('.', ',')} %) en {nombre}, contando desde que se empezó a vender ({_f(desde)})."}
    per = _periodo(ctx, info, lim, defecto="mes")
    if per is None:
        return periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    tot = {x["serie_id"]: x["t"] for x in VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values("serie_id").annotate(t=Sum("unidades"))}
    if re.search(r"dejaron de venderse|dejo de venderse|ya no se vende", t):
        ultimas = {x["serie_id"]: x["u"] for x in VentaDiaria.objects.filter(serie__in=qs, unidades__gt=0).values("serie_id").annotate(u=Max("fecha"))}
        corte = lim["m"] - timedelta(days=28)
        paradas = sorted([(u, sid) for sid, u in ultimas.items() if u < corte])
        if not paradas:
            return {"texto": f"En {desc}, todos los productos registraron al menos una venta en los últimos 28 días."}
        series = {s.id: s for s in qs}
        filas = [[series[sid].item_id, series[sid].tienda.codigo, _f(u)] for u, sid in paradas[:15]]
        return {"texto": f"En {desc}, {len(paradas)} productos no venden desde hace más de 28 días. Estos son los de última venta más antigua:", **_tabla(["Producto", "Tienda", "Última venta"], filas)}
    series = {s.id: s for s in qs}
    nulos = [sid for sid in series if tot.get(sid, 0) == 0]
    if not nulos:
        return {"texto": f"En {nombre} ({_rango(desde, hasta)}), todos los productos de {desc} vendieron al menos una unidad."}
    filas = [[series[sid].item_id, series[sid].tienda.codigo, series[sid].departamento.codigo] for sid in nulos[:15]]
    return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {len(nulos)} de {len(series)} productos de {desc} no vendieron ninguna unidad" + (". Estos son algunos:" if len(nulos) > 15 else ":"), **_tabla(["Producto", "Tienda", "Departamento"], filas)}


def umbral(ctx, info):
    t = info["normalizado"]
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    m = re.search(r"(mas|mayor|superan|pasan|menos|menor) de (\d[\d.]*)", t)
    if not m:
        return {"texto": "¿Qué cifra quieres usar como límite? Por ejemplo: «¿cuántos productos vendieron más de 1000 unidades en 2015?»."}
    n = float(m[2].replace(".", ""))
    mayor = m[1] in ("mas", "mayor", "superan", "pasan")
    lim = _limites()
    per = _periodo(ctx, info, lim)
    if per is None:
        return periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    por_dia = bool(re.search(r"al dia|por dia|diari|en promedio", t))
    g = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values("serie_id").annotate(t=Sum("unidades"), d=Count("id"))
    valores = [x["t"] / x["d"] if por_dia else x["t"] for x in g]
    cuantos = sum(1 for v in valores if (v > n if mayor else v < n))
    return {"texto": f"En {nombre} ({_rango(desde, hasta)}), {cuantos} de {len(valores)} productos (series) de {desc} vendieron {'más' if mayor else 'menos'} de {R.fmt(n)} {'unidad' if n == 1 else 'unidades'}" + (" por día en promedio." if por_dia else " en total.")}


def tendencia(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    lim = _limites()
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    anios = sorted(set(a for a in _anios(t) if 2011 <= a <= 2016))
    base = VentaDiaria.objects.filter(serie__in=qs)
    campos = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}
    agrupar = ents.get("agrupar") if ents.get("agrupar") in campos else next((k for k in campos if re.search(rf"cada {k}|por {k}|las {k}s|{k}s\b", t) and not ctx.get(k)), None)
    quien_crecio = re.search(r"productos?|series?|articulo", t) and re.search(r"mas creci|mas cayo|mas subio|mas bajo|mayor crecimiento|mayor caida|mas aumento|mas disminuy|creci\w+ mas|cay\w+ mas|que mas|cual creci|cual cayo", t)
    # comparación entre dos años (por producto o por grupo)
    if len(anios) >= 2 and (agrupar or quien_crecio):
        a0, a1 = anios[0], anios[-1]
        rango = lambda a: (date(a, 1, 1), min(date(a, 12, 31), lim["m"]))
        r0, r1 = rango(a0), rango(a1)
        llave = campos[agrupar] if agrupar else "serie_id"
        v0 = {x[llave]: x["t"] for x in base.filter(fecha__range=r0).values(llave).annotate(t=Sum("unidades"))}
        v1 = {x[llave]: x["t"] for x in base.filter(fecha__range=r1).values(llave).annotate(t=Sum("unidades"))}
        claves = [k for k in v0 if v0[k] > 0 and k in v1]
        var = {k: (v1[k] - v0[k], 100 * (v1[k] - v0[k]) / v0[k]) for k in claves}
        if agrupar:
            filas = [[k, R.fmt(v0[k]), R.fmt(v1[k]), f"{var[k][1]:+.1f} %".replace(".", ",")] for k in sorted(var, key=lambda k: -var[k][1])]
            return {"texto": f"Variación de ventas de {a0} a {a1} por {agrupar if agrupar != 'categoria' else 'categoría'}" + (" (el año final está incompleto)" if a1 == lim["m"].year else "") + ":", **_tabla([agrupar.capitalize() if agrupar != 'categoria' else 'Categoría', str(a0), str(a1), "Variación"], filas)}
        series = {s.id: s for s in qs}
        cae = bool(re.search(r"cayo|caida|bajo|disminuy|menos", t)) and not re.search(r"mas creci|mayor crecimiento|mas subio", t)
        orden = sorted(var, key=lambda k: var[k][0] if True else 0, reverse=not cae)[:5]
        filas = [[series[k].item_id, series[k].tienda.codigo, R.fmt(v0[k]), R.fmt(v1[k]), R.fmt(var[k][0]), f"{var[k][1]:+.0f} %"] for k in orden]
        return {"texto": f"Los 5 productos de {desc} que más {'cayeron' if cae else 'crecieron'} en unidades de {a0} a {a1}:", **_tabla(["Producto", "Tienda", str(a0), str(a1), "Cambio (unid.)", "Cambio %"], filas)}
    if quien_crecio and not anios:   # sin años: últimos 28 días frente a los 28 anteriores
        fin = lim["m"]
        r1, r0 = (fin - timedelta(days=27), fin), (fin - timedelta(days=55), fin - timedelta(days=28))
        v0 = {x["serie_id"]: x["t"] for x in base.filter(fecha__range=r0).values("serie_id").annotate(t=Sum("unidades"))}
        v1 = {x["serie_id"]: x["t"] for x in base.filter(fecha__range=r1).values("serie_id").annotate(t=Sum("unidades"))}
        var = {k: v1.get(k, 0) - v0[k] for k in v0}
        cae = bool(re.search(r"cayo|caida|bajo|disminuy", t))
        orden = sorted(var, key=var.get, reverse=not cae)[:5]
        series = {s.id: s for s in qs}
        filas = [[series[k].item_id, series[k].tienda.codigo, R.fmt(v0[k]), R.fmt(v1.get(k, 0)), R.fmt(var[k])] for k in orden]
        return {"texto": f"Los 5 productos de {desc} que más {'cayeron' if cae else 'crecieron'} en los últimos 28 días frente a los 28 anteriores:", **_tabla(["Producto", "Tienda", "28 días previos", "Últimos 28 días", "Cambio (unid.)"], filas)}
    # evolución por año (o por mes si se pide)
    if re.search(r"mensual|por mes|cada mes|mes a mes|evolucion mensual", t):
        rango_a = anios or [lim["m"].year]
        g = list(base.filter(fecha__year__gte=min(rango_a), fecha__year__lte=max(rango_a)).values("fecha__year", "fecha__month").annotate(t=Sum("unidades")).order_by("fecha__year", "fecha__month"))
        filas = [[f"{R.MESES_TODOS[x['fecha__month']].capitalize()} {x['fecha__year']}", R.fmt(x["t"])] for x in g]
        return {"texto": f"Ventas mensuales de {desc}" + (f" de {min(rango_a)} a {max(rango_a)}" if len(set(rango_a)) > 1 else f" en {rango_a[0]}") + ":", **_tabla(["Mes", "Unidades"], filas)}
    g = list(base.annotate(a=ExtractYear("fecha")).values("a").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)).order_by("a"))
    if anios:
        g = [x for x in g if min(anios) <= x["a"] <= max(anios)] if len(anios) > 1 else g
    filas = []
    prev = None
    for x in g:
        parcial = x["a"] in (2011, lim["m"].year) and (x["a"] == lim["m"].year or lim["p"].year == x["a"])
        filas.append([str(x["a"]) + (" (parcial)" if parcial else ""), R.fmt(x["t"]), R.fmt1(x["t"] / x["d"]), "—" if prev is None or parcial else f"{100 * (x['t'] / x['d'] - prev) / prev:+.1f} %".replace(".", ",")])
        prev = x["t"] / x["d"]
    completos = [x for x in g if x["a"] not in (2011, lim["m"].year)]
    texto = f"Ventas de {desc} por año (la variación compara el promedio por día, porque 2011 y 2016 están incompletos):"
    if g and re.search(r"tendencia|a la baja|al alza|esta bajando|esta subiendo|baja|sube", t):
        fin = lim["m"]
        v1 = base.filter(fecha__range=(fin - timedelta(days=364), fin)).aggregate(t=Sum("unidades"))["t"] or 0
        v0 = base.filter(fecha__range=(fin - timedelta(days=729), fin - timedelta(days=365))).aggregate(t=Sum("unidades"))["t"] or 0
        if v0:
            texto_t = f"En los últimos 12 meses {desc} vendió {R.fmt(v1)} unidades, {_pct(v1, v0)} que en los 12 meses anteriores ({R.fmt(v0)}): la tendencia es {'prácticamente estable' if abs(v1 - v0) < 0.02 * v0 else 'al alza' if v1 >= v0 else 'a la baja'}. "
        else:
            texto_t = ""
    else:
        texto_t = ""
    if g:
        mejor = max(g, key=lambda x: x["t"] / x["d"])
        texto = texto_t + f"El año con más ventas por día de {desc} fue {mejor['a']} ({R.fmt1(mejor['t'] / mejor['d'])} unidades por día). " + texto
    if len(completos) >= 2:
        u, p = completos[-1], completos[-2]
        texto += f" de {p['a']} a {u['a']} las ventas {'subieron' if u['t'] >= p['t'] else 'bajaron'} un {_pct(u['t'], p['t']).split(' ')[0]} % ({R.fmt(p['t'])} → {R.fmt(u['t'])} unidades)."
    return {"texto": texto, **_tabla(["Año", "Unidades", "Unidades por día", "Variación"], filas)}


def semana(ctx, info):
    t = info["normalizado"]
    from django.db.models.functions import TruncWeek
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    lim = _limites()
    per = _periodo(ctx, info, lim)
    if per is None:
        return periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    g = list(VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).annotate(w=TruncWeek("fecha")).values("w").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
    g = [x for x in g if x["d"] == 7]
    if not g:
        return {"texto": "No hay semanas completas en ese periodo."}
    peor = bool(re.search(r"peor|menos", t))
    g.sort(key=lambda x: x["t"], reverse=not peor)
    filas = [[f"{_f(x['w'])} al {_f(x['w'] + timedelta(days=6))}", R.fmt(x["t"])] for x in g[:5]]
    return {"texto": f"En {nombre}, la semana con {'menos' if peor else 'más'} ventas de {desc} fue la del {filas[0][0]}, con {filas[0][1]} unidades.", **_tabla(["Semana", "Unidades"], filas)}


def _demanda_diaria_mediana(ids):
    agg = R._activa("lgbm_agregado")
    if not agg:
        return None, {}
    d = dict(R.PrediccionAgregada.objects.filter(corrida=agg, serie_id__in=ids, horizonte="28d", tau=0.5).values_list("serie_id", "unidades"))
    return agg, {k: v / 28 for k, v in d.items()}


def cobertura(ctx, info):
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    agg, dia = _demanda_diaria_mediana(ids)
    if not agg:
        return R._sin_predicciones()
    inv = R._inventarios(ids)
    if not inv:
        return {"texto": f"No hay inventario registrado para {desc}, así que no puedo calcular cuántos días dura.", "enlace": R._enlace("reposicion", "Ir a Reposición", tienda=ctx.get("tienda"))}
    sim = InventarioActual.objects.filter(serie_id__in=ids, simulado=True).exists()
    aviso = " Ojo: hay inventarios simulados (de demostración), no son datos reales." if sim else ""
    series = {s.id: s for s in qs}
    if len(ids) == 1:
        sid = ids[0]
        if sid not in inv or not dia.get(sid):
            return {"texto": f"No tengo inventario o demanda proyectada para {desc}."}
        dias_alcanza = inv[sid] / dia[sid]
        return {"texto": f"{desc} tiene {R.fmt(inv[sid])} unidades y se proyecta vender unas {R.fmt1(dia[sid])} por día (mediana), así que el inventario alcanza para unos {R.fmt1(dias_alcanza)} días: "
                         + ("cubre los 28 días del pronóstico." if dias_alcanza >= 28 else f"no cubre los 28 días del pronóstico (faltarían unas {R.fmt(28 * dia[sid] - inv[sid])} unidades).") + aviso}
    tot_inv = sum(inv.get(s, 0) for s in ids if dia.get(s))
    tot_dia = sum(dia.get(s, 0) for s in ids if s in inv)
    cubre28 = (f" Para los 28 días del pronóstico se necesitan unas {R.fmt(28 * tot_dia)} unidades (mediana): "
               + (f"faltarían unas {R.fmt(28 * tot_dia - tot_inv)}." if tot_inv < 28 * tot_dia else f"sobrarían unas {R.fmt(tot_inv - 28 * tot_dia)}.")) if tot_dia else ""
    filas = sorted(((inv[s] / dia[s], s) for s in ids if s in inv and dia.get(s, 0) > 0), key=lambda x: x[0])
    filas = filas[: min(info["entidades"].get("cantidad") or 5, 15)]
    return {"texto": f"Para {desc}, el inventario registrado ({R.fmt(tot_inv)} unidades) cubre unos {R.fmt1(tot_inv / tot_dia) if tot_dia else '—'} días de la demanda mediana proyectada.{cubre28} Estos son los {len(filas)} productos con menos días de cobertura:{aviso}",
            **_tabla(["Producto", "Tienda", "Inventario", "Demanda diaria (mediana)", "Días de cobertura"], [[series[s].item_id, series[s].tienda.codigo, R.fmt(inv[s]), R.fmt1(dia[s]), R.fmt1(d)] for d, s in filas]),
            "enlace": R._enlace("reposicion", "Ver en Reposición", tienda=ctx.get("tienda"), categoria=ctx.get("categoria"))}


def nivel_actual(ctx, info):
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    agg = R._activa("lgbm_agregado")
    if not agg:
        return R._sin_predicciones()
    inv = R._inventarios(ids)
    if not inv:
        return {"texto": f"No hay inventario registrado para {desc}.", "enlace": R._enlace("reposicion", "Ir a Reposición")}
    sug = {}
    for s in SugerenciaReposicion.objects.filter(corrida=agg, serie_id__in=inv, politica="28d"):
        sug.setdefault(round(s.nivel_servicio, 2), {})[s.serie_id] = s.stock_objetivo
    filas = []
    for nivel in (0.8, 0.9, 0.95):
        d = sug.get(nivel, {})
        cubiertas = sum(1 for sid, o in d.items() if inv.get(sid, 0) >= o)
        filas.append([f"{round(nivel * 100)} %", f"{cubiertas} de {len(d)}", f"{100 * cubiertas / len(d):.0f} %" if d else "—"])
    sim = " (inventarios simulados de demostración)" if InventarioActual.objects.filter(serie_id__in=ids, simulado=True).exists() else ""
    return {"texto": f"El aplicativo no guarda un «nivel de servicio actual» como dato, pero se puede estimar: para {desc}{sim} esta es la parte de los productos cuyo inventario ya alcanza el stock objetivo de cada nivel:",
            **_tabla(["Nivel de servicio", "Productos cubiertos", "Porcentaje"], filas)}


def subir_nivel(ctx, info):
    qs, desc, error = _alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    agg = R._activa("lgbm_agregado")
    if not agg:
        return R._sin_predicciones()
    t = info["normalizado"]
    m = re.search(r"(80|90) ?%? ?(?:a|hasta) ?(90|95)", t)
    a, b = (int(m[1]), int(m[2])) if m else (90, 95)
    ta = R._suma_agregada(agg, ids, "28d", a / 100)
    tb = R._suma_agregada(agg, ids, "28d", b / 100)
    return {"texto": f"Para {desc}, subir el nivel de servicio de {a} % a {b} % sube el stock objetivo de 28 días de {R.fmt(ta)} a {R.fmt(tb)} unidades: {R.fmt(tb - ta)} unidades más ({_pct(tb, ta).split(' ')[0]} % extra). "
                     "Es el costo en unidades; el aplicativo no tiene costos para llevarlo a dinero."}


HANDLERS = {"fecha_invalida": fecha_invalida, "periodo_sin_datos": periodo_sin_datos, "tienda_desconocida": tienda_desconocida, "producto_desconocido": producto_desconocido,
            "escenarios": escenarios, "snap": snap, "fin_semana": fin_semana, "eventos": eventos, "precio": precio, "ingresos": ingresos, "participacion": participacion,
            "primera_venta": primera_venta, "sin_ventas": sin_ventas, "umbral": umbral, "tendencia": tendencia, "semana": semana, "cobertura": cobertura, "nivel_actual": nivel_actual,
            "subir_nivel": subir_nivel}


def responder(ctx, info):
    clave = info.get("clave") or detectar(info)
    if clave == "no_disponible":
        return no_disponible(info) or R.no_entendida(ctx, info)
    try:
        return HANDLERS[clave](ctx, info)
    except Exception as exc:                                         # un análisis que falla no debe tumbar el chat
        return {"texto": f"No pude calcular eso con los datos disponibles ({type(exc).__name__}). Prueba reformulando la pregunta o indicando la tienda, la categoría o el periodo.", "sugerencias": R.EJEMPLOS[:3]}


from . import analisis_extra                                           # noqa: E402  (al final: usa las funciones de este módulo)
HANDLERS.update(analisis_extra.EXTRA)


DOMINIO = re.compile(r"venta|vend|producto|tienda|categoria|departamento|inventario|stock|unidades|pedido|pedir|demanda|pronostic|proyecc|snap|calendario|serie|catalogo|modelo|reposicion|quiebre|precio de|dolares|ingres|servicio|nivel|cobertura|compar|evento|anos|navidad|semana|mes|ano|dia")
SIEMPRE = {"fecha_invalida", "periodo_sin_datos", "tienda_desconocida", "producto_desconocido", "no_disponible"}


def detectar(info, ctx=None):
    """Como _detectar, pero un análisis solo se activa si la pregunta menciona algo del aplicativo (evita atrapar preguntas de otros temas)."""
    clave = _detectar(info, ctx)
    if clave and clave not in SIEMPRE and not info["entidades"] and not DOMINIO.search(info["normalizado"]) and not (ctx or {}).get("clave_analisis") and not (ctx or {}).get("intencion"):
        return None
    return clave
