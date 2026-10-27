"""Orquesta un turno de conversación: entidades -> intención (con contexto) -> memoria de la conversación -> respuesta -> historial en la base."""
import re

from . import analisis, datos, entidades, modelo, respuestas

respuestas.FUNCIONES["analisis"] = analisis.responder                      # preguntas analíticas que se resuelven con reglas y consultas directas
respuestas.FUNCIONES["dato_no_disponible"] = lambda ctx, info: analisis.no_disponible(info) or respuestas.no_entendida(ctx, info)
DOMINIO_REGLAS = tuple(datos.INTENCIONES_DOMINIO) + ("analisis",)         # las intenciones que recuerdan tienda, producto, periodo...

UMBRAL_RECHAZO = 0.35      # por debajo de esta confianza no se acepta ninguna intención
UMBRAL_CONFIRMAR = 0.60    # entre ambos umbrales, si hay palabras del dominio, se pide confirmar
CLAVES_ALCANCE = ("producto", "departamento", "categoria")
PALABRAS_DOMINIO = ("stock", "inventario", "existencia", "demanda", "venta", "vender", "vendan", "pedido", "pedir", "reposi", "reabastec", "quiebre", "agot", "sobrante",
                    "exceso", "producto", "tienda", "categoria", "prediccion", "pronostico", "proyeccion", "modelo", "tft", "lightgbm", "p10", "p50", "p90", "servicio", "unidades",
                    "bodega", "almacen", "mercancia", "referencia", "articulo", "surt", "desabast", "rotacion", "mase")


def _palabras_dominio(info):
    t = info["normalizado"]
    return bool(info["entidades"]) or any(p in t for p in PALABRAS_DOMINIO)


def fusionar_contexto(ctx, info):
    """La memoria de la conversación: lo que el usuario menciona se recuerda y reemplaza lo anterior del mismo tipo."""
    ctx = dict(ctx)
    ents = {k: v for k, v in info["entidades"].items() if k not in ("cantidad", "agrupar", "buscar", "orden", "metrica")}      # lo transitorio no se recuerda
    if (ents.get("pasado") or {}).get("generico") and ctx.get("pasado"):          # «vendieron», «ese día»: si ya había un periodo recordado, se conserva
        ents.pop("pasado")
    for k in info["reset"]:
        ctx.pop(k, None)
    if "buscar" in info["entidades"] and "producto" not in ents:     # «¿qué producto...?» busca el producto: no se sigue usando el que se mencionó antes
        ctx.pop("producto", None)
    if any(k in ents for k in CLAVES_ALCANCE):                      # un nuevo producto, departamento o categoría reemplaza al anterior
        for k in CLAVES_ALCANCE:
            ctx.pop(k, None)
    if "pasado" in ents:                                            # el pasado (ventas registradas) y el futuro (proyección) se excluyen
        ctx.pop("horizonte", None)
    if "horizonte" in ents:
        ctx.pop("pasado", None)
    ctx.update(ents)
    return ctx


def decidir(clasif, texto, info, prev):
    """Devuelve (intención, confianza, opciones). 'confirmar' pide al usuario elegir entre las dos intenciones más probables."""
    pr = clasif.probabilidades(texto, prev)
    orden = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)
    intencion, conf = orden[0]
    dominio = _palabras_dominio(info)
    if conf < UMBRAL_RECHAZO:
        return ("no_entendida" if dominio else "fuera_de_contexto"), conf, None
    if intencion == "fuera_de_contexto" and not info["entidades"]:   # si el modelo cree que es de otro tema y no menciona nada del aplicativo, se rechaza
        return intencion, conf, None
    if conf < UMBRAL_CONFIRMAR and dominio:
        opciones = [i for i, _ in orden if i in datos.INTENCIONES_DOMINIO][:2]
        return "confirmar", conf, opciones
    return intencion, conf, None


RELLENO = {"mmm", "mm", "hmm", "eh", "ehh", "pues", "a", "ver", "bueno", "ok", "okey", "aja", "uhm", "um", "y", "entonces", "que", "si", "no", "ya", "vale", "sale", "dime", "oye", "este", "o", "sea", "como"}
AYUDA_APP = re.compile(r"\b(?:donde (?:veo|esta|estan|encuentro|puedo ver|se (?:ve|generan|entrena))|en que pestana|que filtros|que boton|que pestanas?|"
                       r"para que sirve (?:la |el |cada |esta )?(?:pestana|chat|pantalla|boton|aplicacion|aplicativo|herramienta|app)|explicame (?:las |la |cada )?pestanas?|primer dia|por donde empezar|"
                       r"como (?:cambio|selecciono|uso|veo|hago para ver|se usa|funciona (?:la |el |esta )?(?:herramienta|aplicacion|aplicativo|chat|sistema|app))|interpreto la grafica)\b")
