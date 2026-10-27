"""Datos de entrenamiento del clasificador de intenciones (frases generadas con plantillas) y frases de PRUEBA escritas aparte.
Cada ejemplo es (texto, intención_anterior, intención). La intención anterior es el contexto de la conversación."""
import random

INTENCIONES_DOMINIO = ["catalogo", "ventas_pasadas", "demanda_esperada", "rango_proyeccion", "cuanto_pedir", "riesgo_quiebre", "sobreinventario", "top_productos",
                       "comparar_modelos", "estado_modelo", "inventario_actual", "glosario"]
INTENCIONES = INTENCIONES_DOMINIO + ["saludo", "ayuda", "cierre", "seguimiento", "ambigua", "accion_no_soportada", "fuera_de_contexto"]
# Intenciones que pueden continuarse con una frase corta ("¿cuánto?", "¿cuáles?")
CONTINUABLES = ["ventas_pasadas", "demanda_esperada", "rango_proyeccion", "cuanto_pedir", "riesgo_quiebre", "sobreinventario", "top_productos", "inventario_actual", "comparar_modelos"]

TIENDAS = ["CA_1", "TX_2", "WI_2", "la tienda CA_1", "la tienda de Texas", "Wisconsin", "California", "la sede de Texas", "tienda WI_2", "la tienda de California"]
CATEGORIAS = ["FOODS", "HOBBIES", "HOUSEHOLD", "alimentos", "comida", "hogar", "pasatiempos", "la categoría FOODS", "la categoría de hogar", "los artículos del hogar"]
DEPTOS = ["FOODS_1", "FOODS_3", "HOBBIES_2", "HOUSEHOLD_1", "el departamento FOODS_2", "HOBBIES_1", "HOUSEHOLD_2"]
HORIZONTES = ["", "", " en los próximos 28 días", " para la próxima semana", " este mes", " en las próximas dos semanas", " para la semana 2", " en 14 días", " durante la semana 3", " en 7 días"]
PASADOS = ["", " el último mes", " el mes pasado", " la semana pasada", " en los últimos 7 días", " el último mes registrado", " en los últimos 28 días", " ayer", " hasta ahora", " en los últimos 14 días"]
NIVELES = ["", "", "", " con 90 % de servicio", " al 95 %", " con un nivel de servicio del 80 %", " con nivel de servicio de 95 %"]


def _producto(r):
    return f"{r.choice(['FOODS', 'HOBBIES', 'HOUSEHOLD'])}_{r.randint(1, 3)}_{r.randint(1, 600):03d}"


def _alcance(r, sin=0.25):
    """Fragmento que indica de qué se habla: producto, tienda, categoría... (o nada)."""
    if r.random() < sin:
        return ""
    prep = r.choice(["de", "para", "en", "sobre", "de"])
    tipo = r.choice(["tienda", "categoria", "depto", "producto", "producto", "tienda+categoria", "producto+tienda"])
    t, c, d, p = r.choice(TIENDAS), r.choice(CATEGORIAS), r.choice(DEPTOS), _producto(r)
    return {"tienda": f" {prep} {t}", "categoria": f" {prep} {c}", "depto": f" {prep} {d}", "producto": f" {prep} {p}",
            "tienda+categoria": f" {prep} {c} en {t}", "producto+tienda": f" de {p} en {t}"}[tipo]


