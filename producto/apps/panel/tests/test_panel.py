"""Pruebas del panel: acceso, páginas principales, perfil y filtros de reposición."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.panel.models import Perfil


class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user("prueba", password="clave-de-prueba")

    def test_todo_el_sitio_pide_acceso(self):
        for url in ["/", "/proyecciones/", "/reposicion/", "/modelos/", "/chat/", "/perfil/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/acceso/", r["Location"], url)

    def test_la_pagina_de_acceso_es_publica(self):
        self.assertEqual(self.client.get("/acceso/").status_code, 200)

    def test_inicio_de_sesion_y_salida(self):
        r = self.client.post("/acceso/", {"username": "prueba", "password": "clave-de-prueba"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/proyecciones/").status_code, 200)
        self.client.post("/salir/")
        self.assertEqual(self.client.get("/proyecciones/").status_code, 302)

    def test_contrasena_incorrecta(self):
        r = self.client.post("/acceso/", {"username": "prueba", "password": "mala"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "incorrectos")

    def test_paginas_sin_datos_explican_que_hacer(self):
        self.client.force_login(self.usuario)
        for url in ["/proyecciones/", "/reposicion/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "Generar predicciones")

    def test_no_hay_pestana_de_inicio_ni_de_administracion(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/proyecciones/")
        self.assertNotContains(r, "Administración")

    def test_la_raiz_lleva_a_proyecciones(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/")
        self.assertRedirects(r, "/proyecciones/", fetch_redirect_response=False)

    def test_perfil_guarda_nombre_y_avatar(self):
        self.client.force_login(self.usuario)
        self.client.post("/perfil/", {"nombre": "Ana", "sexo": "F"})
        p = Perfil.objects.get(usuario=self.usuario)
        self.assertEqual((p.nombre_mostrado, p.sexo), ("Ana", "F"))
        self.assertContains(self.client.get("/perfil/"), "Ana")

    def test_perfil_rechaza_un_sexo_invalido(self):
        self.client.force_login(self.usuario)
        self.client.post("/perfil/", {"nombre": "Ana", "sexo": "X"})
        self.assertEqual(Perfil.objects.get(usuario=self.usuario).sexo, "N")

    def test_cambio_de_contrasena(self):
        self.client.force_login(self.usuario)
        r = self.client.post("/perfil/", {"accion": "clave", "old_password": "clave-de-prueba", "new_password1": "otra-clave-9", "new_password2": "otra-clave-9"})
        self.assertEqual(r.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("otra-clave-9"))

    def test_el_nivel_de_servicio_acepta_punto_y_coma(self):
        self.client.force_login(self.usuario)
        for nivel in ["0.95", "0,95", "0.8", "basura"]:
            self.assertEqual(self.client.get("/reposicion/", {"nivel": nivel}).status_code, 200, nivel)