ACCION_INICIO = re.compile(r"^(?:por favor,? |oye,? |ok,? )?(programa|mand\w*|enviame|envia|exporta|descarga|borra|elimina|lanza|ejecuta|actualiza|registra|guarda|cambi\w*|pon|activa|desactiva|re-?entrena|entrena|genera|crea|agrega|anade|sube|imprime|abre)\b")


FUTURO = re.compile(r"\b(?:va|van|vamos|iran|ira|sera|seran|vaya|vayan)\b|\bproxim\w*|\bsemana [1-4]\b|\bjunio\b|\bproyecc\w*|\bpronostic\w*|\bespera\w*|\bfuturo\b|\bestim\w*")


ORDINALES = {"primer": 0, "primero": 0, "primera": 0, "segundo": 1, "segunda": 1, "tercer": 2, "tercero": 2, "tercera": 2, "cuarto": 3, "cuarta": 3, "quinto": 4, "quinta": 4, "ultimo": -1, "ultima": -1}


def resolver_referencias(ctx, info):
    """«El segundo de la lista», «el siguiente»: toma el producto de la última tabla mostrada. Devuelve True si resolvió una referencia."""
    t = info["normalizado"]
    lista = ctx.get("lista") or []
    if not lista or "producto" in info["entidades"] or len(t.split()) > 14:
        return False
    idx = None
    if re.search(r"\b(?:el |la )?(?:siguiente|que sigue)\b", t):
        idx = (ctx.get("lista_idx") or 0) + 1
    else:
        m = re.search(r"\b(?:el |la )?(primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|ultim[oa])\b(?! (?:mes|dia|semana|trimestre|ano|registrad|vez))", t)
        if m and re.search(r"lista|ranking|ellos|esos|esas|producto|tabla|anterior|^el |^la |^y el |^y la |, ", t):
            idx = ORDINALES[m[1]]
    if idx is None:
        return False
    idx = len(lista) - 1 if idx == -1 else idx
    if not 0 <= idx < len(lista):
        return False
    prod, tienda = lista[idx]
    info["entidades"]["producto"] = prod
    if tienda:
        info["entidades"]["tienda"] = tienda
    info["ref"] = idx
    return True