PLANTILLAS = {
    "catalogo": ["cuáles son nuestras sedes", "qué tiendas hay", "cuántas tiendas tengo", "qué categorías manejo", "cuántos productos hay{a}", "cuántas series hay{a}", "qué departamentos hay{a}",
                 "qué productos hay{a}", "de qué fechas son los datos", "desde cuándo hay ventas registradas", "lista de tiendas", "qué sedes están en el sistema", "qué estados cubre el aplicativo",
                 "cuántos productos tiene{a}", "qué abarca este aplicativo", "con qué tiendas trabajamos", "cuántas referencias manejamos{a}", "qué datos tienes cargados", "cuántos días de historia hay",
                 "en qué ciudades tenemos tiendas", "qué sucursales existen", "cuántas categorías de productos hay", "muéstrame las tiendas disponibles", "hasta qué fecha llegan las ventas"],
    "ventas_pasadas": ["cuánto se vendió{a}{p}", "qué productos vendieron más{a}{p}", "ventas del último mes{a}", "historial de ventas{a}", "cuáles fueron los más vendidos{a}{p}",
                       "cuántas unidades vendimos{a}{p}", "dime las ventas reales{a}{p}", "ventas registradas{a}{p}", "qué se vendió más{a}{p}", "cómo nos fue en ventas{a}{p}",
                       "total vendido{a}{p}", "los productos con más ventas{a}{p}", "qué tanto vendimos{a}{p}", "ventas de la semana pasada{a}", "quiero ver lo que se vendió{a}{p}",
                       "cuáles son los productos más vendidos{a}{p}", "top {k} de lo que más se vendió{a}{p}", "qué productos tuvieron más ventas{a}{p}", "cuánto vendí{a}{p}",
                       "dame las ventas pasadas{a}{p}", "cuántas ventas hubo{a}{p}", "qué fue lo que más se vendió{a}{p}",
                       "cuál fue el producto que más vendió ese día", "qué producto vendió más ese día y en qué tienda", "cuánto vendió este producto el último día que haya vendido algo",
                       "en qué sede se vendió más ese día", "cuál es el producto que menos vende en promedio{a}", "qué producto vende menos{a}", "cuál es la tienda con peores ventas", "qué día de la semana se vende más{a}",
                       "qué mes se vende más{a}", "cuál fue el mejor día de ventas{a}", "promedio de ventas por día{a}", "qué categoría vende menos{a}", "cuántas unidades vende en promedio al día{a}",
                       "cuál es el producto que más vende en promedio{a}", "qué departamento vendió menos{p}", "cuál fue el peor día de ventas{a}", "quiero saber qué producto vendió más ese día", "cuál fue el artículo más vendido ese día", "y qué producto fue el que más vendió{p}"],
    "demanda_esperada": ["¿cuánto se va a vender{a}{h}?", "cuál es la demanda esperada{a}{h}", "dame la proyección de ventas{a}{h}", "cuántas unidades se venderán{a}{h}",
                         "pronóstico de demanda{a}{h}", "qué demanda se espera{a}{h}", "muéstrame las ventas proyectadas{a}{h}", "cuánto esperamos vender{a}{h}",
                         "proyección{a}{h}", "cuánta demanda habrá{a}{h}", "qué tanto se va a vender{a}{h}", "estima las ventas{a}{h}", "demanda esperada{a}{h}",
                         "cuántas unidades se espera vender{a}{h}", "predicción de ventas{a}{h}", "cómo va a estar la demanda{a}{h}", "ventas esperadas{a}{h}",
                         "las ventas que vamos a tener{a}{h}", "cuántas ventas tendremos{a}{h}", "qué ventas se prevén{a}{h}", "ventas futuras{a}{h}", "cuánto saldrá{a}{h}",
                         "quiero conocer el volumen de ventas{a}{h}"],
    "rango_proyeccion": ["cuál es el mejor y peor escenario{a}{h}", "dame el rango de la proyección{a}{h}", "entre qué valores puede estar la demanda{a}{h}",
                         "qué tan incierta es la predicción{a}", "cuál es el escenario alto de la demanda{a}{h}", "dame el intervalo de la predicción{a}",
                         "cuánto como máximo podría venderse{a}{h}", "qué pasa si la demanda sale más alta de lo esperado{a}", "cuál es el percentil 90 de la demanda{a}{h}",
                         "rango entre p10 y p90{a}", "cuál es el margen de error de la proyección{a}", "escenario pesimista y optimista{a}{h}", "qué tan seguro es el pronóstico{a}",
                         "dame los cuantiles de la demanda{a}{h}", "hasta cuánto podría subir la demanda{a}{h}"],
    "cuanto_pedir": ["cuánto debo pedir{a}{n}", "cuánto stock necesito{a}{h}{n}", "qué cantidad debo reponer{a}{n}", "sugerencia de pedido{a}{h}{n}", "cuántas unidades tengo que comprar{a}{n}",
                     "cuánto pido de reposición{a}{n}", "necesito reponer inventario{a}", "cuál es el stock objetivo{a}{n}", "qué pedido recomiendas{a}{n}", "cuánto compro{a}{h}{n}",
                     "calcula la reposición{a}{n}", "cuánto debería ordenar{a}{h}{n}", "pedido sugerido{a}{h}{n}", "qué cantidad pedir al proveedor{a}{n}", "cuánto necesito reabastecer{a}{h}{n}"],
    "riesgo_quiebre": ["qué productos están en riesgo de quedarse sin stock{a}", "cuáles pueden agotarse{a}", "muéstrame los productos con riesgo de quiebre{a}", "dónde podría haber desabastecimiento{a}",
                       "qué referencias tienen poco inventario{a}", "alertas de quiebre de stock{a}", "qué se me va a acabar{a}", "productos con faltante{a}", "cuántos productos están en riesgo{a}",
                       "qué artículos corren riesgo de agotarse{a}", "hay riesgo de quedarnos sin inventario{a}", "productos que me pueden faltar{a}"],
    "sobreinventario": ["qué productos tienen exceso de inventario{a}", "dónde tengo sobreinventario{a}", "qué tengo de más en bodega{a}", "productos con sobrestock{a}", "cuáles tienen demasiado stock{a}",
                        "muéstrame el sobrante{a}", "qué referencias están sobreabastecidas{a}", "tengo mucho inventario de algo{a}", "qué artículos tienen inventario excesivo{a}", "cuántos productos tienen exceso{a}",
                        "productos acumulados que no rotan{a}", "mercancía estancada{a}", "qué no se va a vender{a}", "stock de más{a}", "artículos sin rotación{a}",
                        "tengo demasiado de algunos productos{a}"],
    "top_productos": ["cuáles serán los productos más vendidos{a}{h}", "top {k} productos con mayor demanda esperada{a}", "qué productos van a vender más{a}", "ranking de demanda{a}", "los {k} productos principales{a}",
                      "cuáles son las series con más demanda esperada{a}", "qué artículos se venderán más{a}{h}", "producto estrella{a}", "dame los {k} productos con más ventas{a}{h}", "lista de los productos que más rotan{a}"],
    "comparar_modelos": ["cuál modelo es mejor", "compara los modelos", "qué tan preciso es el tft", "cuál es el mejor algoritmo", "qué modelo tiene menor error", "diferencia entre lightgbm y el tft",
                         "muéstrame las métricas de los modelos", "qué exactitud tiene el modelo", "ranking de modelos por mase", "cuál predice mejor", "el tft supera a lightgbm", "qué tan bueno es lightgbm",
                         "resultados de la comparación de modelos", "cuál es el error del modelo", "qué modelo usan las predicciones"],
    "estado_modelo": ["cuándo se actualizaron las predicciones", "qué modelo está activo", "cuándo se entrenó el modelo", "estado de las predicciones", "hasta qué fecha llega el pronóstico",
                      "cuál fue la última corrida", "terminó el entrenamiento", "de qué fecha son los datos", "las predicciones están al día", "cuándo fue la última vez que se generaron predicciones",
                      "ya se entrenó el tft", "qué tan reciente es la proyección"],
    "inventario_actual": ["cuánto inventario tengo{a}", "cuál es el inventario actual{a}", "cuántas unidades hay en stock{a}", "qué inventario hay registrado{a}", "existencias{a}", "cuánto stock hay{a}",
                          "cuántas unidades me quedan{a}", "dime el inventario disponible{a}", "qué existencias tengo{a}"],
    "glosario": ["qué significa p90", "qué es el nivel de servicio", "qué es el stock objetivo", "explícame el mase", "qué es un quiebre de stock", "qué quiere decir cobertura", "para qué sirve el cuantil",
                 "qué es sobreinventario", "cómo se calcula el pedido sugerido", "qué es la mediana de demanda", "define pronóstico probabilístico", "qué es el tft", "qué es p10", "qué significa p50",
                 "qué es el rango p10 p90", "cómo interpreto la proyección", "qué es lightgbm", "qué mide el mase", "cuál es la diferencia entre p50 y p90"],
    "accion_no_soportada": ["registra {k} unidades de inventario{a}", "actualiza el inventario{a} a {k} unidades", "lanza el entrenamiento del tft", "ejecuta generar predicciones", "exporta las proyecciones a excel",
                            "descarga el reporte de reposición", "borra todos mis datos", "cambia mi contraseña", "envía el pedido al proveedor{a}", "crea un nuevo usuario", "modifica el nivel de servicio por defecto",
                            "programa un correo con el pedido{a}", "guarda este inventario{a}", "sube un archivo de ventas", "imprime la lista de pedidos{a}", "agrega un producto nuevo", "elimina el producto{a}",
                            "haz el pedido de {k} unidades{a}", "reentrena el modelo ahora", "genera un pdf con las proyecciones"],
    "saludo": ["hola", "buenos días", "buenas", "hey", "qué tal", "buenas tardes", "saludos", "hola, ¿cómo estás?", "buenas noches", "hola de nuevo", "hola buen día"],
    "ayuda": ["ayuda", "qué puedes hacer", "para qué sirves", "qué preguntas puedo hacerte", "cómo funciona este chat", "quién eres", "qué sabes hacer", "necesito ayuda", "cómo te uso",
              "cuáles son tus funciones", "en qué me puedes ayudar", "qué temas manejas", "explícame cómo usar el asistente",
              "para qué sirve esta herramienta", "qué hace esta aplicación", "cómo se usa este asistente", "qué puedo consultar aquí", "para qué es este chat", "instrucciones de uso"],
    "cierre": ["gracias", "muchas gracias", "perfecto, gracias", "listo, gracias", "ok gracias", "genial", "excelente", "vale gracias", "chao", "hasta luego", "adiós", "eso es todo", "mil gracias", "nos vemos",
              "gracias por la ayuda", "te lo agradezco", "muy amable", "gracias, eso era todo", "hasta pronto", "nos hablamos", "agradezco la información", "ya me quedó claro, gracias",
              "eso es todo, gracias"],
}

