"""Pasa los datos de la base (PostgreSQL) a matrices de numpy: una fila por serie y una columna por día (d_1 en la columna 0)."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from apps.catalogo.models import Calendario, PrecioSemanal, Serie, VentaDiaria


@dataclass
class Datos:
    ids: list            # id_m5 de cada serie, ordenado
    serie_pk: np.ndarray
    Y: np.ndarray        # ventas (n, T); NaN antes de la primera venta y en el futuro
    P: np.ndarray        # precio (n, T); NaN si ese día no hay precio
    SN: np.ndarray       # SNAP del estado de la serie
    EV: np.ndarray       # día con evento
    DOW: np.ndarray      # día de la semana (T,)
    MES: np.ndarray      # mes (T,)
    fechas: list         # fecha de cada día (T,)
    inicio: np.ndarray   # índice (0-based) de la primera venta de cada serie
    tienda: np.ndarray   # códigos numéricos para LightGBM
    depto: np.ndarray
    estado: np.ndarray
    rotacion: list
    tienda_nombre: list
    depto_nombre: list
    ultimo_dnum: int     # último día con ventas reales (d_1941 en M5)
    DMES: np.ndarray     # día del mes (T,)
    ETIPO: np.ndarray    # tipo de evento codificado (T,); -1 si no hay evento
    ULT_POS: np.ndarray  # (n, T) índice del último día con venta positiva hasta cada día (-1 si aún no hubo)
    TIENDA_SUM: np.ndarray  # (n, T) ventas totales de la tienda de cada serie
    GRUPO_SUM: np.ndarray   # (n, T) ventas totales de la tienda x departamento de cada serie


def cargar():
    cal = list(Calendario.objects.order_by("dnum").values_list("dnum", "fecha", "wm_yr_wk", "dia_semana", "mes", "evento", "snap_ca", "snap_tx", "snap_wi", "tipo_evento"))
    T = len(cal)
    assert [c[0] for c in cal] == list(range(1, T + 1)), "El calendario debe ser continuo desde d_1."
    fechas = [c[1] for c in cal]
    semana = np.array([c[2] for c in cal])
    DOW = np.array([c[3] for c in cal], dtype=float); MES = np.array([c[4] for c in cal], dtype=float)
    ev_dia = np.array([bool(c[5]) for c in cal], dtype=float)
    DMES = np.array([c[1].day for c in cal], dtype=float)
    ETIPO = pd.Series([c[9] or None for c in cal]).astype("category").cat.codes.to_numpy(dtype=float)     # igual que el laboratorio: códigos por orden alfabético, -1 sin evento
    snap_estado = {"CA": np.array([c[6] for c in cal], dtype=float), "TX": np.array([c[7] for c in cal], dtype=float), "WI": np.array([c[8] for c in cal], dtype=float)}

    series = list(Serie.objects.select_related("tienda", "departamento").order_by("id_m5"))
    n = len(series)
    fila = {s.id: i for i, s in enumerate(series)}
    idx_fecha = {f: i for i, f in enumerate(fechas)}

    Y = np.full((n, T), np.nan)
    v = pd.DataFrame(list(VentaDiaria.objects.values_list("serie_id", "fecha", "unidades")), columns=["s", "f", "u"])
    Y[v.s.map(fila).to_numpy(), v.f.map(idx_fecha).to_numpy()] = v.u.to_numpy(float)
    ultimo = int(np.max(np.where(np.isfinite(Y).any(axis=0))[0]) + 1)

    semanas = sorted(set(semana.tolist())); idx_sem = {w: i for i, w in enumerate(semanas)}
    Pw = np.full((n, len(semanas)), np.nan)
    p = pd.DataFrame(list(PrecioSemanal.objects.values_list("serie_id", "wm_yr_wk", "precio")), columns=["s", "w", "p"])
    p = p[p.w.isin(idx_sem)]
    Pw[p.s.map(fila).to_numpy(), p.w.map(idx_sem).to_numpy()] = p.p.astype(float).to_numpy()
    P = Pw[:, [idx_sem[w] for w in semana]]
    P[np.isnan(Y) & (np.arange(T)[None, :] < ultimo)] = np.nan          # antes de la primera venta no importa el precio

    SN = np.vstack([snap_estado[s.tienda.estado] for s in series])
    EV = np.tile(ev_dia, (n, 1))
    inicio = np.array([int(np.argmax(np.isfinite(Y[k]))) for k in range(n)])
    codigos = lambda vals: pd.Series(vals).astype("category").cat.codes.to_numpy()
    cod_tienda, cod_depto = codigos([s.tienda.codigo for s in series]), codigos([s.departamento.codigo for s in series])
    pos = np.where(np.nan_to_num(Y) > 0, np.arange(T)[None, :], -1)
    ULT_POS = np.maximum.accumulate(pos, axis=1)
    Y0 = np.nan_to_num(Y)
    suma_tienda = {g: Y0[cod_tienda == g].sum(0) for g in np.unique(cod_tienda)}
    cod_grupo = cod_tienda * 100 + cod_depto
    suma_grupo = {g: Y0[cod_grupo == g].sum(0) for g in np.unique(cod_grupo)}
    TIENDA_SUM = np.vstack([suma_tienda[g] for g in cod_tienda]); GRUPO_SUM = np.vstack([suma_grupo[g] for g in cod_grupo])
    return Datos(ids=[s.id_m5 for s in series], serie_pk=np.array([s.id for s in series]), Y=Y, P=P, SN=SN, EV=EV, DOW=DOW, MES=MES, fechas=fechas,
                 inicio=inicio, tienda=cod_tienda, depto=cod_depto,
                 estado=codigos([s.tienda.estado for s in series]), rotacion=[s.rotacion for s in series],
                 tienda_nombre=[s.tienda.codigo for s in series], depto_nombre=[s.departamento.codigo for s in series], ultimo_dnum=ultimo,
                 DMES=DMES, ETIPO=ETIPO, ULT_POS=ULT_POS, TIENDA_SUM=TIENDA_SUM, GRUPO_SUM=GRUPO_SUM)