def clasificar(clasif, texto, prev, info=None, ctx=None):
    """Clasificación completa que usa el chat: modelo, umbrales y reglas de seguridad. Devuelve (intención, confianza, opciones)."""
    info = info or entidades.extraer(texto)
    ctx = ctx or {}
    limpio = re.sub(r"^[^a-z0-9]+", "", info["normalizado"])
    if prev == "ventas_pasadas" and ctx.get("agrupar_ref") and re.match(r"^(?:y )?(?:cual (?:fue |es )?)?(?:el |la |lo )?(peor|mejor|menor|mayor|menos|mas)\b", info["normalizado"]) and len(info["normalizado"].split()) <= 5:
        info["entidades"]["agrupar"] = ctx["agrupar_ref"]                  # «¿Y el peor?» repite el ranking anterior en sentido contrario
        if re.match(r"^(?:y )?(?:cual (?:fue |es )?)?(?:el |la |lo )?(peor|menor|menos)\b", info["normalizado"]):
            info["entidades"]["orden"] = "asc"
        return "ventas_pasadas", 1.0, None
    palabras = re.findall(r"[a-z]+", info["normalizado"])
    if palabras and not info["entidades"] and all(p in RELLENO for p in palabras):
        return "ambigua", 1.0, None                                 # puro relleno («mmm, a ver, eh... pues...»)
    abstracto = entidades.abstraer(info).split()
    solo_entidades = bool(info["entidades"]) and all(p.startswith("x") and p in entidades.TOKENS.values() or p in RELLENO or p in ("de", "en", "la", "el", "los", "las", "del", "para", "solo") for p in abstracto)
    if solo_entidades and prev not in DOMINIO_REGLAS:
        return "ambigua", 1.0, None                                 # «FOODS_2_398 WI_2» sin una pregunta previa: se pide precisar
    if len(palabras) == 1 and palabras[0] in respuestas.TEMAS_UNA_PALABRA and not info["entidades"] and prev not in DOMINIO_REGLAS:
        return "ambigua", 1.0, None                                 # una palabra suelta («ventas», «inventario»): se ofrecen opciones
    if AYUDA_APP.search(info["normalizado"]) and not entidades.es_ajena(info):
        return "ayuda", 1.0, None                                   # pregunta sobre cómo usar el aplicativo
    clave = analisis.detectar(info, ctx)
    if clave:                                                       # análisis con reglas: calendario, precios, ingresos, participación... o un dato que el aplicativo no tiene
        info["clave"] = clave
        return ("dato_no_disponible" if clave == "no_disponible" else "analisis"), 1.0, None
    inicio = ACCION_INICIO.match(info["normalizado"])
    if inicio and not (inicio.group(1).startswith(("cambi", "pon")) and info["entidades"]) and not entidades.es_ajena(info):
        return "accion_no_soportada", 1.0, None                     # empieza con un verbo de acción: pide que el asistente haga algo
    if re.match(r"^no\b[ ,]*(?:yo |lo que |me )?(?:queria|quiero|me referia|digo|era|buscaba)\b", info["normalizado"]) and info["entidades"] and prev in DOMINIO_REGLAS:
        return "seguimiento", 1.0, None                             # «No, yo quería ver Texas»: corrige el dato de la pregunta anterior
    if prev == "analisis" and ctx.get("clave_analisis") and len(limpio.split()) <= 8 and (info["entidades"] or info["reset"]) \
            and re.match(r"^(?:y|e|ahora|pero|tambien|solo|incluye)\b|^en (?:todas|total|general)", limpio) and not entidades.es_ajena(info):
        info["clave"] = ctx["clave_analisis"]                       # «¿y en todas las sedes?» repite el mismo análisis con el filtro nuevo
        return "analisis", 1.0, None
    intencion, conf, opciones = decidir(clasif, texto, info, prev)
    t = info["normalizado"]
    ents = info["entidades"]
    if intencion == "confirmar" and not entidades.es_ajena(info):    # reglas de seguridad para las dudas más comunes (en vez de preguntar al usuario)
        if re.search(r"\bmodelo\b|\balgoritmo\b", t):
            return "comparar_modelos", conf, None
        if re.search(r"\bpedir\b.*\bprimero\b|\bque (?:debo|tengo que|hay que) pedir\b|\bpedidos? (?:mas )?(?:urgente|prioritari)", t):
            return "cuanto_pedir", conf, None
        if ents.get("orden") == "asc" and (prev in ("top_productos", "demanda_esperada") or FUTURO.search(t)):
            return "top_productos", conf, None
        if ents.get("agrupar") in ("mes", "dia_semana", "fecha") and not FUTURO.search(t):
            return "ventas_pasadas", conf, None
        if ents.get("horizonte") and not ents.get("pasado") and FUTURO.search(t):
            return "demanda_esperada", conf, None
    if intencion in ("confirmar", "demanda_esperada", "top_productos") and (ents.get("metrica") or ents.get("orden") or ents.get("agrupar") in ("mes", "dia_semana", "fecha") or re.search(r"\bvende\b|\bvenden\b|\bsuele\b|\bnormalmente\b|\bhabitualmente\b", t)) \
            and not FUTURO.search(t) and not entidades.es_ajena(info):
        return "ventas_pasadas", conf, None                         # «lo que menos vende en promedio» sin ninguna marca de futuro habla de ventas reales
    if intencion not in ("saludo", "ayuda", "cierre", "fuera_de_contexto") and entidades.es_ajena(info):
        return "fuera_de_contexto", conf, None                      # habla de otra empresa, lugar o tema aunque use palabras del aplicativo
    if not _palabras_dominio(info):                                 # «glosario» exige un término del aplicativo; «ambigua» solo vale para frases cortas sin contenido propio
        if intencion == "glosario" and not respuestas.terminos_glosario(info):
            intencion = "fuera_de_contexto"
        elif intencion == "ambigua" and len(info["normalizado"].split()) > 3:
            intencion = "fuera_de_contexto"
    return intencion, conf, opciones