SEGUIMIENTO = ["¿y en {t}?", "y para {c}", "¿y {p}?", "¿y con {n}?", "¿y la semana 2?", "¿y con el TFT?", "¿y de {d}?", "qué tal en {t}", "ahora en {t}", "lo mismo para {c}", "¿y en total?",
               "pero solo {t}", "y {c} en {t}", "ahora la semana siguiente", "con 95 % mejor", "y si lo quiero al {n}", "¿y para {d}?", "ahora con lightgbm", "y en {t}, ¿cómo va?", "¿y {c}?",
               "cámbialo a {t}", "mejor para {p}", "¿y para los próximos 14 días?", "¿y si es {t}?", "ahora para {c} en {t}", "¿y en todas las tiendas?",
               "ahora para {t}", "y de {c}?", "y si lo hago con {n}", "pero en {t}", "y en el caso de {p}", "qué pasa con {c}", "y para {t}, ¿cuánto sería?", "entonces para {d}", "y si cambio a {c}"]

AMBIGUAS = ["¿cuánto?", "¿cuántas unidades?", "dame el detalle", "muéstramelo", "¿y cuánto sería eso?", "¿cuál es el valor?", "ver más", "dame más información", "¿puedes mostrarme la lista?",
            "¿cuáles?", "¿cuántos son?", "¿y eso?", "cuéntame más", "¿en cuánto?", "¿de cuántas?", "dime los números", "¿cuál es el total?", "continúa", "dámelo", "¿y cuál es el resultado?"]

FUERA = [
    "cuál es la capital de Francia", "cuéntame un chiste", "cómo preparo una pizza", "quién ganó el mundial", "qué clima hará mañana", "recomiéndame una película", "cuánto es 25 por 4",
    "escribe un poema sobre el mar", "cómo se programa en python", "quién es el presidente de Colombia", "traduce hola al inglés", "dame una receta de arroz con pollo", "cuál es el sentido de la vida",
    "qué hora es en Tokio", "cómo bajo de peso", "qué es la fotosíntesis", "explícame la teoría de la relatividad", "cuánto cuesta un vuelo a Madrid", "cuál es el mejor celular del año",
    "cómo está el dólar hoy", "cuál es el precio del bitcoin", "quién fue Simón Bolívar", "cómo cuido a mi perro", "dame consejos para dormir mejor", "qué canción me recomiendas",
    "el pronóstico del tiempo para el fin de semana", "predicción del partido de esta noche", "quién va a ganar las elecciones", "cuál es la mejor universidad", "cómo se escribe un currículum",
    "ayúdame con mi tarea de matemáticas", "resuelve esta ecuación", "cuántos habitantes tiene China", "qué debo comer para el desayuno", "cuál es el animal más rápido",
    "cuéntame una historia", "juguemos algo", "qué opinas de la inteligencia artificial", "cómo hackear una cuenta", "dime un dato curioso", "cuál es tu color favorito", "tienes novia",
    "cómo se llama el director de Titanic", "cuál es la montaña más alta", "dónde queda la torre Eiffel", "cómo arreglo mi computador", "instala un programa por mí", "cuál es la raíz cuadrada de 144",
    "escribe un correo para mi jefe", "qué pedir en un restaurante", "inventario de la película de terror", "cuánto cuesta un taxi", "cómo gano dinero rápido", "ventas de autos usados en mi ciudad",
    "demanda de empleo en tecnología", "qué significa soñar con agua", "recomiéndame un libro", "cómo aprendo inglés", "cuál es la mejor dieta", "cómo se juega ajedrez", "qué pasó en la segunda guerra mundial",
    "quién inventó el teléfono", "cuál es la fórmula del agua", "cómo hago una página web", "cuántos años tiene la luna", "dime algo gracioso", "háblame de política", "quién es Messi",
    "pronóstico de lluvia en Bogotá", "cuánto vale un apartamento en Medellín", "cómo declaro renta", "qué es el amor", "tu opinión sobre el fútbol", "me siento triste", "cuál es la mejor serie",
    "explícame qué es una hipoteca", "cuál es el horario del metro", "dime las noticias de hoy", "genera una imagen de un gato", "cómo se dice gracias en francés", "qué estudia un ingeniero civil",
    "mejor lugar para vacaciones", "cuéntame del universo", "cómo funciona un motor", "qué tan lejos está Marte", "cuál es el idioma más hablado", "recomienda un gimnasio", "cómo se hace un pastel",
    "quién escribió Cien años de soledad", "cómo está el tráfico", "dime la fecha de hoy", "cuántos días tiene febrero", "puedes cantar", "contraseña de wifi", "abre mi correo", "envía un mensaje a Juan",
    "cuánto vale el dólar", "precio de la gasolina", "cuánto cuesta una casa", "cuánto vale un iPhone", "a cuánto está el petróleo", "cuánto cuesta el pan", "tasa de cambio del peso",
    "dime el resultado del partido", "quién ganó el clásico", "cómo está la bolsa de valores", "qué ropa me pongo hoy", "cómo cocino pasta", "dónde queda el hospital más cercano",
    "cómo se llama tu creador", "cuántos años tienes", "cuál es el mejor restaurante", "ponme música", "cómo me relajo", "cuál es la mejor marca de carros", "cuándo es el próximo feriado",
]


