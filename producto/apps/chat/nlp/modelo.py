"""Clasificador de intenciones del chat: regresión logística sobre TF-IDF de palabras y de caracteres del texto abstraído (las entidades se
reemplazan por marcas), la intención anterior de la conversación (contexto) y banderas de entidades presentes. Se entrena en segundos, sin GPU ni APIs."""
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from . import datos, entidades

VERSION = 10                         # súbela cuando cambien las intenciones o las variables de entrada: un clasificador guardado de otra versión se reentrena solo
UMBRAL = 0.35                       # por debajo, la pregunta se considera fuera de lo que el aplicativo entiende
_PREVIAS = ["ninguna"] + datos.INTENCIONES


class Clasificador:
    def _contexto(self, prevs, bandas):
        uno = np.zeros((len(prevs), len(_PREVIAS)))
        for i, p in enumerate(prevs):
            uno[i, _PREVIAS.index(p if p in _PREVIAS else "ninguna")] = 1.0
        return csr_matrix(np.hstack([uno, np.array(bandas)]))

    def _matriz(self, textos, prevs, bandas, ajustar=False):
        if ajustar:
            self.palabras = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
            self.letras = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)
            partes = [self.palabras.fit_transform(textos), self.letras.fit_transform(textos)]
        else:
            partes = [self.palabras.transform(textos), self.letras.transform(textos)]
        return hstack(partes + [self._contexto(prevs, bandas)]).tocsr()

    @staticmethod
    def _preparar(texto):
        info = entidades.extraer(texto)
        return entidades.abstraer(info), entidades.banderas(info)

    def entrenar(self, filas):
        self.version = VERSION
        textos, bandas = zip(*[self._preparar(t) for t, _, _ in filas])
        X = self._matriz(list(textos), [p for _, p, _ in filas], list(bandas), ajustar=True)
        self.clf = LogisticRegression(C=25, max_iter=3000, class_weight="balanced")
        self.clf.fit(X, [y for _, _, y in filas])
        return self

    def probabilidades(self, texto, prev):
        abstracto, bandas = self._preparar(texto)
        p = self.clf.predict_proba(self._matriz([abstracto], [prev], [bandas]))[0]
        return dict(zip(self.clf.classes_, p))

    def predecir(self, texto, prev=None):
        """Devuelve (intención, confianza). Si la confianza es baja, la intención es 'fuera_de_contexto'."""
        pr = self.probabilidades(texto, prev)
        intencion = max(pr, key=pr.get)
        return (intencion, pr[intencion]) if pr[intencion] >= UMBRAL else ("fuera_de_contexto", pr[intencion])


def _evaluar_conjunto(clasificador, frases):
    """Evalúa el flujo completo del chat (modelo + umbrales + reglas). Estricta: la intención debe coincidir. Funcional: además cuenta como acierto
    que una frase de seguimiento se resuelva como la intención anterior (hace lo mismo) o que la confirmación ofrezca la intención correcta."""
    from . import motor
    estricta, funcional, por, errores = 0, 0, {}, []
    for texto, prev, esperada in frases:
        pred, conf, opciones = motor.clasificar(clasificador, texto, prev)
        ok = pred == esperada
        ok_f = ok or (esperada == "seguimiento" and pred == prev) or (pred == "seguimiento" and esperada == prev and prev is not None) or (pred == "confirmar" and esperada in (opciones or []))
        estricta += ok
        funcional += ok_f
        por.setdefault(esperada, []).append(ok_f)
        if not ok_f:
            errores.append({"texto": texto, "contexto": prev, "esperada": esperada, "predicha": pred, "confianza": round(float(conf), 2)})
    n = len(frases)
    return {"exactitud": round(funcional / n, 3), "exactitud_estricta": round(estricta / n, 3), "n_prueba": n,
            "por_intencion": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(por.items())}, "errores": errores}


def evaluar(clasificador):
    """La exactitud que se reporta es la de la prueba 5 (frases nuevas, sin ajustar nada con ellas). Las demás conjuntos se usaron para diagnosticar y ampliar el entrenamiento."""
    final = _evaluar_conjunto(clasificador, datos.PRUEBA_5 + datos.PRUEBA_6)
    final["exactitud_desarrollo"] = _evaluar_conjunto(clasificador, datos.PRUEBA + datos.PRUEBA_FINAL + datos.PRUEBA_3 + datos.PRUEBA_4)["exactitud"]
    return final


def ruta_modelo():
    return Path(settings.MODELOS_DIR) / "chat" / "clasificador.joblib"


def entrenar_y_guardar():
    filas = datos.generar()
    c = Clasificador().entrenar(filas)
    metricas = evaluar(c)
    metricas.update({"n_entrenamiento": len(filas), "entrenado": datetime.now().strftime("%d/%m/%Y %H:%M"), "umbral": UMBRAL})
    ruta = ruta_modelo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(c, ruta)
    (ruta.parent / "metricas.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8")
    global _CACHE
    _CACHE = c
    return c, metricas


_CACHE = None


def obtener():
    """Carga el clasificador guardado; si no existe todavía, lo entrena (tarda unos segundos)."""
    global _CACHE
    if _CACHE is None:
        ruta = ruta_modelo()
        guardado = joblib.load(ruta) if ruta.exists() else None
        _CACHE = guardado if guardado is not None and getattr(guardado, "version", None) == VERSION else entrenar_y_guardar()[0]
    return _CACHE


def metricas_guardadas():
    ruta = ruta_modelo().parent / "metricas.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
