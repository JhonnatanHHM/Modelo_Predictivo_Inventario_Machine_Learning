"""Pruebas del LightGBM diario con datos sintéticos (no necesitan base de datos ni M5)."""
from types import SimpleNamespace

import numpy as np
from django.test import SimpleTestCase

from ml import diario


def datos_sinteticos(n=6, T=1000, semilla=0):
    rng = np.random.default_rng(semilla)
    dia = np.arange(T)
    nivel = rng.uniform(0.3, 3, (n, 1)) * (1 + 0.5 * np.sin(2 * np.pi * dia / 7))[None, :]
    Y = rng.poisson(nivel).astype(float)
    Y[0, :40] = np.nan                                                    # una serie que empieza más tarde
    P = np.full((n, T), 2.0) + rng.normal(0, 0.05, (n, T))
    tienda, depto = np.array([0, 0, 1, 1, 2, 2][:n]), np.array([0, 1, 0, 1, 0, 1][:n])
    Y0 = np.nan_to_num(Y)
    ULT_POS = np.maximum.accumulate(np.where(Y0 > 0, dia[None, :], -1), axis=1)
    return SimpleNamespace(ids=[f"s{k}" for k in range(n)], Y=Y, P=P, SN=(rng.random((n, T)) < .1).astype(float), EV=(rng.random((n, T)) < .03).astype(float),
                           DOW=(dia % 7 + 1).astype(float), MES=((dia // 30) % 12 + 1).astype(float), DMES=(dia % 30 + 1).astype(float), ETIPO=np.where(rng.random(T) < .03, 1.0, -1.0),
                           inicio=np.array([int(np.argmax(np.isfinite(Y[k]))) for k in range(n)]), ULT_POS=ULT_POS,
                           TIENDA_SUM=np.vstack([Y0[tienda == g].sum(0) for g in tienda]), GRUPO_SUM=np.vstack([Y0[(tienda == g) & (depto == d)].sum(0) for g, d in zip(tienda, depto)]),
                           tienda=tienda, depto=depto, estado=tienda)


class DiarioTests(SimpleTestCase):
    def test_variables_completas_y_sin_futuro(self):
        D = datos_sinteticos()
        df = diario.filas_origen(D, 899, con_y=False)
        self.assertEqual(list(diario.COLS_X), diario.VARS_BASE + diario.VARS_NUEVAS)
        self.assertEqual(len(diario.COLS_X), 38)
        self.assertEqual(df.shape[0], len(D.ids) * diario.H)
        self.assertTrue(set(diario.COLS_X) <= set(df.columns))
        # cambiar las ventas posteriores al origen no puede alterar ninguna variable (no hay fuga del futuro)
        D2 = datos_sinteticos(); D2.Y[:, 900:] += 50
        a, b = df[diario.COLS_X].to_numpy(), diario.filas_origen(D2, 899, con_y=False)[diario.COLS_X].to_numpy()
        self.assertTrue(np.array_equal(a, b, equal_nan=True))

    def test_pronostico_ordenado_no_negativo_y_sin_fuga(self):
        D = datos_sinteticos()
        Q = diario.pronosticar(D, 900)
        self.assertEqual(Q.shape, (len(D.ids), diario.H, 3))
        self.assertTrue(np.isfinite(Q).all() and (Q >= 0).all())
        self.assertTrue((Q[:, :, 0] <= Q[:, :, 1]).all() and (Q[:, :, 1] <= Q[:, :, 2]).all())
        D2 = datos_sinteticos(); D2.Y[:, 900:] += 50                      # el pronóstico con origen 900 no debe depender de nada posterior
        self.assertTrue(np.allclose(Q, diario.pronosticar(D2, 900)))