# Combinaciones de inicio + núcleo con sinónimos del dominio (amplían el vocabulario más allá de las plantillas)
COMBOS = {
    "demanda_esperada": (["cuánto", "qué cantidad", "cuántas unidades", "qué volumen", "dime cuánto", "necesito saber cuánto", "quiero saber qué cantidad", "me interesa conocer cuánto"],
                         ["vamos a vender", "se va a vender", "venderemos", "se venderá", "saldrá", "se despachará", "se espera que se venda", "podemos esperar de ventas", "habrá de demanda",
                          "van a comprar los clientes", "se moverá en ventas", "esperamos colocar"]),
    "rango_proyeccion": (["cuál es", "dame", "muéstrame", "quiero ver", "necesito", "calcula"],
                         ["el mejor y el peor caso de la demanda", "el escenario optimista de las ventas", "el escenario pesimista", "el margen de incertidumbre del pronóstico", "el rango probable de ventas",
                          "la banda de confianza de la proyección", "el máximo que podría venderse", "el intervalo entre el caso bajo y el alto", "la variabilidad de la predicción",
                          "qué tan lejos puede quedar la demanda real", "el techo de la demanda esperada"]),
    "cuanto_pedir": (["cuánto", "qué cantidad", "qué volumen", "cuántas unidades", "dime cuánto", "necesito saber cuánto"],
                     ["debo pedir", "tengo que reabastecer", "debo reponer", "hay que ordenar", "conviene comprar", "me recomiendas surtir", "tengo que pedirle al proveedor", "falta pedir",
                      "debería reaprovisionar", "necesito para cubrir la demanda", "hay que mandar a pedir"]),
    "riesgo_quiebre": (["qué productos", "cuáles referencias", "dónde", "qué artículos", "qué cosas", "hay algo que"],
                       ["están en riesgo de agotarse", "se pueden acabar pronto", "me van a faltar", "están por agotarse", "tienen pocas existencias", "estoy corto de existencias",
                        "se están acabando", "podrían quedarse sin stock", "tienen inventario bajo", "no me alcanzan para la demanda", "tienen riesgo de desabastecimiento", "se me van a terminar"]),
    "sobreinventario": (["qué productos", "cuáles referencias", "dónde", "qué artículos", "qué cosas", "hay algo que"],
                        ["tengo de sobra", "se me está quedando sin salida", "están acumulados en bodega", "tienen demasiadas unidades guardadas", "no se van a vender a tiempo",
                         "tienen inventario excedente", "están sobreabastecidos", "me sobran", "tienen exceso de existencias", "están estancados en almacén", "tienen más stock del necesario", "no rotan"]),
    "inventario_actual": (["cuántas unidades", "cuánto stock", "cuánta mercancía", "cuánto inventario", "qué existencias", "a cuánto asciende el stock"],
                          ["tengo guardadas", "hay hoy", "hay en bodega", "tenemos disponibles", "quedan", "hay registradas", "tengo en existencia", "hay disponibles ahora", "hay en el almacén"]),
    "ventas_pasadas": (["cuánto", "qué productos", "cuáles fueron los productos que", "dime cuánto", "quiero saber qué"],
                       ["se vendió", "vendimos", "vendieron más", "se vendió más", "tuvieron más ventas", "vendí", "se movió en ventas", "salió más"]),
    "top_productos": (["cuáles son", "dime", "muéstrame", "lista de", "quiero ver"],
                      ["los productos que más voy a vender", "los artículos con mayor proyección", "las referencias que más se mueven", "los {k} productos con más demanda", "los más demandados",
                       "los que más rotan", "los mejores productos", "lo que más se va a vender"]),
    "estado_modelo": (["", "dime", "necesito saber"],
                      ["cuál es el modelo que se está usando", "con qué datos se generó la última predicción", "qué versión del modelo está activa", "en qué fecha se hizo el último pronóstico",
                       "con qué información se entrenó", "cuándo fue el último cálculo", "si las proyecciones son recientes", "qué corrida está vigente", "el modelo que está en producción"]),
    "glosario": (["qué se entiende por", "explica qué es", "a qué te refieres con", "qué significa", "define", "para qué sirve", "cómo se interpreta"],
                 ["el quiebre", "la cobertura del intervalo", "el nivel de servicio", "el stock objetivo", "el pedido sugerido", "p90", "la mediana", "el mase", "el pinball", "un cuantil",
                  "el rango p10 p90", "el sobreinventario", "el tft", "lightgbm", "ets", "naive", "la demanda esperada"]),
    "accion_no_soportada": (["por favor", "necesito que", "quiero que", "puedes", "", "ayúdame a"],
                            ["registres el inventario de FOODS_2_398", "lances el entrenamiento", "exportes las ventas", "descargues los datos", "borres la conversación", "cambies la configuración",
                             "mandes el pedido", "actualices el stock", "ejecutes las predicciones", "guardes los cambios", "envíes un correo"]),
    "catalogo": (["cuáles son", "qué", "dime", "cuántas", "lista de"],
                 ["nuestras sedes", "las tiendas disponibles", "las categorías que manejo", "los departamentos", "las sucursales", "las tiendas que hay en el sistema", "los productos que existen"]),
    "ambigua": ([""], ["y entonces qué", "mmm", "no entiendo", "ah ok y luego", "y qué más", "no sé", "bueno y", "entonces", "ya veo, sigue",
                       "ajá", "uhm", "sí", "no", "ya", "ah ya", "okey", "vale", "entiendo", "y ahora qué", "bueno"]),
}