def responder(sesion, texto, intencion_forzada=None):
    """Procesa un mensaje del usuario, guarda ambos mensajes y devuelve el payload de la respuesta."""
    from apps.chat.models import MensajeChat
    texto = texto.strip()[:600]
    ctx = dict(sesion.contexto or {})
    prev = ctx.get("ultima")
    info = entidades.extraer(texto)
    clasif = modelo.obtener()
    info["pasado_prev"] = ctx.get("pasado")                         # el periodo del turno anterior (para «¿y cómo se compara con marzo?»)
    referencia = resolver_referencias(ctx, info)

    if intencion_forzada:
        intencion, conf, opciones = intencion_forzada, 1.0, None
    else:
        intencion, conf, opciones = clasificar(clasif, texto, prev, info, ctx)
        if referencia and intencion in ("top_productos", "confirmar", "ambigua", "no_entendida", "fuera_de_contexto", "seguimiento") and (ctx.get("lista_intencion") or ctx.get("intencion")) in DOMINIO_REGLAS:
            intencion = ctx.get("lista_intencion") or ctx["intencion"]     # «¿y el siguiente?»: sigue con lo que generó la lista
            if intencion == "analisis":
                info["clave"] = ctx.get("lista_clave") or ctx.get("clave_analisis")
    es_seguimiento = intencion == "seguimiento"
    if es_seguimiento:                                              # continúa la intención anterior con otros datos
        intencion = ctx.get("intencion") or "ambigua"
    # El tiempo manda: si se habla del pasado («el último mes», «se vendió»), las preguntas de «más vendidos» o «demanda» se responden con ventas reales;
    # y si tras hablar del pasado se pide un periodo futuro, vuelve a ser una proyección.
    ents = info["entidades"]
    if not intencion_forzada:
        if intencion in ("top_productos", "demanda_esperada") and "pasado" in ents:
            intencion = "ventas_pasadas"
        elif intencion == "demanda_esperada" and re.search(r"\b(?:va|van|vaya|vayan) a (?:vender|tener|mover) mas\b|\bmas salida\b|best ?seller|mas demandad|mayor demanda", info["normalizado"]):
            intencion = "top_productos"
        elif intencion == "ventas_pasadas" and "horizonte" in ents and "pasado" not in ents and not ents.get("agrupar"):
            intencion = "top_productos" if ctx.get("intencion") == "top_productos" else "demanda_esperada"
    if not (es_seguimiento or intencion == ctx.get("intencion")):   # una pregunta de otro tema no hereda el periodo ni el nivel de servicio anteriores
        ctx = {k: v for k, v in ctx.items() if k not in ("horizonte", "nivel", "pasado")}
    if intencion == "analisis" and not info.get("clave"):            # un seguimiento de un análisis repite el mismo análisis con los datos nuevos
        info["clave"] = ctx.get("clave_analisis")
        if not info["clave"]:
            intencion = "ambigua"
    nuevo_ctx = fusionar_contexto(ctx, info) if intencion in DOMINIO_REGLAS or intencion == "confirmar" else dict(ctx)

    if intencion == "confirmar":
        payload = {"texto": "No estoy seguro de haber entendido bien. ¿Quisiste preguntar por alguna de estas opciones?",
                   "opciones": [{"texto": respuestas.NOMBRES_INTENCION[i], "intencion": i, "mensaje": texto} for i in opciones]}
    else:
        payload = respuestas.FUNCIONES.get(intencion, respuestas.no_entendida)(nuevo_ctx, info)
        nuevo_ctx.update(payload.pop("_ctx", {}))                   # la respuesta puede fijar datos de la conversación (por ejemplo, la fecha exacta de «ese día»)

    if intencion == "ventas_pasadas" and info["entidades"].get("agrupar"):
        nuevo_ctx["agrupar_ref"] = info["entidades"]["agrupar"]       # para «¿y el peor?»
    if payload.get("columnas") and payload.get("filas") and payload["columnas"][0] == "Producto" and len(payload["columnas"]) > 1 and payload["columnas"][1] == "Tienda":
        nuevo_ctx["lista"] = [[f[0], f[1]] for f in payload["filas"][:15]]       # la última lista de productos mostrada: «el segundo», «el siguiente»
        nuevo_ctx["lista_idx"] = 0
        nuevo_ctx["lista_intencion"] = intencion
        nuevo_ctx["lista_clave"] = info.get("clave")
    elif info.get("ref") is not None:
        nuevo_ctx["lista_idx"] = info["ref"]
    nuevo_ctx["ultima"] = intencion
    if intencion in DOMINIO_REGLAS:
        nuevo_ctx["intencion"] = intencion
    if intencion == "analisis":
        nuevo_ctx["clave_analisis"] = info.get("clave")
    sesion.contexto = nuevo_ctx
    if not sesion.titulo:
        sesion.titulo = texto[:60]
    sesion.save()

    fuera = intencion == "fuera_de_contexto"
    MensajeChat.objects.create(sesion=sesion, rol="usuario", texto=texto, intencion=intencion, confianza=round(float(conf), 3),
                               entidades={**info["entidades"], "contexto_previo": prev}, fuera_de_contexto=fuera)
    payload["texto"] = payload["texto"].replace(" de el ", " del ")
    extra = {k: v for k, v in payload.items() if k != "texto" and v}
    MensajeChat.objects.create(sesion=sesion, rol="asistente", texto=payload["texto"], intencion=intencion, entidades={"extra": extra}, fuera_de_contexto=fuera)
    memoria = {k: v for k, v in nuevo_ctx.items() if k in ("tienda", "categoria", "departamento", "producto", "nivel", "horizonte", "pasado")}
    return {"texto": payload["texto"], **extra, "intencion": intencion, "confianza": round(float(conf), 2), "fuera_de_contexto": fuera, "memoria": memoria}
