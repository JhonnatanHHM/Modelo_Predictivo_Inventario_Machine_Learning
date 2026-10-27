"""Pruebas de las reglas del chat que no necesitan base de datos: extracción de entidades, detección de análisis y alcance."""
from django.test import SimpleTestCase

from apps.chat.nlp import analisis, entidades


def ents(texto):
    return entidades.extraer(texto)["entidades"]


class EntidadesTests(SimpleTestCase):
    def test_tienda_por_codigo_y_por_estado(self):
        self.assertEqual(ents("ventas en CA_1")["tienda"], "CA_1")
        self.assertEqual(ents("ventas en Texas")["tienda"], "TX_2")
        self.assertEqual(ents("ventas en wisconsin")["tienda"], "WI_2")

    def test_tienda_negada_no_cuenta(self):
        self.assertEqual(ents("no, yo quería ver Texas, no California")["tienda"], "TX_2")

    def test_producto_departamento_y_categoria(self):
        self.assertEqual(ents("demanda de FOODS_2_398")["producto"], "FOODS_2_398")
        self.assertEqual(ents("demanda de HOUSEHOLD_1")["departamento"], "HOUSEHOLD_1")
        self.assertEqual(ents("cuánto pedir de hogar")["categoria"], "HOUSEHOLD")

    def test_nivel_de_servicio(self):
        self.assertEqual(ents("pedido con 95 % de servicio")["nivel"], 0.95)
        self.assertEqual(ents("pedido con 80% de servicio")["nivel"], 0.8)

    def test_horizonte(self):
        self.assertEqual(ents("demanda de la semana 2")["horizonte"], {"tipo": "semana", "n": 2})
        self.assertEqual(ents("demanda de los próximos 28 días")["horizonte"], {"tipo": "28d"})

    def test_periodos_del_pasado(self):
        self.assertEqual(ents("qué se vendió el último mes")["pasado"], {"n": 28})
        self.assertEqual(ents("ventas de 2015")["pasado"], {"anio": 2015})
        self.assertEqual(ents("ventas de marzo de 2015")["pasado"], {"mes_anio": [3, 2015]})
        self.assertEqual(ents("qué vendimos el 4 de julio de 2015")["pasado"]["fecha"], "2015-07-04")

    def test_orden_ascendente_y_promedio(self):
        e = ents("el producto que menos vende en promedio")
        self.assertEqual(e["orden"], "asc")
        self.assertEqual(e["metrica"], "promedio")

    def test_temas_ajenos(self):
        self.assertTrue(entidades.es_ajena(entidades.extraer("dame una receta de pasta")))
        self.assertFalse(entidades.es_ajena(entidades.extraer("cuánto pedir de FOODS_2_398")))


def clave(texto, ctx=None):
    return analisis.detectar(entidades.extraer(texto), ctx)


class DeteccionDeAnalisisTests(SimpleTestCase):
    def test_datos_que_el_aplicativo_no_tiene(self):
        for t in ["cuál es el margen de ganancia de FOODS_3", "quién es el proveedor de FOODS_1_001", "cuántos clientes entran a la tienda de Texas"]:
            self.assertEqual(clave(t), "no_disponible", t)

    def test_periodos_sin_datos(self):
        self.assertEqual(clave("ventas de HOBBIES en julio de 2017"), "periodo_sin_datos")
        self.assertEqual(clave("pronóstico para diciembre de 2016"), "periodo_sin_datos")

    def test_fecha_inexistente(self):
        self.assertEqual(clave("qué pasó el 31 de febrero de 2015"), "fecha_invalida")

    def test_analisis_con_datos(self):
        self.assertEqual(clave("¿se vende más en fin de semana o entre semana?"), "fin_semana")
        self.assertEqual(clave("compara ventas en días SNAP contra días sin SNAP en California"), "snap")
        self.assertEqual(clave("cuánto se vendió en Navidad comparado con un día normal"), "eventos")
        self.assertEqual(clave("cuál es el producto más caro de la tienda TX_2"), "precio")
        self.assertEqual(clave("qué categoría genera más ingresos"), "ingresos")
        self.assertEqual(clave("qué porcentaje de las ventas representa la categoría FOODS"), "participacion")

    def test_escenarios_no_se_simulan(self):
        self.assertEqual(clave("¿qué pasaría si las ventas suben 20 %?"), "escenarios")

    def test_otros_temas_no_activan_analisis(self):
        for t in ["¿cuánto cuesta una laptop gamer?", "cuéntame sobre la revolución francesa", "¿cuál es la mejor forma de ahorrar dinero?", "¿qué es el pinball?"]:
            self.assertIsNone(clave(t), t)

    def test_seguimiento_usa_el_contexto(self):
        self.assertEqual(clave("¿y ese día cae en algún evento?", {"dia_ref": "2016-06-06"}), "dia_info")