FUERA_PLANTILLAS = ["cuánto mide {x}", "cuánto pesa {x}", "cuál es el {s} más {a} del mundo", "qué significa la palabra {w}", "quién fue {p}", "dónde queda {l}",
                    "cuántos años tiene {x}", "cómo se dice {w} en inglés", "cuál es la capital de {l}", "qué es {c}", "cómo funciona {c}", "por qué {f}", "háblame de {c}",
                    "cuánto cuesta viajar a {l}", "cuéntame algo sobre {c}", "cuál es la historia de {l}", "explícame {c}"]
FUERA_RELLENOS = {"x": ["la torre Eiffel", "el monte Everest", "un elefante", "la luna", "un avión", "el sol", "una ballena", "el Amazonas"],
                  "s": ["río", "edificio", "animal", "país", "lago", "océano"], "a": ["largo", "alto", "grande", "rápido", "antiguo", "profundo"],
                  "w": ["efímero", "paradoja", "ubicuo", "sinónimo", "metáfora", "ajedrez", "melancolía"], "p": ["Napoleón", "Einstein", "Leonardo da Vinci", "Cleopatra", "Gandhi"],
                  "l": ["Perú", "Egipto", "Tokio", "Australia", "Argentina", "la Antártida"], "c": ["un agujero negro", "la democracia", "el arte moderno", "la música clásica", "un volcán", "la gravedad", "internet", "los dinosaurios"],
                  "f": ["el cielo es azul", "llueve", "se mueven los planetas", "hay terremotos", "los gatos ronronean"]}


def _alt(r, lista):
    return r.choice(lista)


def frases_agentes(excluir=None):
    """Frases escritas por agentes que simulan usuarios (ver frases_agentes.json). `excluir`: conjunto de (texto, previa) que se dejan fuera (validación cruzada)."""
    import json
    import os
    ruta = os.path.join(os.path.dirname(__file__), "frases_agentes.json")
    if not os.path.exists(ruta):
        return []
    filas = [(d["texto"], d.get("prev"), d["intencion"]) for d in json.load(open(ruta, encoding="utf-8"))]
    return [f for f in filas if not excluir or (f[0], f[1]) not in excluir]


def generar(semilla=42, por_plantilla=7, con_agentes=True, excluir=None):
    r = random.Random(semilla)
    filas = []
    prevs = CONTINUABLES + [None] * 4 + ["saludo", "ayuda", "glosario", "estado_modelo", "fuera_de_contexto"]
    for intencion, (inicios, nucleos) in COMBOS.items():
        for o in inicios:
            for c in nucleos:
                if r.random() < 0.7:
                    conalcance = intencion not in ("glosario", "estado_modelo", "ambigua")
                    texto = f"{o} {c}".strip().format(k=r.choice([3, 5, 10]))
                    if conalcance:
                        texto += _alcance(r, sin=0.3) + (_alt(r, HORIZONTES) if intencion in ("demanda_esperada", "rango_proyeccion", "cuanto_pedir", "top_productos") else (_alt(r, PASADOS) if intencion == "ventas_pasadas" else ""))
                    prev = r.choice(prevs) if intencion != "ambigua" else r.choice([None, "saludo", "ayuda", "glosario", "estado_modelo", "cierre"])
                    filas.append((_ruido(r, texto), prev, intencion))
    for intencion, plantillas in PLANTILLAS.items():
        for p in plantillas:
            for _ in range(por_plantilla):
                texto = p.format(a=_alcance(r), h=_alt(r, HORIZONTES), n=_alt(r, NIVELES), p=_alt(r, PASADOS), k=r.choice([3, 5, 10, "cinco", 8]))
                filas.append((_ruido(r, texto), r.choice(prevs), intencion))
    for p in SEGUIMIENTO:
        for _ in range(9):
            texto = p.format(t=_alt(r, TIENDAS), c=_alt(r, CATEGORIAS), p=_producto(r), d=_alt(r, DEPTOS), n=_alt(r, ["90 %", "95 %", "80 %", "nivel de servicio del 95 %"]))
            filas.append((_ruido(r, texto), r.choice(CONTINUABLES + [None]), "seguimiento"))
    for texto in AMBIGUAS:                                         # el contexto decide la intención
        for prev in CONTINUABLES:
            for _ in range(3):
                filas.append((_ruido(r, texto), prev, prev))
        for prev in (None, "saludo", "ayuda", "glosario", "estado_modelo", "cierre"):
            for _ in range(3):
                filas.append((_ruido(r, texto), prev, "ambigua"))
    for texto in FUERA:
        for _ in range(4):
            filas.append((_ruido(r, texto), r.choice(prevs), "fuera_de_contexto"))
    for p in FUERA_PLANTILLAS:
        for _ in range(8):
            texto = p.format(**{k: r.choice(v) for k, v in FUERA_RELLENOS.items()})
            filas.append((_ruido(r, texto), r.choice(prevs), "fuera_de_contexto"))
    if con_agentes:
        filas += frases_agentes(excluir) * 3                         # las frases reales simuladas pesan más que las de plantilla
    r.shuffle(filas)
    return filas


def _ruido(r, texto):
    """Variaciones de escritura: sin tildes, sin signos, mayúsculas, errores comunes."""
    x = r.random()
    if x < 0.15:
        texto = texto.lower()
    elif x < 0.25:
        texto = texto.replace("¿", "").replace("?", "")
    elif x < 0.32:
        texto = texto.upper()
    if r.random() < 0.2:
        texto = texto.replace("cuánto", "cuanto").replace("qué", "que").replace("está", "esta").replace("más", "mas").replace("cuál", "cual")
    return texto


