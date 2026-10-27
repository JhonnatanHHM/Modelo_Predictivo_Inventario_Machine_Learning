"""Extracción de entidades del texto (reglas): tienda, categoría, departamento, producto, nivel de servicio, horizonte, modelo y cantidad.
No usa la base de datos: solo reconoce el formato. La validación contra los datos reales se hace al responder."""
import re
import unicodedata
from datetime import date

NIVELES = (0.8, 0.9, 0.95)
ESTADOS_TIENDA = {"california": "CA_1", "texas": "TX_2", "wisconsin": "WI_2"}
CATEGORIAS = {"foods": "FOODS", "food": "FOODS", "alimento": "FOODS", "alimentos": "FOODS", "comida": "FOODS", "comidas": "FOODS",
              "hobbies": "HOBBIES", "hobby": "HOBBIES", "pasatiempo": "HOBBIES", "pasatiempos": "HOBBIES",
              "household": "HOUSEHOLD", "hogar": "HOUSEHOLD"}
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5}
MESES_TODOS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
NUMEROS = {"uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
TOKENS = {"tienda": "xtienda", "categoria": "xcategoria", "departamento": "xdepto", "producto": "xproducto", "nivel": "xnivel",
          "horizonte": "xhoriz", "modelo": "xmodelo", "cantidad": "xcantidad", "pasado": "xpasado"}


def normalizar(texto):
    """Minúsculas y sin tildes, conservando la longitud (para poder reemplazar tramos)."""
    salida = []
    for ch in texto.lower():
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
        salida.append(base[:1] if base else ch)
    return "".join(salida)


def _nivel(valor):
    return min(NIVELES, key=lambda n: abs(n - valor / 100)) if min(abs(n - valor / 100) for n in NIVELES) <= 0.04 else None


def extraer(texto):
    """Devuelve {'entidades': {...}, 'reset': [...], 'spans': [(inicio, fin, clave)], 'normalizado': str}."""
    t = normalizar(texto)
    usados, ents, spans, reset = [], {}, [], []

    def libre(a, b):
        return all(b <= x or a >= y for x, y in usados)

    def registrar(clave, valor, m):
        if libre(m.start(), m.end()):
            usados.append((m.start(), m.end())); spans.append((m.start(), m.end(), clave))
            ents.setdefault(clave, valor)

    for m in re.finditer(r"\b(foods|hobbies|household)[ _-]?([123])[ _-]?(\d{3})\b", t):
        registrar("producto", f"{m[1].upper()}_{m[2]}_{m[3]}", m)
    for m in re.finditer(r"\b(foods|hobbies|household)[ _-]?([123])\b", t):
        registrar("departamento", f"{m[1].upper()}_{m[2]}", m)
    for m in re.finditer(r"\b(ca|tx|wi)[ _-]?([1-4])\b", t):
        registrar("tienda", f"{m[1].upper()}_{m[2]}", m)
    for m in re.finditer(r"(?<!\bno )\b(california|texas|wisconsin)\b", t):
        registrar("tienda", ESTADOS_TIENDA[m[1]], m)
    for m in re.finditer(r"\b(foods|food|alimentos?|comidas?|hobbies|hobby|pasatiempos?|household|hogar)\b", t):
        registrar("categoria", CATEGORIAS[m[1]], m)
    # nivel de servicio
    for m in re.finditer(r"\b(\d{2})\s*(?:%|por ?ciento)", t):
        registrar("nivel", _nivel(int(m[1])), m)
    for m in re.finditer(r"nivel de servicio (?:de |del |al )?(\d{2})\b", t):
        registrar("nivel", _nivel(int(m[1])), m)
    for m in re.finditer(r"\b(noventa y cinco|noventa|ochenta)\b", t):
        registrar("nivel", {"noventa y cinco": 0.95, "noventa": 0.9, "ochenta": 0.8}[m[1]], m)
    # fechas concretas del pasado: meses ya registrados (enero a mayo), año 2016, histórico completo, lo que va del mes, quincena
    for m in re.finditer(r"\b(\d{1,2}) de (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) (?:de |del )?(201[1-6])\b", t):
        try:
            registrar("pasado", {"fecha": date(int(m[3]), MESES_TODOS[m[2]], int(m[1])).isoformat(), "etiqueta": f"el {m[1]} de {m[2]} de {m[3]}"}, m)
        except ValueError:
            pass                                                       # fecha que no existe: la trata la capa de análisis
    for m in re.finditer(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) (?:de |del )?(201[1-6])\b", t):
        registrar("pasado", {"mes_anio": [MESES_TODOS[m[1]], int(m[2])]}, m)
    meses = [MESES[m[1]] for m in re.finditer(r"\b(enero|febrero|marzo|abril|mayo)\b", t)]
    if meses:
        primero = re.search(r"\b(enero|febrero|marzo|abril|mayo)\b", t)
        registrar("pasado", {"meses": list(dict.fromkeys(meses))[:2]}, primero)
    for m in re.finditer(r"\ben lo que va del mes\b|\bmes en curso\b|\bllevamos (?:vendido|vendiendo)\b", t):
        registrar("pasado", {"mtd": True}, m)
    for m in re.finditer(r"\bquincena\b", t):
        registrar("pasado", {"n": 14}, m)
    for m in re.finditer(r"\bdesde que hay (?:registros|datos|ventas)\b|\b(?:toda|en toda) la historia\b|\ben la historia\b|\bdesde siempre\b|\bdesde el (?:inicio|principio)\b|\bhistoric\w*\b|\bhistorial\b", t):
        registrar("pasado", {"todo": True}, m)
    for m in re.finditer(r"\b(?:en |del |de |durante )?(201[1-6])\b", t):
        registrar("pasado", {"anio": int(m[1])}, m)
    for m in re.finditer(r"\b(?:ultimo ano|ano pasado|ultimos 12 meses|ultimo ano registrado)\b", t):
        registrar("pasado", {"n": 365}, m)
    for m in re.finditer(r"\b(?:ultimo trimestre(?: registrado)?|trimestre pasado|ultimos 3 meses)\b", t):
        registrar("pasado", {"n": 91}, m)
    # "qué categoría/tienda/departamento ..." pide agrupar el ranking por esa dimensión
    for m in re.finditer(r"\b(?:la |el |las |los )?(categoria|tienda|departamento|sede)s? (?:que|con|de) (?:mas|menos|mejor|peor|mayor|menor)\b", t):
        ents.setdefault("agrupar", {"sede": "tienda"}.get(m[1], m[1]))
    for m in re.finditer(r"\b(?:que|cual|cuales|en cada|por cada|por) (categoria|tienda|departamento|sede)s?\b", t):
        ents.setdefault("agrupar", {"sede": "tienda"}.get(m[1], m[1]))
    # orden ascendente («el que menos vende», «peor tienda», «menos vendido») y métrica («en promedio», «por día»)
    if re.search(r"\bmenos (?:se )?(?:vend|vent|dem|sal|mov)\w*|\bmenor(?:es)? (?:venta|demanda|rotacion)|\bpeor(?:es)? (?:producto|venta|articulo|tienda|categoria|departamento|dia|mes|sede)s?\b|\bmas bajas? ventas\b|\bel menos vendido\b|\bque menos\b|\bpeor(?:es)? (?:vend|vent)\w*\b|\b(?:vend|vent)\w* menos\b", t):
        ents["orden"] = "asc"
    if re.search(r"\bpromedio\b|\bpor dia\b|\bdiari[oa]s?\b|\bpor semana\b|\bsemanal(?:es)?\b", t):
        ents["metrica"] = "promedio"
    for m in re.finditer(r"\b(?:que|cual) dia de la semana\b|\bdia de la semana\b", t):
        ents.setdefault("agrupar", "dia_semana")
    for m in re.finditer(r"\b(?:que|cual|en que) mes\b(?! (?:pasado|anterior))|\b(?:mejor|peor) mes\b|\bmes con (?:mas|menos)\b", t):
        ents.setdefault("agrupar", "mes")
    for m in re.finditer(r"\bpico de ventas\b|\b(?:mejor|peor) dia\b|\bdia con (?:mas|menos) (?:ventas|demanda)\b|\b(?:que|cual) dia (?:se )?(?:vendio|vendi\w*|vende|fue)\b", t):
        ents.setdefault("agrupar", "fecha")
    # tiempo pasado: ventas ya registradas ("el último mes registrado", "la semana pasada", "se vendió"...). Va antes del horizonte para quedarse con "últimos 28 días".
    for m in re.finditer(r"\bultim[oa]s? (\d{1,2}) dias\b", t):
        registrar("pasado", {"n": max(int(m[1]), 1)}, m)
    for m in re.finditer(r"\bultim[oa]s? (\d) semanas\b", t):
        registrar("pasado", {"n": 7 * int(m[1])}, m)
    for m in re.finditer(r"\b(?:ultima semana|semana pasada|semana anterior)\b", t):
        registrar("pasado", {"n": 7}, m)
    for m in re.finditer(r"\b(?:ultimo mes(?: registrado)?|mes pasado|mes anterior|ultimas 4 semanas)\b", t):
        registrar("pasado", {"n": 28}, m)
    for m in re.finditer(r"\bultimo dia (?:en )?(?:que )?(?:haya |hayan |se )?(?:vendi\w*|con ventas)\b|\bultima vez que (?:se )?vendi\w*\b|\bultimo dia que (?:se )?vendi\w*\b", t):
        registrar("pasado", {"ultima_venta": True}, m)
    for m in re.finditer(r"\bayer\b|\bultimo dia(?: registrado)?\b|\bdia anterior\b", t):
        registrar("pasado", {"n": 1}, m)
    for m in re.finditer(r"\bese (?:mismo )?dia\b|\besa fecha\b", t):
        registrar("pasado", {"n": 1, "generico": True}, m)
    for m in re.finditer(r"\b(?:se vendi(?:o|eron)|vendieron|vendimos|vendi|hasta ahora|hasta hoy|ventas reales)\b", t):
        registrar("pasado", {"n": 28, "generico": True}, m)
    # horizonte
    for m in re.finditer(r"\bsemana[s]? ([1-4])\b", t):
        registrar("horizonte", {"tipo": "semana", "n": int(m[1])}, m)
    for m in re.finditer(r"\b(?:proxima|siguiente|esta|entrante) semana\b|\bsemana (?:proxima|siguiente|que viene|entrante)\b|\bla semana que viene\b", t):
        registrar("horizonte", {"tipo": "semana", "n": 1}, m)
    for m in re.finditer(r"\b(\d{1,2}) dias?\b", t):
        n = int(m[1]); registrar("horizonte", {"tipo": "28d"} if n >= 28 else {"tipo": "dias", "n": max(n, 1)}, m)
    for m in re.finditer(r"\b(\d|dos|tres|cuatro) semanas\b", t):
        n = int(m[1]) if m[1].isdigit() else NUMEROS[m[1]]
        registrar("horizonte", {"tipo": "28d"} if n >= 4 else {"tipo": "dias", "n": 7 * n}, m)
    for m in re.finditer(r"\b(mes|mensual|cuatro semanas)\b|\bjunio\b|\b(?:hasta|al) (?:el )?19(?:/06| de junio)\b", t):
        registrar("horizonte", {"tipo": "28d"}, m)
    # modelo y cantidad
    for m in re.finditer(r"\b(tft|transformer)\b", t):
        registrar("modelo", "tft", m)
    for m in re.finditer(r"\b(lightgbm|lgbm|light gbm)\b", t):
        registrar("modelo", "lightgbm", m)
    for m in re.finditer(r"\b(ets|naive)\b", t):
        registrar("modelo", m[1], m)
    for m in re.finditer(r"\b(?:el|la|cual (?:es|fue|sera) el|que) (?:producto|articulo|referencia|item)(?: [a-z_0-9 ]{0,30})? (?:que mas|con mas|mas)\b", t):
        registrar("cantidad", 1, m)                                  # "el producto que más..." pide uno solo
    # «¿qué producto...?»: el producto es lo que se busca (no el que se mencionó antes)
    for m in re.finditer(r"\b(?:que|cual|cuales) (?:fue |es |sera |seran |fueron |son )?(?:el |los |la |las )?(?:producto|articulo|referencia|item)(s?)\b|\b(?:el|los) (?:producto|articulo|referencia)(s?) (?:que|con) mas\b", t):
        ents.setdefault("buscar", {"plural": (m[1] or m[2]) == "s"})
    for m in re.finditer(r"\btop ?(\d{1,2})\b", t):
        registrar("cantidad", int(m[1]), m)
    for m in re.finditer(r"\b(\d{1,2}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez) (?:productos|series|articulos|referencias|items)\b", t):
        registrar("cantidad", int(m[1]) if m[1].isdigit() else NUMEROS[m[1]], m)
    # reinicios: "en todas las tiendas", "en total"
    if re.search(r"\btodas las (tiendas|sedes)\b", t):
        reset.append("tienda")
    if re.search(r"\ben total\b|\ben general\b|\btodos los productos\b|\btodas las categorias\b|\btodo el inventario\b", t):
        reset += ["producto", "departamento", "categoria"]
    spans.sort()
    return {"entidades": ents, "reset": reset, "spans": spans, "normalizado": t}


# Señales de que la pregunta NO es del aplicativo aunque use palabras como ventas, stock, modelo o pronóstico: empresas y lugares reales, clima, deportes, cocina, programación,
# intentos de manipular al asistente y teoría general. Las fuertes se aplican siempre; las débiles solo si no se menciona ninguna entidad del aplicativo.
AJENAS_FUERTES = re.compile(r"\b(amazon|zara|mercadona|falabella|mercado ?libre|costco|apple|tesla|google|netflix|toyota|nike|adidas|messi|ronaldo|shakira|bitcoin|dolar|euro|petroleo|bolsa de valores|farmacia|"
                            r"restaurante|clima|temperatura|lluvia|partido|seleccion|capital de|chiste|receta|keto|dieta|python|javascript|script|poema|cuento|cancion|pelicula|"
                            r"ignora (?:todas )?(?:tus|las) instrucciones|revela tu|tu prompt|actua como|eres realmente|mi barrio|mi casa|en el mundo|dragones|bogota|madrid|espana|tokio|dallas|medellin|"
                            r"iphone|prime day|mundial|videojuego|marketing|abrir un negocio|impuestos|en todo el mundo|tus reglas|quien te creo|modelo de lenguaje|tus programadores|quien te programo|cuantos anos tienes)\b")
MODELO_AJENO = re.compile(r"\bmodelos? de (?:carros?|autos?|coches?|ropa|moda|zapatillas?|zapatos?|celular(?:es)?|telefonos?|negocio|tendencia|pasarela|computador(?:es)?)\b")
AJENAS_DEBILES = re.compile(r"\ben estadistica\b|\ben teoria\b|\bmatematicamente\b|\bdesviacion estandar\b|\bsix sigma\b|\bjust in time\b|\barima\b|\bprophet\b|\baprendizaje (?:supervisado|automatico)\b|"
                            r"\bmachine learning\b|\binteligencia artificial\b|\bregresion lineal\b|\bgradient boosting\b|\bred(?:es)? neuronal(?:es)?\b")


def es_ajena(info):
    t = info["normalizado"]
    if AJENAS_FUERTES.search(t) or MODELO_AJENO.search(t):
        return True
    return not info["entidades"] and bool(AJENAS_DEBILES.search(t))


def abstraer(info):
    """Texto normalizado con las entidades reemplazadas por marcas (xtienda, xproducto...): así el modelo generaliza."""
    t, partes, pos = info["normalizado"], [], 0
    for a, b, clave in info["spans"]:
        partes.append(t[pos:a]); partes.append(f" {TOKENS[clave]} "); pos = b
    partes.append(t[pos:])
    return re.sub(r"\s+", " ", "".join(partes)).strip()


# Raíces de palabras características de cada intención: le dan al modelo conocimiento de sinónimos que no vio en el entrenamiento
LEXICOS = {
    "riesgo_quiebre": r"agot|acab|falt|quiebr|desabast|terminar|poca[s]? existencia|corto de|sin stock|no alcanz|se me van",
    "sobreinventario": r"sobr|exceso|excedent|acumul|estanc|demasiad|sin salida|parad[ao]|de mas|sobreabast|no rota",
    "cuanto_pedir": r"\bped(ir|ido)|repon|reposici|reabastec|compr|ordenar|surt|encarg|aprovision|proveedor",
    "demanda_esperada": r"vend|venta|demanda|proyecci|pronostic|prediccion|despach|salida",
    "rango_proyeccion": r"rango|escenario|optimista|pesimista|incertidumbre|intervalo|maximo|minimo|percentil|banda|oscil|desviad|techo",
    "top_productos": r"mas vendid|\btop\b|ranking|principales|lider|mejores productos|mas demand|mayor demanda|mayor proyeccion|que mas|mas se mueven|rotan",
    "comparar_modelos": r"modelo|algoritmo|\btft\b|lightgbm|\bets\b|naive|mase|precis|error|exactitud|confiable|mejores metricas",
    "estado_modelo": r"ultim[ao] (prediccion|corrida|calculo|entren|vez)|actualiz|refresc|vigente|entreno|fecha|hasta que dia|en uso|activo",
    "inventario_actual": r"inventario|stock|existencia|guardad|piezas|bodega|almacen|mercancia|tengo|disponible",
    "glosario": r"significa|que es\b|define|definicion|\bdef\b|a que le dicen|concepto|explica|para que sirve|se entiende|interpret|a que te refieres|a que le llaman|que quiere decir",
    "catalogo": r"sede|sucursal|tiendas? (hay|existe|disponible)|cuantas tiendas|cuantos productos|cuantas series|cuantos departamentos|que categorias|que departamentos|lista de|hay datos de|que info|que datos|desde cuando|abarca|catalogo|periodo de tiempo|cobertura de los datos|que fechas",
    "accion_no_soportada": r"registra|actualiza|lanza|ejecuta|exporta|descarga|borra|elimina|envia|crea\b|modifica|programa|sube|agrega|anade|imprime|guarda|genera la|re-?entrena|\bentrena\b|\bcambia\b|\bpon\b|activa|desactiva|configura|reinicia",
    "saludo": r"^(hola|holi|buenas|buenos dias|buen dia|que onda|q onda|que mas|hey|saludos|muy buenas|buenas tardes|buenas noches)",
    "ayuda": r"\bayuda\b|\bhelp\b|guia|no se que preguntar|que puedo consultar|como (usar|uso|funciona)|que puedes hacer|para que sirves|instrucciones",
    "cierre": r"\bbye\b|\bchao\b|\bthx\b|gracias|nos vemos|hasta luego|adios|hasta pronto|eso es todo|listo, ",
    "ventas_pasadas": r"vendi|vendid|ventas reales|historic|ultimo mes|mes pasado|semana pasada|ayer|se vendio|hasta ahora|hasta hoy|fueron|quincena|\babril\b|\bmarzo\b|febrero|enero|2016|llevamos|va del mes|promedio diario|hace (dos|tres|\d+)",
}
_LEXICOS = {k: re.compile(v) for k, v in LEXICOS.items()}


def banderas(info):
    e = info["entidades"]
    t = info["normalizado"]
    n_palabras = len(t.split())
    base = [float(k in e) for k in ("tienda", "categoria", "departamento", "producto", "nivel", "horizonte", "modelo", "cantidad", "pasado")] + \
           [float(bool(e)), float(n_palabras <= 4), float(n_palabras <= 2)]
    return base + [float(bool(rx.search(t))) for rx in _LEXICOS.values()]