# --------------------------------------------------------------------------------------------- PRUEBA (frases escritas aparte)
PRUEBA = [
    ("necesito saber las ventas que vamos a tener de FOODS_3_090 en CA_1", None, "demanda_esperada"),
    ("¿qué tan alta puede ser la demanda de hogar en Texas el próximo mes?", None, "rango_proyeccion"),
    ("de qué productos debería hacer pedido esta semana en WI_2", None, "cuanto_pedir"),
    ("dime cuántas unidades de HOBBIES_1_117 debo comprar para tener 95 % de servicio", None, "cuanto_pedir"),
    ("hay algo que se me pueda agotar pronto en la tienda de California", None, "riesgo_quiebre"),
    ("tengo productos acumulados que no se van a vender", None, "sobreinventario"),
    ("cuáles son los 10 artículos que más se van a mover en TX_2", None, "top_productos"),
    ("entre el tft y lightgbm quién se equivoca menos", None, "comparar_modelos"),
    ("las predicciones que veo son de qué día", None, "estado_modelo"),
    ("cuánta mercancía hay hoy de FOODS_1_025", None, "inventario_actual"),
    ("a qué te refieres con nivel de servicio", None, "glosario"),
    ("hola, buen día", None, "saludo"),
    ("explícame para qué sirve esta aplicación", None, "ayuda"),
    ("muchas gracias por la ayuda", None, "cierre"),
    ("cuánto voy a vender de alimentos en las próximas dos semanas", None, "demanda_esperada"),
    ("quiero ver el peor y el mejor caso de la demanda de FOODS_2_398", None, "rango_proyeccion"),
    ("qué cantidad reponer de la categoría HOUSEHOLD", None, "cuanto_pedir"),
    ("dónde me faltaría inventario en Wisconsin", None, "riesgo_quiebre"),
    ("qué cosas tengo sobrando en HOBBIES", None, "sobreinventario"),
    ("los cinco mejores productos de FOODS por demanda", None, "top_productos"),
    ("qué modelo conviene usar", None, "comparar_modelos"),
    ("cuándo se corrió el último entrenamiento", None, "estado_modelo"),
    ("qué quiere decir mase", None, "glosario"),
    ("cuántas unidades tenemos en CA_1", None, "inventario_actual"),
    # fuera de contexto
    ("quién es el mejor jugador de baloncesto", None, "fuera_de_contexto"),
    ("cómo se hace una torta de chocolate", None, "fuera_de_contexto"),
    ("cuál será el clima este domingo", None, "fuera_de_contexto"),
    ("ayúdame a escribir una carta de amor", None, "fuera_de_contexto"),
    ("cuántos kilómetros hay entre Bogotá y Cali", None, "fuera_de_contexto"),
    ("qué opinas del gobierno actual", None, "fuera_de_contexto"),
    ("explícame cómo funciona un avión", None, "fuera_de_contexto"),
    ("dame un consejo para estudiar mejor", None, "fuera_de_contexto"),
    ("cuánto vale el euro", None, "fuera_de_contexto"),
    ("pronóstico del tiempo en Medellín", None, "fuera_de_contexto"),
    # con contexto de la conversación
    ("¿y en WI_2?", "demanda_esperada", "seguimiento"),
    ("y para hogar", "cuanto_pedir", "seguimiento"),
    ("ahora con 95 %", "cuanto_pedir", "seguimiento"),
    ("¿y la semana que viene?", "demanda_esperada", "seguimiento"),
    ("¿y con el TFT?", "comparar_modelos", "seguimiento"),
    ("cuántas?", "riesgo_quiebre", "riesgo_quiebre"),
    ("dame el detalle", "sobreinventario", "sobreinventario"),
    ("¿cuánto sería?", "cuanto_pedir", "cuanto_pedir"),
    ("muéstrame la lista", "top_productos", "top_productos"),
    ("¿cuánto?", None, "ambigua"),
    ("dime más", "saludo", "ambigua"),
]

# Prueba nueva (no se usó para ajustar el entrenamiento): es la exactitud que se reporta.
PRUEBA_FINAL = [
    ("quisiera conocer la proyección de ventas de HOUSEHOLD_2_410 en TX_2", None, "demanda_esperada"),
    ("qué cantidad de FOODS vamos a vender la semana 3", None, "demanda_esperada"),
    ("cuál sería el escenario más optimista de ventas de pasatiempos", None, "rango_proyeccion"),
    ("con qué margen de incertidumbre se calculó el pronóstico de FOODS_1_200", None, "rango_proyeccion"),
    ("indícame el pedido que debo hacer de hogar con un 80 % de servicio", None, "cuanto_pedir"),
    ("qué volumen tengo que reabastecer en la tienda de Texas", None, "cuanto_pedir"),
    ("productos que probablemente se acaben antes de fin de mes en CA_1", None, "riesgo_quiebre"),
    ("en qué referencias estoy corto de existencias", None, "riesgo_quiebre"),
    ("qué mercancía se me está quedando sin salida", None, "sobreinventario"),
    ("dime los artículos con demasiadas unidades guardadas en Wisconsin", None, "sobreinventario"),
    ("lista de los 7 productos con mayor proyección en HOBBIES", None, "top_productos"),
    ("cuáles son los que más voy a vender en la categoría de alimentos", None, "top_productos"),
    ("qué algoritmo tiene mejores métricas", None, "comparar_modelos"),
    ("muéstrame cómo le fue al tft frente a ets", None, "comparar_modelos"),
    ("con qué datos se hizo la última predicción", None, "estado_modelo"),
    ("cuál es el modelo que está en uso ahora", None, "estado_modelo"),
    ("cuántas unidades de HOBBIES_2_050 tengo guardadas", None, "inventario_actual"),
    ("a cuánto asciende mi stock en la tienda WI_2", None, "inventario_actual"),
    ("qué se entiende por quiebre", None, "glosario"),
    ("explica qué es la cobertura del intervalo", None, "glosario"),
    ("buenas tardes", None, "saludo"),
    ("cómo puedo usar este asistente", None, "ayuda"),
    ("te agradezco mucho", None, "cierre"),
    ("dime algo sobre el calentamiento global", None, "fuera_de_contexto"),
    ("cómo preparo un café frío", None, "fuera_de_contexto"),
    ("cuál es el mejor equipo de fútbol de Europa", None, "fuera_de_contexto"),
    ("recomiéndame un lugar para viajar en diciembre", None, "fuera_de_contexto"),
    ("cuánto cuesta una bicicleta eléctrica", None, "fuera_de_contexto"),
    ("escribe una canción de cumpleaños", None, "fuera_de_contexto"),
    ("cómo se calcula el área de un círculo", None, "fuera_de_contexto"),
    ("quién descubrió América", None, "fuera_de_contexto"),
    ("ahora para Texas", "riesgo_quiebre", "seguimiento"),
    ("y de HOBBIES?", "top_productos", "seguimiento"),
    ("y si lo hago con 90 %", "cuanto_pedir", "seguimiento"),
    ("los productos de ese listado", "sobreinventario", "sobreinventario"),
    ("¿cuántas unidades en total?", "demanda_esperada", "demanda_esperada"),
    ("¿y cuántos serían?", "riesgo_quiebre", "riesgo_quiebre"),
    ("mmm y entonces", None, "ambigua"),
]

# Prueba 3: escrita después de ampliar el vocabulario y sin ajustar nada con ella. Es la exactitud que se reporta.
PRUEBA_3 = [
    ("¿qué tanta salida van a tener los productos de hogar el próximo mes?", None, "demanda_esperada"),
    ("estimación de unidades vendidas de FOODS_3_121 para dos semanas", None, "demanda_esperada"),
    ("¿entre cuánto y cuánto oscilará la demanda de WI_2?", None, "rango_proyeccion"),
    ("qué tan desviada podría salir la predicción de ventas de HOBBIES", None, "rango_proyeccion"),
    ("¿qué cantidad de FOODS_2_050 debo encargar con 95 %?", None, "cuanto_pedir"),
    ("para cubrir la demanda de CA_1, ¿cuánto surto?", None, "cuanto_pedir"),
    ("en qué productos voy a quedar desabastecido en TX_2", None, "riesgo_quiebre"),
    ("¿hay referencias a punto de terminarse?", None, "riesgo_quiebre"),
    ("qué artículos tengo almacenados de más en HOUSEHOLD", None, "sobreinventario"),
    ("¿hay mercancía parada en CA_1?", None, "sobreinventario"),
    ("¿qué productos lideran la demanda proyectada en Texas?", None, "top_productos"),
    ("ranking de los 5 que más se venderán de HOBBIES", None, "top_productos"),
    ("¿qué tan confiable es el tft comparado con lightgbm?", None, "comparar_modelos"),
    ("¿cuál tiene más error, ets o naive?", None, "comparar_modelos"),
    ("¿hasta qué día llegan las proyecciones?", None, "estado_modelo"),
    ("¿cuándo se refrescaron los pronósticos por última vez?", None, "estado_modelo"),
    ("¿qué tanto stock queda de HOUSEHOLD_1_300?", None, "inventario_actual"),
    ("¿cuántas piezas hay en TX_2 ahora mismo?", None, "inventario_actual"),
    ("no entiendo qué es el nivel de servicio del 95 %", None, "glosario"),
    ("¿para qué se usa el percentil 90?", None, "glosario"),
    ("buen día, ¿cómo estás?", None, "saludo"),
    ("¿qué tipo de consultas acepta este asistente?", None, "ayuda"),
    ("ok, muchas gracias, hasta luego", None, "cierre"),
    ("¿cuál es la distancia de la tierra al sol?", None, "fuera_de_contexto"),
    ("recomiéndame una receta vegana", None, "fuera_de_contexto"),
    ("¿cómo está el mercado inmobiliario?", None, "fuera_de_contexto"),
    ("cuéntame algo sobre dinosaurios", None, "fuera_de_contexto"),
    ("¿puedes explicarme la guerra fría?", None, "fuera_de_contexto"),
    ("¿qué serie veo esta noche?", None, "fuera_de_contexto"),
    ("¿cómo configuro mi router?", None, "fuera_de_contexto"),
    ("dime la capital de Japón", None, "fuera_de_contexto"),
    ("ahora lo quiero para California", "cuanto_pedir", "seguimiento"),
    ("¿y si es solo HOUSEHOLD?", "demanda_esperada", "seguimiento"),
    ("dame lo mismo con TFT", "comparar_modelos", "seguimiento"),
    ("y para la semana 4", "demanda_esperada", "seguimiento"),
    ("¿cuántos son?", "sobreinventario", "sobreinventario"),
    ("muéstrame cuáles", "riesgo_quiebre", "riesgo_quiebre"),
    ("¿y de cuánto sería?", "cuanto_pedir", "cuanto_pedir"),
    ("ok, ¿y?", None, "ambigua"),
]

# Prueba 4: escrita antes de medir el modelo con las pistas léxicas y sin ajustar nada con ella. Es la exactitud que se reporta.
PRUEBA_4 = [
    ("¿cuántas unidades de HOUSEHOLD_1_052 se despacharán en la semana 1?", None, "demanda_esperada"),
    ("necesito el volumen de ventas previsto para la categoría hogar en Wisconsin", None, "demanda_esperada"),
    ("¿hasta cuánto podría llegar la demanda de FOODS_3_300 con mala suerte?", None, "rango_proyeccion"),
    ("quiero conocer la banda de incertidumbre de la proyección en TX_2", None, "rango_proyeccion"),
    ("qué cantidad conviene encargar de HOBBIES_1_040 para estar tranquilo con 95 %", None, "cuanto_pedir"),
    ("¿cuánto reabastecer en CA_1 para no quedarme corto?", None, "cuanto_pedir"),
    ("¿qué artículos me van a faltar en la tienda de California?", None, "riesgo_quiebre"),
    ("alerta: referencias con probabilidad de agotarse esta semana", None, "riesgo_quiebre"),
    ("¿en qué categoría tengo mercancía acumulada sin rotación?", None, "sobreinventario"),
    ("dime los productos sobreabastecidos en Wisconsin", None, "sobreinventario"),
    ("¿cuáles serán los 8 artículos más demandados del próximo mes?", None, "top_productos"),
    ("muéstrame el ranking de productos principales en HOUSEHOLD", None, "top_productos"),
    ("¿cuál de los modelos comete menos errores?", None, "comparar_modelos"),
    ("quiero comparar la precisión de ets contra el tft", None, "comparar_modelos"),
    ("¿las predicciones están vigentes o ya son viejas?", None, "estado_modelo"),
    ("¿en qué fecha se corrió el último entrenamiento del tft?", None, "estado_modelo"),
    ("¿qué existencias tengo ahora de FOODS_1_100?", None, "inventario_actual"),
    ("dime cuántas piezas tenemos en bodega en CA_1", None, "inventario_actual"),
    ("¿a qué se refiere el stock objetivo?", None, "glosario"),
    ("explícame qué es la mediana de las ventas", None, "glosario"),
    ("hola, buenas", None, "saludo"),
    ("¿cómo funciona este chat?", None, "ayuda"),
    ("perfecto, mil gracias por todo", None, "cierre"),
    ("¿cuánto mide el Everest?", None, "fuera_de_contexto"),
    ("recomiéndame un videojuego", None, "fuera_de_contexto"),
    ("¿qué significa la palabra efímero?", None, "fuera_de_contexto"),
    ("cuéntame cómo funciona la bolsa de Nueva York", None, "fuera_de_contexto"),
    ("dame ideas para decorar mi sala", None, "fuera_de_contexto"),
    ("¿cuál es el río más largo del mundo?", None, "fuera_de_contexto"),
    ("escribe un cuento corto para niños", None, "fuera_de_contexto"),
    ("¿y para Wisconsin?", "cuanto_pedir", "seguimiento"),
    ("ahora con el modelo lightgbm", "demanda_esperada", "seguimiento"),
    ("¿y si lo veo de la categoría FOODS?", "top_productos", "seguimiento"),
    ("¿cuántos hay?", "riesgo_quiebre", "riesgo_quiebre"),
    ("dame el detalle de esos", "sobreinventario", "sobreinventario"),
    ("¿y cuánto serían en total?", "cuanto_pedir", "cuanto_pedir"),
    ("ajá y qué", None, "ambigua"),
]


# Prueba 5: frases nuevas escritas antes de medir las últimas mejoras (conocimiento general como negativos, reglas de seguridad). Es la exactitud que se reporta.
PRUEBA_5 = [
    ("¿cuánto voy a facturar en unidades de FOODS_3_077 en CA_1 el próximo mes?", None, "demanda_esperada"),
    ("necesito el pronóstico de ventas de pasatiempos para dos semanas", None, "demanda_esperada"),
    ("¿qué tan malo puede salir el escenario de ventas de WI_2?", None, "rango_proyeccion"),
    ("dame el tope probable de demanda en HOUSEHOLD_2_090", None, "rango_proyeccion"),
    ("¿cuánto debo surtir de alimentos en Texas?", None, "cuanto_pedir"),
    ("calcula cuántas unidades ordenar de HOBBIES_2_010 con 90 % de servicio", None, "cuanto_pedir"),
    ("¿qué referencias están a punto de acabarse en WI_2?", None, "riesgo_quiebre"),
    ("dime si hay mercancía que no se mueve en la tienda de Texas", None, "sobreinventario"),
    ("los 6 productos que más se van a mover en HOBBIES", None, "top_productos"),
    ("¿qué tal es el desempeño del tft frente a los demás?", None, "comparar_modelos"),
    ("¿cuándo se generó el último pronóstico?", None, "estado_modelo"),
    ("¿cuántas unidades quedan de FOODS_2_020 en TX_2?", None, "inventario_actual"),
    ("¿qué es el pinball?", None, "glosario"),
    ("buenos días", None, "saludo"),
    ("¿qué cosas puedo preguntarte?", None, "ayuda"),
    ("excelente, gracias", None, "cierre"),
    ("¿cuánto cuesta una laptop gamer?", None, "fuera_de_contexto"),
    ("cuéntame sobre la revolución francesa", None, "fuera_de_contexto"),
    ("¿cuál es el mejor método para aprender a tocar guitarra?", None, "fuera_de_contexto"),
    ("¿qué debo hacer si me duele la cabeza?", None, "fuera_de_contexto"),
    ("¿cuántos continentes hay?", None, "fuera_de_contexto"),
    ("traduce buenos días al alemán", None, "fuera_de_contexto"),
    ("¿qué película me recomiendas para esta noche?", None, "fuera_de_contexto"),
    ("explícame qué es la fotosíntesis", None, "fuera_de_contexto"),
    ("¿cómo se llama el presidente de Francia?", None, "fuera_de_contexto"),
    ("¿cuál es la mejor forma de ahorrar dinero?", None, "fuera_de_contexto"),
    ("y para Texas", "top_productos", "seguimiento"),
    ("ahora al 80 %", "cuanto_pedir", "seguimiento"),
    ("¿cuáles son?", "sobreinventario", "sobreinventario"),
    ("¿cuánto en total?", "demanda_esperada", "demanda_esperada"),
    ("hmm", None, "ambigua"),
]


# Prueba 6: frases nuevas para la intención de ventas pasadas y su contraste con el futuro, escritas antes de entrenar con ella. Se reporta junto con la prueba 5.
PRUEBA_6 = [
    ("¿qué productos se vendieron más el último mes registrado?", None, "ventas_pasadas"),
    ("dime cuántas unidades vendimos la semana pasada en TX_2", None, "ventas_pasadas"),
    ("cuáles fueron los 3 artículos con más ventas en CA_1 en los últimos 28 días", None, "ventas_pasadas"),
    ("quiero ver el historial de ventas de FOODS_2_398", None, "ventas_pasadas"),
    ("¿cómo nos fue en ventas de hogar el mes pasado?", None, "ventas_pasadas"),
    ("total vendido de pasatiempos hasta ahora", None, "ventas_pasadas"),
    ("pero quiero que me digas lo que tuvieron más ventas el último mes registrado", "top_productos", "ventas_pasadas"),
    ("¿y de la semana anterior?", "ventas_pasadas", "seguimiento"),
    ("¿cuánto se va a vender de HOBBIES_1_117 el próximo mes?", None, "demanda_esperada"),
    ("cuáles serán los productos más vendidos la semana 2", None, "top_productos"),
    ("qué productos van a tener más ventas en Texas", None, "top_productos"),
    ("proyección de ventas de alimentos para 14 días", None, "demanda_esperada"),
]
