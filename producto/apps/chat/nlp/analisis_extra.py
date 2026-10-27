"""Más análisis del chat (continuación de analisis.py): comparaciones entre tiendas, categorías o departamentos, comparación de periodos y crecimiento, estacionalidad,
volatilidad, clasificación ABC, cambios de precio, cobertura por grupo, proyección frente a lo real y otras preguntas cotidianas."""
import re
from datetime import date, timedelta

from django.db.models import Avg, Count, Max, Min, Q, StdDev, Sum
from django.db.models.functions import ExtractWeekDay

from apps.catalogo.models import Calendario, PrecioSemanal, Serie, VentaDiaria
from apps.pronosticos.models import InventarioActual, Prediccion, PrediccionAgregada

from . import analisis as A
from . import respuestas as R

CAMPOS = {"categoria": "serie__departamento__categoria__codigo", "tienda": "serie__tienda__codigo", "departamento": "serie__departamento__codigo"}
ESTADOS = {"california": "CA_1", "texas": "TX_2", "wisconsin": "WI_2"}
CATEGORIAS = {"foods": "FOODS", "food": "FOODS", "alimento": "FOODS", "alimentos": "FOODS", "comida": "FOODS", "comidas": "FOODS", "hobbies": "HOBBIES", "hobby": "HOBBIES",
              "pasatiempo": "HOBBIES", "pasatiempos": "HOBBIES", "household": "HOUSEHOLD", "hogar": "HOUSEHOLD"}
MES_NUM = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def menciones(t):
    """Tiendas, departamentos y categorías distintos que se nombran en el texto (en orden de aparición)."""
    tiendas = [f"{m[1].upper()}_{m[2]}" for m in re.finditer(r"\b(ca|tx|wi)[ _-]?([1-4])\b", t)]
    tiendas += [ESTADOS[m[1]] for m in re.finditer(r"\b(california|texas|wisconsin)\b", t)]
    deptos = [f"{m[1].upper()}_{m[2]}" for m in re.finditer(r"\b(foods|hobbies|household)[ _-]?([123])\b(?![ _-]?\d)", t)]
    cats = [CATEGORIAS[m[1]] for m in re.finditer(r"\b(foods|food|alimentos?|comidas?|hobbies|hobby|pasatiempos?|household|hogar)\b(?![ _-]?\d)", t)]
    return {"tienda": list(dict.fromkeys(tiendas)), "departamento": list(dict.fromkeys(deptos)), "categoria": list(dict.fromkeys(cats))}


def _nfilas(info, defecto=5, tope=15):
    return min(info["entidades"].get("cantidad") or defecto, tope)


def _med(x):
    return x["t"] / x["d"] if x["d"] else 0


# --------------------------------------------------------------------------------------------- comparar tiendas, categorías o departamentos
def comparar(ctx, info):
    t = info["normalizado"]
    lim = A._limites()
    m = menciones(t)
    tipo = next((k for k in ("tienda", "departamento", "categoria") if len(m[k]) >= 2), None)
    per = A._periodo(ctx, info, lim)
    if per is None:
        return A.periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    base = VentaDiaria.objects.filter(fecha__range=(desde, hasta))
    ult = PrecioSemanal.objects.aggregate(m=Max("wm_yr_wk"))["m"]
    if tipo is None:                                                 # «las tres tiendas», «cada categoría»
        tipo = "tienda" if re.search(r"tiendas|sedes|sucursales", t) else "categoria" if re.search(r"categorias", t) else "departamento"
        elegidos = None
    else:
        elegidos = m[tipo]
    campo = CAMPOS[tipo]
    g = list(base.values(campo).annotate(u=Sum("unidades"), d=Count("fecha", distinct=True)))
    if elegidos:
        g = [x for x in g if x[campo] in elegidos]
    if len(g) < 2:
        return {"texto": "Dime al menos dos tiendas, categorías o departamentos para compararlos, por ejemplo «compara CA_1 con TX_2»."}
    con_precio = bool(re.search(r"precio", t))
    precios = {x[campo]: float(x["p"]) for x in PrecioSemanal.objects.filter(wm_yr_wk=ult).values(*[CAMPOS[tipo].replace("serie__", "serie__")]).annotate(p=Avg("precio"))} if con_precio else {}
    nser = {x[campo.replace("serie__", "")]: x["n"] for x in Serie.objects.values(campo.replace("serie__", "")).annotate(n=Count("id"))}
    g.sort(key=lambda x: -x["u"])
    sup, inf_ = g[0], g[-1]
    filas = []
    for x in g:
        fila = [x[campo], R.fmt(x["u"]), R.fmt1(x["u"] / x["d"])]
        if con_precio:
            fila.append(f"${precios.get(x[campo], 0):.2f}")
        filas.append(fila)
    cols = [tipo.capitalize() if tipo != "categoria" else "Categoría", "Unidades", "Por día"] + (["Precio promedio actual"] if con_precio else [])
    if tipo != "tienda":
        sufijo = ""
    else:
        sufijo = ""
    texto = (f"En {nombre} ({A._rango(desde, hasta)}) vendió más {sup[campo]} con {R.fmt(sup['u'])} unidades, un {A._pct(sup['u'], inf_['u']).split(' ')[0]} % más que {inf_[campo]} ({R.fmt(inf_['u'])})."
             if len(g) == 2 else f"En {nombre} ({A._rango(desde, hasta)}) vendió más {sup[campo]} ({R.fmt(sup['u'])} unidades) y menos {inf_[campo]} ({R.fmt(inf_['u'])}).")
    if tipo != "tienda" and len(g) == 2 and nser:
        texto += " Ojo: no todos tienen el mismo número de productos (series), por eso también muestro el promedio por día."
    return {"texto": texto + sufijo, "columnas": cols, "filas": filas, "enlace": R._enlace("proyecciones", "Ver en Proyecciones")}


# --------------------------------------------------------------------------------------------- crecimiento y comparación de periodos
def _periodos(t, lim):
    ultimo = lim["m"]
    out = []
    for m in re.finditer(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+|del\s+)?(20\d\d)\b", t):
        mes, y = MES_NUM[m[1]], int(m[2])
        d0 = date(y, mes, 1)
        d1 = (date(y + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1))
        if lim["p"] <= d0 <= ultimo:
            out.append((f"{m[1]} de {y}", d0, min(d1, ultimo)))
    if len(out) >= 2:
        return out[:2]
    anios = sorted(set(int(a) for a in re.findall(r"\b(201[1-6])\b", t)))
    q = re.search(r"\b(primer|segundo|tercer|cuarto|1er|2do|3er|4to)\w*\s+(trimestre|semestre)", t)
    if q and anios:
        n = {"primer": 1, "1er": 1, "segundo": 2, "2do": 2, "tercer": 3, "3er": 3, "cuarto": 4, "4to": 4}[q[1]]
        paso = 3 if q[2] == "trimestre" else 6
        out = []
        for y in anios[:2]:
            d0 = date(y, paso * (n - 1) + 1, 1)
            fin_mes = paso * n
            d1 = date(y + (fin_mes == 12), fin_mes % 12 + 1, 1) - timedelta(days=1)
            if d0 <= ultimo:
                out.append((f"{q[0].split(' ')[0]} {q[2]} de {y}", d0, min(d1, ultimo)))
        return out
    if len(anios) >= 2:
        return [(str(y), date(y, 1, 1), min(date(y, 12, 31), ultimo)) for y in (anios[0], anios[-1])]
    return []


def tendencia2(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    lim = A._limites()
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    periodos = _periodos(t, lim)
    quien = bool(re.search(r"\b(?:producto|series?|articulo|item)s?\b|\bel que\b|\bcual (?:creci|cayo|subio|bajo)\w*|\bque mas (?:creci|cayo|subio|bajo)", t)
                 and re.search(r"mas creci|mas cayo|mas subio|mas bajo|mayor crecimiento|mayor caida|mas aumento|mas disminuy|creci\w+ mas|cay\w+ mas|que mas|cual creci|cual cayo|el que mas", t))
    agrupar = ents.get("agrupar") if ents.get("agrupar") in CAMPOS else next((k for k in CAMPOS if re.search(rf"cada {k}|por {k}|las {k}s|los {k}s|{k}s\b|que {k}", t) and not ctx.get(k)), None)
    if not quien and not agrupar and ctx.get("periodos_cmp") and ctx.get("agrupar_cmp") and len(t.split()) <= 8 and not _periodos(t, lim):
        if ctx["agrupar_cmp"] == "producto":
            quien = True
        else:
            agrupar = ctx["agrupar_cmp"] if not ctx.get(ctx["agrupar_cmp"]) else None
    if len(periodos) < 2 and ctx.get("periodos_cmp") and (quien or agrupar):
        periodos = [(n, date.fromisoformat(a), date.fromisoformat(b)) for n, a, b in ctx["periodos_cmp"]]
    if len(periodos) < 2 and agrupar:                                # sin periodos: los dos últimos años completos
        periodos = [("2014", date(2014, 1, 1), date(2014, 12, 31)), ("2015", date(2015, 1, 1), date(2015, 12, 31))]
    anios_txt = sorted(set(int(a) for a in re.findall(r"\b(201[1-6])\b", t)))
    if not quien and not agrupar and (len(anios_txt) > 2 or (len(anios_txt) >= 2 and re.search(r"resumen|por ano|cada ano|anual|evolucion|que ano|en que ano|ano se vendio|ano con mas|mensual", t))):
        return A.tendencia(ctx, info)
    if len(periodos) >= 2:
        (n0, a0, b0), (n1, a1, b1) = periodos[0], periodos[1]
        base = VentaDiaria.objects.filter(serie__in=qs)
        memoria = {"_ctx": {"periodos_cmp": [[n0, a0.isoformat(), b0.isoformat()], [n1, a1.isoformat(), b1.isoformat()]], "agrupar_cmp": agrupar or ("producto" if quien else None)}}
        d0, d1 = (b0 - a0).days + 1, (b1 - a1).days + 1
        parcial = abs(d0 - d1) > 10
        llave = CAMPOS[agrupar] if agrupar else ("serie_id" if quien else None)
        if llave is None:
            v0 = base.filter(fecha__range=(a0, b0)).aggregate(t=Sum("unidades"))["t"] or 0
            v1 = base.filter(fecha__range=(a1, b1)).aggregate(t=Sum("unidades"))["t"] or 0
            texto = f"{desc[0].upper() + desc[1:]} vendió {R.fmt(v0)} unidades en {n0} y {R.fmt(v1)} en {n1}: {n1} fue {A._pct(v1, v0)} que {n0}."
            if parcial:
                texto += f" Como los periodos no duran lo mismo, por día fueron {R.fmt1(v0 / d0)} frente a {R.fmt1(v1 / d1)} ({A._pct(v1 / d1, v0 / d0)})."
            if re.fullmatch(r"\d{4}", n0) and re.fullmatch(r"\d{4}", n1) and int(n1) > int(n0) and v0 and not parcial:
                cagr = (v1 / v0) ** (1 / (int(n1) - int(n0))) - 1
                texto += f" Crecimiento anual compuesto: {f'{100 * cagr:.1f}'.replace('.', ',')} % al año."
            return {"texto": texto, **memoria}
        v0 = {x[llave]: x["t"] for x in base.filter(fecha__range=(a0, b0)).values(llave).annotate(t=Sum("unidades"))}
        v1 = {x[llave]: x["t"] for x in base.filter(fecha__range=(a1, b1)).values(llave).annotate(t=Sum("unidades"))}
        k_ok = [k for k in v0 if v0[k] > 0 and k in v1]
        var = {k: (v1[k] / d1 - v0[k] / d0, 100 * ((v1[k] / d1) / (v0[k] / d0) - 1)) for k in k_ok}
        nota = " (por día, porque los periodos no duran lo mismo)" if parcial else ""
        if agrupar:
            filas = [[k, R.fmt(v0[k]), R.fmt(v1[k]), f"{var[k][1]:+.1f} %".replace(".", ",")] for k in sorted(var, key=lambda k: -var[k][1])]
            mejor, peor = filas[0], filas[-1]
            return {"texto": f"De {n0} a {n1}{nota}, creció más {mejor[0]} ({mejor[3]}) y creció menos o cayó más {peor[0]} ({peor[3]}).",
                    "columnas": [agrupar.capitalize() if agrupar != "categoria" else "Categoría", n0, n1, "Variación"], "filas": filas, **memoria}
        series = {s.id: s for s in qs}
        cae = bool(re.search(r"cayo|cayeron|caida|bajo|bajaron|disminuy|menos", t)) and not re.search(r"mas creci|mayor crecimiento|mas subio", t)
        orden = sorted(var, key=lambda k: var[k][0], reverse=not cae)[:_nfilas(info)]
        filas = [[series[k].item_id, series[k].tienda.codigo, R.fmt(v0[k]), R.fmt(v1[k]), f"{var[k][1]:+.0f} %"] for k in orden]
        if len(filas) == 1:
            return {"texto": f"El producto de {desc} que más {'cayó' if cae else 'creció'} entre {n0} y {n1}{nota} fue {filas[0][0]} en la tienda {filas[0][1]}: de {filas[0][2]} a {filas[0][3]} unidades ({filas[0][4]}).", **memoria}
        return {"texto": f"Los {len(filas)} productos de {desc} que más {'cayeron' if cae else 'crecieron'} entre {n0} y {n1}{nota}:",
                "columnas": ["Producto", "Tienda", n0, n1, "Cambio %"], "filas": filas, **memoria}
    if quien:                                                        # sin años: últimos 28 días frente a los 28 anteriores
        fin = lim["m"]
        r1, r0 = (fin - timedelta(days=27), fin), (fin - timedelta(days=55), fin - timedelta(days=28))
        base = VentaDiaria.objects.filter(serie__in=qs)
        v0 = {x["serie_id"]: x["t"] for x in base.filter(fecha__range=r0).values("serie_id").annotate(t=Sum("unidades"))}
        v1 = {x["serie_id"]: x["t"] for x in base.filter(fecha__range=r1).values("serie_id").annotate(t=Sum("unidades"))}
        var = {k: v1.get(k, 0) - v0[k] for k in v0}
        cae = bool(re.search(r"cayo|caida|bajo|disminuy", t))
        series = {s.id: s for s in qs}
        orden = sorted(var, key=var.get, reverse=not cae)[:_nfilas(info)]
        filas = [[series[k].item_id, series[k].tienda.codigo, R.fmt(v0[k]), R.fmt(v1.get(k, 0)), R.fmt(var[k])] for k in orden]
        return {"texto": f"Los {len(filas)} productos de {desc} que más {'cayeron' if cae else 'crecieron'} en los últimos 28 días frente a los 28 anteriores:",
                "columnas": ["Producto", "Tienda", "28 días previos", "Últimos 28 días", "Cambio (unid.)"], "filas": filas}
    return A.tendencia(ctx, info)


# --------------------------------------------------------------------------------------------- calendario y SNAP
def snap2(ctx, info):
    t = info["normalizado"]
    if re.search(r"considera|tiene en cuenta|incluye|usa(?:n)? (?:los )?dias|toma(?:n)? en cuenta", t) and re.search(r"modelo|pronostico|proyeccion|prediccion", t):
        return {"texto": "Sí: LightGBM y el TFT usan el calendario como variable de entrada, incluidos los días SNAP de cada estado y los eventos. Por eso la proyección ya refleja esos días; "
                         "puedes ver cuáles caen en el periodo preguntando «¿qué días SNAP hay en junio?»."}
    ents = info["entidades"]
    pide_efecto = bool(re.search(r"suben|bajan|afect|venden mas|vende mas|aumenta|efecto|ventas|vender|mas ventas", t)) and not A.R_FUTURO.search(t)
    futuro = bool(A.R_FUTURO.search(t) or (ents.get("horizonte") and not pide_efecto) or re.search(r"cuantos dias|que dias|dias snap hay", t)
                  or (ctx.get("snap_rango") and re.search(r"esos dias|esas fechas|tambien hay|hay snap", t) and not pide_efecto))
    if not futuro:
        lim = A._limites()
        qs, desc, error = A._alcance(ctx)
        if error:
            return {"texto": error}
        desde, hasta, nombre, _, _ = A._periodo(ctx, info, lim) or (lim["p"], lim["m"], "todo el histórico", None, None)
        base = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta))
        if ents.get("buscar") or re.search(r"productos? (?:que |q )?(?:venden|se venden|suben)|que productos|cuales productos", t):   # ranking de productos
            g = base.values("serie_id").annotate(a=Avg("unidades", filter=Q(snap=True)), b=Avg("unidades", filter=Q(snap=False)))
            series = {s.id: s for s in qs}
            puntos = sorted(((x["a"] / x["b"], x["serie_id"], x["a"], x["b"]) for x in g if x["a"] is not None and x["b"] and x["b"] >= 1), reverse=True)[:_nfilas(info)]
            filas = [[series[sid].item_id, series[sid].tienda.codigo, R.fmt1(a), R.fmt1(b), f"{100 * (r - 1):+.0f} %"] for r, sid, a, b in puntos]
            return {"texto": f"En {nombre}, los productos de {desc} que más suben sus ventas en días SNAP (frente a días sin SNAP, solo productos con al menos 1 unidad por día):",
                    "columnas": ["Producto", "Tienda", "Por día en SNAP", "Por día sin SNAP", "Diferencia"], "filas": filas}
        g = {x["snap"]: x for x in base.values("snap").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True))}
        if True not in g or False not in g:
            return {"texto": f"En {nombre} no hay días SNAP y no SNAP para comparar."}
        s, n = g[True], g[False]
        ps, pn = s["t"] / s["d"], n["t"] / n["d"]
        total = s["t"] + n["t"]
        dias_pct = 100 * s["d"] / (s["d"] + n["d"])
        texto = (f"En {nombre} ({A._rango(desde, hasta)}), {desc} vendió unas {R.fmt1(ps)} unidades por día en días SNAP y {R.fmt1(pn)} en días sin SNAP: "
                 f"en días SNAP se vende un {A._pct(ps, pn)}. Los días SNAP son el {f'{dias_pct:.0f}'} % de los días y concentran el {f'{100 * s['t'] / total:.1f}'.replace('.', ',')} % de las unidades vendidas.")
        if not ctx.get("tienda"):
            texto += " (Cada serie usa el calendario SNAP de su estado: CA, TX o WI.)"
        return {"texto": texto, "columnas": ["Tipo de día", "Días", "Unidades por día"], "filas": [["SNAP", R.fmt(s["d"]), R.fmt1(ps)], ["Sin SNAP", R.fmt(n["d"]), R.fmt1(pn)]]}
    return A.snap(ctx, info)


def fin_semana2(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    lim = A._limites()
    seguimiento_rank = bool(ctx.get("rank_fs")) and len(t.split()) <= 11
    if (ents.get("buscar") or re.search(r"\bproductos?\b", t) or seguimiento_rank) and (seguimiento_rank or re.search(r"\bmas\b|\bmenos\b|mejor|peor", t)) and not re.search(r"solo|casi solo|unicamente|principalmente|sobre todo|porcentaje", t):
        per = A._periodo(ctx, info, lim)
        desde, hasta, nombre, _, _ = per or (lim["p"], lim["m"], "todo el histórico", None, None)
        g = (VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).annotate(dsem=ExtractWeekDay("fecha")).filter(dsem__in=(1, 7))
             .values("serie_id").annotate(tot=Sum("unidades"), d=Count("fecha", distinct=True)))
        series = {s.id: s for s in qs}
        asc = ents.get("orden") == "asc"
        por_sede = bool(re.search(r"todas las (?:sedes|tiendas)|cada (?:sede|tienda)|por (?:sede|tienda)|las tres", t)) or ("tienda" in info["reset"])
        if por_sede:                                                  # el producto líder de cada tienda (sea el mismo o distinto)
            mejores = {}
            for x in sorted(g, key=lambda x: x["tot"] / x["d"], reverse=not asc):
                tienda = series[x["serie_id"]].tienda.codigo
                mejores.setdefault(tienda, (series[x["serie_id"]].item_id, x["tot"] / x["d"]))
            filas = [[item, tienda, R.fmt1(v)] for tienda, (item, v) in sorted(mejores.items())]
            mismo = len({f[0] for f in filas}) == 1
            return {"texto": f"En {nombre}, el producto de {desc} que {'menos' if asc else 'más'} vende por día en fin de semana (sábado y domingo), en cada tienda: " + (f"es el mismo ({filas[0][0]}) en todas." if mismo else "es distinto según la tienda."),
                    "columnas": ["Producto", "Tienda", "Unidades por día en fin de semana"], "filas": filas, "_ctx": {"rank_fs": True}}
        puntos = sorted(((x["tot"] / x["d"], x["serie_id"]) for x in g if x["d"]), reverse=not asc)[:_nfilas(info, defecto=5 if ents.get("buscar", {}).get("plural") else 1)]
        filas = [[series[sid].item_id, series[sid].tienda.codigo, R.fmt1(v)] for v, sid in puntos]
        if len(filas) == 1:
            return {"texto": f"En {nombre}, el producto de {desc} que {'menos' if asc else 'más'} vende por día en fin de semana (sábado y domingo) es {filas[0][0]} en {filas[0][1]}, con {filas[0][2]} unidades por día en promedio.",
                    "columnas": ["Producto", "Tienda", "Unidades por día en fin de semana"], "filas": filas, "_ctx": {"rank_fs": True}}
        return {"texto": f"En {nombre}, los {len(filas)} productos de {desc} que {'menos' if asc else 'más'} venden por día en fin de semana:", "columnas": ["Producto", "Tienda", "Unidades por día en fin de semana"], "filas": filas, "_ctx": {"rank_fs": True}}
    if re.search(r"productos? .*(?:solo|casi solo|unicamente|principalmente|sobre todo)|que productos|cuales productos", t):   # ranking de dependencia del fin de semana
        per = A._periodo(ctx, info, lim, defecto="anio")
        desde, hasta, nombre, _, _ = per
        g = (VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).annotate(dsem=ExtractWeekDay("fecha")).values("serie_id")
             .annotate(f=Sum("unidades", filter=Q(dsem__in=(1, 7))), tot=Sum("unidades")))
        series = {s.id: s for s in qs}
        puntos = sorted(((x["f"] / x["tot"], x["serie_id"], x["tot"]) for x in g if x["tot"] and x["tot"] >= 50 and x["f"] is not None), reverse=True)[:_nfilas(info)]
        filas = [[series[sid].item_id, series[sid].tienda.codigo, f"{100 * p:.0f} %", R.fmt(tot)] for p, sid, tot in puntos]
        return {"texto": f"En {nombre}, los productos de {desc} con mayor parte de sus ventas en fin de semana (si se vendiera parejo, sábado y domingo serían el 29 %). Ninguno vende «solo» los fines de semana si el porcentaje es menor a 100 %:",
                "columnas": ["Producto", "Tienda", "% de sus ventas en fin de semana", "Unidades"], "filas": filas}
    if re.search(r"cual de las|cada tienda|por tienda|que tienda|cual tienda|las tres", t):
        per = A._periodo(ctx, info, lim)
        desde, hasta, nombre, _, _ = per or (lim["p"], lim["m"], "todo el histórico", None, None)
        g = (VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).annotate(dsem=ExtractWeekDay("fecha")).values("serie__tienda__codigo")
             .annotate(f=Sum("unidades", filter=Q(dsem__in=(1, 7))), df=Count("fecha", filter=Q(dsem__in=(1, 7)), distinct=True), w=Sum("unidades", filter=~Q(dsem__in=(1, 7))), dw=Count("fecha", filter=~Q(dsem__in=(1, 7)), distinct=True)))
        filas_t = sorted(([x["serie__tienda__codigo"], x["f"] / x["df"], x["w"] / x["dw"]] for x in g if x["df"] and x["dw"]), key=lambda f: -f[1])
        return {"texto": f"En {nombre}, la tienda que más vende por día en fin de semana es {filas_t[0][0]} ({R.fmt1(filas_t[0][1])} unidades por día; entre semana {R.fmt1(filas_t[0][2])}).",
                "columnas": ["Tienda", "Fin de semana (por día)", "Entre semana (por día)", "Diferencia"], "filas": [[a, R.fmt1(b), R.fmt1(c), f"{100 * (b / c - 1):+.0f} %"] for a, b, c in filas_t]}
    if re.search(r"fin de semana largo|puente|festivo|viene|necesito|cubrir|cubrirlo|pedir|conviene|stock|inventario", t) and not ents.get("pasado"):
        corrida = R._activa("lightgbm")
        if not corrida:
            return R._sin_predicciones()
        filas_d = list(Prediccion.objects.filter(corrida=corrida, serie__in=qs).annotate(dsem=ExtractWeekDay("fecha")).filter(dsem__in=(1, 7)).values("fecha")
                       .annotate(p50=Sum("p50"), p90=Sum("p90")).order_by("fecha"))
        if not filas_d:
            return {"texto": "No tengo proyección diaria para ese periodo."}
        sab_dom = filas_d[:2]
        t50 = sum(x["p50"] for x in filas_d[:2])
        t90 = sum(x["p90"] for x in filas_d[:2])
        largo = bool(re.search(r"largo|puente|festivo", t))
        fines = filas_d[:3] if largo else filas_d[:2]
        extra = ""
        if largo:
            extra = " Para un fin de semana largo (3 días) suma el lunes de la tabla de proyecciones; el aplicativo no sabe cuál es el festivo, pero los eventos del calendario están en las fechas que preguntes."
        return {"texto": f"Para el primer fin de semana pronosticado ({A._f(sab_dom[0]['fecha'])} y {A._f(sab_dom[-1]['fecha'])}), {desc} vendería unas {R.fmt(t50)} unidades (suma de medianas). "
                         f"Para cubrirlo con holgura, la suma de los P90 diarios es {R.fmt(t90)} (tope exigente; la suma de P90 sobreestima el total).{extra} "
                         "Recuerda descontar el inventario que ya tengas.",
                "columnas": ["Día", "Mediana", "P90"], "filas": [[A._f(x["fecha"]), R.fmt(x["p50"]), R.fmt(x["p90"])] for x in fines]}
    return A.fin_semana(ctx, info)


# --------------------------------------------------------------------------------------------- precios
def precio2(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    if len(ids) == 1 and re.search(r"venta|vend|baja(?:n)? las ventas|suben las ventas|afect|elasticidad", t) and re.search(r"precio", t):
        g = list(VentaDiaria.objects.filter(serie_id=ids[0], precio__isnull=False).values("precio").annotate(d=Count("id"), m=Avg("unidades")).filter(d__gte=14).order_by("precio"))
        if len(g) < 2:
            return {"texto": f"{desc} casi no cambió de precio, así que no hay con qué comparar sus ventas."}
        bajo, alto = g[0], g[-1]
        filas = [[f"${float(x['precio']):.2f}", R.fmt(x["d"]), R.fmt1(x["m"])] for x in g]
        texto = (f"{desc} se vendió a {len(g)} precios distintos. Con el precio más bajo (${float(bajo['precio']):.2f}) vendió unas {R.fmt1(bajo['m'])} unidades por día y con el más alto "
                 f"(${float(alto['precio']):.2f}) unas {R.fmt1(alto['m'])}: {'sí' if bajo['m'] > alto['m'] else 'no'} se vendió más cuando el precio estuvo más bajo. "
                 "Es solo una comparación de promedios; no prueba que el precio sea la causa (también influyen la temporada y los eventos).")
        return {"texto": texto, "columnas": ["Precio", "Días", "Unidades por día"], "filas": filas[:10]}
    if len(ids) > 1 and re.search(r"subio|subieron|bajo|bajaron|cambia|cambian|cambio|estable|seguido|frecuen|promocion|rebaja|oferta|aumento|variacion", t):
        ult = PrecioSemanal.objects.aggregate(m=Max("wm_yr_wk"))["m"]
        hist = {}
        for sid, w, p in PrecioSemanal.objects.filter(serie_id__in=ids).order_by("serie_id", "wm_yr_wk").values_list("serie_id", "wm_yr_wk", "precio"):
            hist.setdefault(sid, []).append((w, float(p)))
        series = {s.id: s for s in qs}
        if re.search(r"estable|seguido|frecuen|cambia(?:n)? (?:mas|menos|de precio)|cuantas veces", t):
            cambios = {sid: sum(1 for (_, a), (_, b) in zip(h, h[1:]) if a != b) for sid, h in hist.items()}
            anios = {sid: max(len(h) / 52, 1) for sid, h in hist.items()}
            promedio = sum(cambios.values()) / max(len(cambios), 1)
            estable = bool(re.search(r"estable|menos", t)) and not re.search(r"mas cambia", t)
            orden = sorted(cambios, key=lambda s: cambios[s], reverse=not estable)[:_nfilas(info)]
            filas = [[series[s].item_id, series[s].tienda.codigo, str(cambios[s]), f"{cambios[s] / anios[s]:.1f}".replace(".", ",")] for s in orden]
            return {"texto": f"En {desc}, cada producto cambió de precio en promedio {f'{promedio:.1f}'.replace('.', ',')} veces en todo el histórico. "
                             f"{'Los de precio más estable' if estable else 'Los que más cambian de precio'}:",
                    "columnas": ["Producto", "Tienda", "Cambios de precio", "Por año"], "filas": filas}
        if re.search(r"promocion|rebaja|oferta|bajo|bajaron", t):
            filas_b = []
            for sid, h in hist.items():
                recientes = [p for w, p in h if w > ult - 12]
                previos = [p for w, p in h if ult - 52 < w <= ult - 12]
                if recientes and previos and min(recientes) < 0.95 * max(previos[-8:] or previos):
                    ref = max(previos[-8:] or previos)
                    filas_b.append((100 * (min(recientes) - ref) / ref, sid, ref, min(recientes)))
            filas_b.sort()
            if not filas_b:
                return {"texto": f"En {desc} no veo rebajas de precio de más de 5 % en las últimas 12 semanas."}
            filas = [[series[sid].item_id, series[sid].tienda.codigo, f"${ref:.2f}", f"${nuevo:.2f}", f"{p:.0f} %"] for p, sid, ref, nuevo in filas_b[:_nfilas(info)]]
            return {"texto": f"En {desc}, {len(filas_b)} productos tuvieron una rebaja de precio de más de 5 % en las últimas 12 semanas. Las mayores:",
                    "columnas": ["Producto", "Tienda", "Precio anterior", "Precio más bajo reciente", "Cambio"], "filas": filas}
        puntos = []
        for sid, h in hist.items():
            antes = [p for w, p in h if w <= ult - 52]
            if antes:
                puntos.append((100 * (h[-1][1] - antes[-1]) / antes[-1], sid, antes[-1], h[-1][1]))
        baja = bool(re.search(r"bajo|bajaron|cayo", t))
        puntos.sort(reverse=not baja)
        filas = [[series[sid].item_id, series[sid].tienda.codigo, f"${a:.2f}", f"${b:.2f}", f"{p:+.0f} %"] for p, sid, a, b in puntos[:_nfilas(info)]]
        return {"texto": f"Los productos de {desc} cuyo precio más {'bajó' if baja else 'subió'} en el último año (precio de hace 52 semanas frente al actual):",
                "columnas": ["Producto", "Tienda", "Hace un año", "Actual", "Cambio"], "filas": filas}
    return A.precio(ctx, info)


# --------------------------------------------------------------------------------------------- volatilidad, estacionalidad, ABC, parecidos
def irregular(ctx, info):
    t = info["normalizado"]
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    lim = A._limites()
    desde, hasta, nombre, _, _ = A._periodo(ctx, info, lim, defecto="anio")
    g = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values("serie_id").annotate(m=Avg("unidades"), s=StdDev("unidades"), ceros=Count("id", filter=Q(unidades=0)), d=Count("id"))
    estable = bool(re.search(r"\bestables?\b|\bconstantes?\b|\bregulares?\b|menos (?:irregular|volatil|variab)", t))
    series = {s.id: s for s in qs}
    puntos = sorted(((x["s"] / x["m"], x["serie_id"], x) for x in g if x["m"] and x["m"] >= 1 and x["s"] is not None), reverse=not estable)[: _nfilas(info)]
    if not puntos:
        return {"texto": "No hay productos con ventas suficientes para medir su irregularidad."}
    filas = [[series[sid].item_id, series[sid].tienda.codigo, R.fmt1(x["m"]), f"{cv:.2f}".replace(".", ","), f"{100 * x['ceros'] / x['d']:.0f} %"] for cv, sid, x in puntos]
    return {"texto": f"En {nombre} ({A._rango(desde, hasta)}), los productos de {desc} con ventas {'más estables' if estable else 'más irregulares'} (coeficiente de variación = desviación estándar ÷ promedio diario; "
                     f"mientras mayor, más picos y días sin ventas), entre los que venden al menos 1 unidad por día en promedio:",
            "columnas": ["Producto", "Tienda", "Promedio por día", "Coef. de variación", "Días en cero"], "filas": filas}


def estacional(ctx, info):
    t = info["normalizado"]
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    lim = A._limites()
    base = VentaDiaria.objects.filter(serie__in=qs, fecha__lt=date(2016, 1, 1))     # años completos (2011-2015), para no sesgar por 2011 y 2016 incompletos
    series = {s.id: s for s in qs}
    if re.search(r"verano|invierno", t):
        g = base.values("serie_id").annotate(v=Avg("unidades", filter=Q(fecha__month__in=(6, 7, 8))), i=Avg("unidades", filter=Q(fecha__month__in=(12, 1, 2))))
        pts = [(x["v"] / x["i"], x["serie_id"], x["v"], x["i"]) for x in g if x["v"] is not None and x["i"] and x["i"] >= 1]
        invierno = bool(re.search(r"mejor en invierno|mas en invierno|invierno que en verano", t))
        pts.sort(reverse=not invierno)
        filas = [[series[sid].item_id, series[sid].tienda.codigo, R.fmt1(v), R.fmt1(i), f"{100 * (r - 1):+.0f} %"] for r, sid, v, i in pts[:_nfilas(info)]]
        tv = base.filter(fecha__month__in=(6, 7, 8)).aggregate(a=Sum("unidades"), d=Count("fecha", distinct=True))
        ti = base.filter(fecha__month__in=(12, 1, 2)).aggregate(a=Sum("unidades"), d=Count("fecha", distinct=True))
        total = (f" En total, {desc} vende {A._pct((tv['a'] / tv['d']), (ti['a'] / ti['d']))} en verano que en invierno (por día)." if tv["d"] and ti["d"] else "")
        return {"texto": f"Productos de {desc} que se venden {'mejor en invierno' if invierno else 'mejor en verano'} (junio-agosto frente a diciembre-febrero, 2011-2015, solo los que venden al menos 1 unidad por día en invierno).{total}",
                "columnas": ["Producto", "Tienda", "Por día en verano", "Por día en invierno", "Diferencia"], "filas": filas}
    g = base.values("serie_id", "fecha__month").annotate(a=Avg("unidades"))
    por = {}
    for x in g:
        por.setdefault(x["serie_id"], {})[x["fecha__month"]] = x["a"]
    pts = []
    for sid, meses in por.items():
        if len(meses) == 12:
            media = sum(meses.values()) / 12
            if media >= 1:
                pico = max(meses, key=meses.get)
                pts.append((meses[pico] / media, sid, pico, media))
    pts.sort(reverse=True)
    filas = [[series[sid].item_id, series[sid].tienda.codigo, R.MESES_TODOS[pico].capitalize(), f"{r:.2f}".replace(".", ",") + "×", R.fmt1(media)] for r, sid, pico, media in pts[:_nfilas(info)]]
    return {"texto": f"Productos de {desc} con ventas más estacionales por mes del año (2011-2015): el mes pico vende tantas veces el promedio mensual como indica la columna «Pico». "
                     "Ninguno vende solo en una época del año, pero estos concentran más en un mes:",
            "columnas": ["Producto", "Tienda", "Mes pico", "Pico", "Promedio por día"], "filas": filas}


def abc(ctx, info):
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    lim = A._limites()
    desde, hasta, nombre, _, _ = A._periodo(ctx, info, lim)
    g = sorted((x["t"] for x in VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values("serie_id").annotate(t=Sum("unidades"))), reverse=True)
    total = sum(g)
    if not total:
        return {"texto": "No hay ventas en ese periodo."}
    acum, n80, n95 = 0, None, None
    for i, v in enumerate(g, 1):
        acum += v
        if n80 is None and acum >= 0.8 * total:
            n80 = i
        if n95 is None and acum >= 0.95 * total:
            n95 = i
    nt = len(g)
    return {"texto": f"En {nombre} ({A._rango(desde, hasta)}), el 80 % de las unidades vendidas de {desc} lo concentran {n80} de {nt} productos ({100 * n80 / nt:.0f} %). "
                     f"Clasificación ABC: A = {n80} productos (80 % de las ventas), B = {n95 - n80} (siguiente 15 %), C = {nt - n95} (último 5 %).",
            "columnas": ["Clase", "Productos", "Participación de las ventas"], "filas": [["A", str(n80), "80 %"], ["B", str(n95 - n80), "15 %"], ["C", str(nt - n95), "5 %"]]}


def parecidos(ctx, info):
    prod = ctx.get("producto")
    if not prod:
        return {"texto": "¿Parecidos a cuál producto? Dime su código, por ejemplo «productos parecidos a FOODS_2_398»."}
    s0 = Serie.objects.filter(item_id=prod).first()
    if not s0:
        return {"texto": f"No encontré el producto {prod} en los datos."}
    promedios = {x["serie_id"]: x["m"] for x in VentaDiaria.objects.filter(serie__departamento=s0.departamento).values("serie_id").annotate(m=Avg("unidades"))}
    obj = promedios.get(Serie.objects.filter(item_id=prod).first().id, 0)
    series = {s.id: s for s in Serie.objects.filter(departamento=s0.departamento).select_related("tienda")}
    precios, _ = A._precio_actual(list(series))
    cand = sorted(((abs(m - obj), sid) for sid, m in promedios.items() if series[sid].item_id != prod))[:5]
    filas = [[series[sid].item_id, series[sid].tienda.codigo, R.fmt1(promedios[sid]), f"${precios.get(sid, 0):.2f}"] for _, sid in cand]
    return {"texto": f"El aplicativo no mide «similitud» entre productos; como aproximación, estos son los del mismo departamento ({s0.departamento.codigo}) con un promedio diario de ventas más cercano a {prod} ({R.fmt1(obj)} por día):",
            "columnas": ["Producto", "Tienda", "Promedio por día", "Precio actual"], "filas": filas}


def top_por_grupo(ctx, info):
    t = info["normalizado"]
    clave = "categoria" if re.search(r"categoria", t) else "tienda" if re.search(r"tienda|sede", t) else "departamento"
    n = _nfilas(info, defecto=3, tope=10)
    lim = A._limites()
    desde, hasta, nombre, _, _ = A._periodo(ctx, info, lim)
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    series = {s.id: s for s in qs}
    g = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values("serie_id").annotate(t=Sum("unidades"))
    por = {}
    for x in g:
        s = series[x["serie_id"]]
        k = {"categoria": s.departamento.categoria.codigo, "tienda": s.tienda.codigo, "departamento": s.departamento.codigo}[clave]
        por.setdefault(k, []).append((x["t"], s))
    filas = []
    for k in sorted(por):
        for tot, s in sorted(por[k], key=lambda p: -p[0])[:n]:
            filas.append([k, s.item_id, s.tienda.codigo, R.fmt(tot)])
    return {"texto": f"En {nombre} ({A._rango(desde, hasta)}), los {n} productos más vendidos de cada {clave if clave != 'categoria' else 'categoría'}:", "columnas": [clave.capitalize() if clave != "categoria" else "Categoría", "Producto", "Tienda", "Unidades"], "filas": filas}


# --------------------------------------------------------------------------------------------- inventario y proyección
def cobertura2(ctx, info):
    t = info["normalizado"]
    ents = info["entidades"]
    agrupar = ents.get("agrupar") if ents.get("agrupar") in ("tienda", "categoria") else ("tienda" if re.search(r"cada tienda|por tienda|las tiendas", t) else "categoria" if re.search(r"cada categoria|por categoria", t) else None)
    if agrupar and not ctx.get(agrupar):
        qs, desc, error = A._alcance(ctx)
        if error:
            return {"texto": error}
        ids = list(qs.values_list("id", flat=True))
        agg, dia = A._demanda_diaria_mediana(ids)
        if not agg:
            return R._sin_predicciones()
        inv = R._inventarios(ids)
        grupos = {}
        for s in qs:
            k = s.tienda.codigo if agrupar == "tienda" else s.departamento.categoria.codigo
            if s.id in inv and dia.get(s.id):
                a, b = grupos.get(k, (0, 0))
                grupos[k] = (a + inv[s.id], b + dia[s.id])
        filas = [[k, R.fmt(a), R.fmt1(b), R.fmt1(a / b)] for k, (a, b) in sorted(grupos.items())]
        return {"texto": "Días de inventario por " + ("tienda" if agrupar == "tienda" else "categoría") + " (inventario registrado ÷ demanda diaria mediana proyectada)." +
                         (" Ojo: hay inventarios simulados (de demostración), no son datos reales." if InventarioActual.objects.filter(simulado=True).exists() else ""),
                "columnas": [agrupar.capitalize() if agrupar != "categoria" else "Categoría", "Inventario", "Demanda diaria", "Días de cobertura"], "filas": filas}
    return A.cobertura(ctx, info)


def real_vs_proyeccion(ctx, info):
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    agg = R._activa("lgbm_agregado")
    if not agg:
        return R._sin_predicciones()
    ids = list(qs.values_list("id", flat=True))
    lim = A._limites()
    fin = lim["m"]
    base = VentaDiaria.objects.filter(serie_id__in=ids)
    r1 = base.filter(fecha__range=(fin - timedelta(days=27), fin)).aggregate(t=Sum("unidades"))["t"] or 0
    r0 = base.filter(fecha__range=(fin - timedelta(days=55), fin - timedelta(days=28))).aggregate(t=Sum("unidades"))["t"] or 0
    proy = R._suma_agregada(agg, ids, "28d", 0.5)
    return {"texto": f"{desc[0].upper() + desc[1:]} vendió {R.fmt(r1)} unidades en los últimos 28 días ({A._pct(r1, r0)} que los 28 anteriores, {R.fmt(r0)}). La proyección mediana para los próximos 28 días es de {R.fmt(proy)} unidades "
                     f"({A._pct(proy, r1)} que lo vendido en los últimos 28 días). Para saber qué tan bien acertó el modelo en el pasado (no tengo guardada la proyección que hizo antes frente a lo real) revisa las métricas de la pestaña Modelos.",
            "enlace": {"texto": "Ir a Modelos", "url": R.reverse("modelos")}}


def incertidumbre_semanas(ctx, info):
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    agg = R._activa("lgbm_agregado")
    if not agg:
        return R._sin_predicciones()
    ids = list(qs.values_list("id", flat=True))
    filas, rel = [], []
    for n in (1, 2, 3, 4):
        p50 = R._suma_agregada(agg, ids, f"sem{n}", 0.5)
        p90 = R._suma_agregada(agg, ids, f"sem{n}", 0.9)
        rel.append(p90 / p50 - 1 if p50 else 0)
        filas.append([f"Semana {n}", R.fmt(p50), R.fmt(p90), f"{100 * rel[-1]:.0f} %"])
    mejor = min(range(4), key=lambda i: rel[i]) + 1
    return {"texto": f"Para {desc}, la semana con la proyección relativamente más segura (menor distancia entre la mediana y el P90) es la {mejor}. La columna final es cuánto más que la mediana puede llegar a pasar la demanda con 90 % de probabilidad.",
            "columnas": ["Semana", "Mediana", "P90 (90 % de servicio)", "Margen sobre la mediana"], "filas": filas}


def cuando_pedir(ctx, info):
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    ids = list(qs.values_list("id", flat=True))
    agg, dia = A._demanda_diaria_mediana(ids)
    inv = R._inventarios(ids)
    urgentes = sum(1 for s in ids if s in inv and dia.get(s) and inv[s] / dia[s] < 7)
    aviso = f" Con el inventario registrado, {urgentes} de {len(ids)} productos de {desc} tienen menos de 7 días de cobertura: esos son los primeros en pedir." if agg and inv else ""
    return {"texto": "El pedido sugerido se calcula al inicio del periodo: con la política de 28 días conviene reponer ahora (el stock objetivo cubre hasta el 19/06/2016) y con la semanal, cada semana. "
                     "Para decidir el día exacto hace falta el plazo de entrega de tu proveedor, que el aplicativo no tiene: pide con esa anticipación antes de que el inventario llegue a cero." + aviso,
            "enlace": R._enlace("reposicion", "Ir a Reposición")}


def por_que(ctx, info):
    pasado = ctx.get("pasado") or {}
    if not pasado.get("fecha"):
        return {"texto": "No tengo la causa de los cambios en las ventas (el aplicativo solo guarda cifras). Dime una fecha concreta y te muestro qué ocurría ese día en el calendario: día de la semana, evento y días SNAP."}
    d = date.fromisoformat(pasado["fecha"])
    c = Calendario.objects.filter(fecha=d).first()
    nombre_dia = R.DIAS_SEMANA[(d.isoweekday() % 7) + 1]
    partes = [f"el {A._f(d)} fue {nombre_dia}"]
    if c and c.evento:
        partes.append(f"el calendario marca «{c.evento}»")
        if c.evento == "Christmas":
            partes.append("las tiendas suelen estar cerradas ese día, por eso aparece con cero ventas")
    if c and (c.snap_ca or c.snap_tx or c.snap_wi):
        partes.append("había ayuda SNAP en al menos un estado")
    return {"texto": "No guardo causas, solo cifras; esto es lo que dice el calendario: " + "; ".join(partes) + "."}


def umbral2(ctx, info):
    t = info["normalizado"]
    if not re.search(r"cuantos dias", t):
        return A.umbral(ctx, info)
    m = re.search(r"(mas|mayor|superan|encima|menos|menor|debajo) de (\d[\d.]*)", t)
    if not m:
        return {"texto": "¿Con qué cifra quieres comparar? Por ejemplo: «¿cuántos días se vendieron más de 5.000 unidades?»."}
    n = float(m[2].replace(".", ""))
    mayor = m[1] in ("mas", "mayor", "superan", "encima")
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    lim = A._limites()
    desde, hasta, nombre, _, _ = A._periodo(ctx, info, lim)
    diarios = [x["t"] for x in VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values("fecha").annotate(t=Sum("unidades"))]
    cuantos = sum(1 for v in diarios if (v > n if mayor else v < n))
    maxi = max(diarios) if diarios else 0
    return {"texto": f"En {nombre} ({A._rango(desde, hasta)}), {desc} vendió {'más' if mayor else 'menos'} de {R.fmt(n)} unidades en {R.fmt(cuantos)} de {R.fmt(len(diarios))} días (el máximo en un día fue {R.fmt(maxi)})."}


def sin_ventas2(ctx, info):
    ents = info["entidades"]
    t = info["normalizado"]
    agrupar = ents.get("agrupar")
    if agrupar in CAMPOS and not ctx.get(agrupar):
        qs, desc, error = A._alcance(ctx)
        if error:
            return {"texto": error}
        lim = A._limites()
        per = A._periodo(ctx, info, lim, defecto="mes")
        desde, hasta, nombre, _, _ = per
        g = VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).values(CAMPOS[agrupar]).annotate(z=Count("id", filter=Q(unidades=0)), n=Count("id"))
        filas = sorted(([x[CAMPOS[agrupar]], str(x["z"]), str(x["n"]), f"{100 * x['z'] / x['n']:.0f} %"] for x in g if x["n"]), key=lambda f: -int(f[1]))
        return {"texto": f"En {nombre} ({A._rango(desde, hasta)}), {filas[0][0]} tuvo más productos con ventas en cero ({filas[0][1]} de {filas[0][2]} registros día-producto).",
                "columnas": [agrupar.capitalize(), "Registros en cero", "Registros", "% en cero"], "filas": filas}
    return A.sin_ventas(ctx, info)


def estacionalidad(ctx, info):
    """Perfil semanal (por día de la semana) y anual (por mes) de las ventas de la selección."""
    from django.db.models.functions import ExtractMonth
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    base = VentaDiaria.objects.filter(serie__in=qs, fecha__lt=date(2016, 1, 1))
    sem = list(base.annotate(g=ExtractWeekDay("fecha")).values("g").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
    mes = list(base.annotate(g=ExtractMonth("fecha")).values("g").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
    ps = {x["g"]: x["t"] / x["d"] for x in sem}
    pm = {x["g"]: x["t"] / x["d"] for x in mes}
    ms, mm = sum(ps.values()) / len(ps), sum(pm.values()) / len(pm)
    alto_s, bajo_s = max(ps, key=ps.get), min(ps, key=ps.get)
    alto_m, bajo_m = max(pm, key=pm.get), min(pm, key=pm.get)
    filas = [[f"{R.DIAS_SEMANA[k].capitalize()}", f"{100 * (v / ms - 1):+.0f} %"] for k, v in sorted(ps.items(), key=lambda kv: -kv[1])]
    filas += [[f"{R.MESES_TODOS[k].capitalize()}", f"{100 * (v / mm - 1):+.0f} %"] for k, v in sorted(pm.items(), key=lambda kv: -kv[1])]
    return {"texto": f"Estacionalidad de {desc} (2011-2015, promedio por día frente a su media). Semanal: sí; se vende más el {R.DIAS_SEMANA[alto_s]} ({100 * (ps[alto_s] / ms - 1):+.0f} %) y menos el {R.DIAS_SEMANA[bajo_s]} ({100 * (ps[bajo_s] / ms - 1):+.0f} %). "
                     f"Anual: {'sí' if (pm[alto_m] / pm[bajo_m]) > 1.1 else 'leve'}; el mes más alto es {R.MESES_TODOS[alto_m]} ({100 * (pm[alto_m] / mm - 1):+.0f} %) y el más bajo {R.MESES_TODOS[bajo_m]} ({100 * (pm[bajo_m] / mm - 1):+.0f} %). "
                     "Los modelos de proyección ya incorporan estos patrones (día de la semana, mes y eventos).",
            "columnas": ["Día de la semana / mes", "Diferencia con el promedio"], "filas": filas}


DIAS_NOMBRE = {"domingo": 1, "lunes": 2, "martes": 3, "miercoles": 4, "jueves": 5, "viernes": 6, "sabado": 7}


def dias_comparar(ctx, info):
    t = info["normalizado"]
    elegidos = list(dict.fromkeys(DIAS_NOMBRE[m[1]] for m in re.finditer(r"\b(domingo|lunes|martes|miercoles|jueves|viernes|sabado)s?\b", t)))
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    lim = A._limites()
    per = A._periodo(ctx, info, lim)
    if per is None:
        return A.periodo_sin_datos(ctx, info)
    desde, hasta, nombre, _, _ = per
    g = list(VentaDiaria.objects.filter(serie__in=qs, fecha__range=(desde, hasta)).annotate(g=ExtractWeekDay("fecha")).values("g").annotate(t=Sum("unidades"), d=Count("fecha", distinct=True)))
    por = {x["g"]: x["t"] / x["d"] for x in g}
    orden = sorted((k for k in elegidos if k in por), key=lambda k: -por[k])
    if len(orden) < 2:
        return {"texto": "No tengo ventas de esos días en el periodo."}
    ka, kb = orden[0], orden[-1]
    filas = [[R.DIAS_SEMANA[k].capitalize(), R.fmt1(por[k])] for k in orden]
    return {"texto": f"En {nombre} ({A._rango(desde, hasta)}), {desc} vendió más los {R.DIAS_SEMANA[ka]} ({R.fmt1(por[ka])} unidades por día) que los {R.DIAS_SEMANA[kb]} ({R.fmt1(por[kb])}): "
                     f"un {A._pct(por[ka], por[kb]).split(' ')[0]} % más.",
            "columnas": ["Día", "Unidades por día"], "filas": filas}


def comparar_periodos(ctx, info):
    """«¿Y cómo se compara con marzo?»: compara el periodo de ahora con el del turno anterior."""
    lim = A._limites()
    ahora = A._periodo(ctx, info, lim)
    anterior = None
    pp = info.get("pasado_prev")
    if pp:
        try:
            if pp.get("fecha"):
                d = date.fromisoformat(pp["fecha"])
                anterior = (d, d, pp.get("etiqueta", "ese día"), None, None)
            else:
                anterior = R._periodo_pasado(pp, lim["p"], lim["m"])
        except Exception:
            anterior = None
    if not ahora or not anterior:
        return A.periodo_sin_datos(ctx, info)
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    base = VentaDiaria.objects.filter(serie__in=qs)
    (d1, h1, n1, _, _), (d0, h0, n0, _, _) = ahora, anterior
    v1 = base.filter(fecha__range=(d1, h1)).aggregate(t=Sum("unidades"))["t"] or 0
    v0 = base.filter(fecha__range=(d0, h0)).aggregate(t=Sum("unidades"))["t"] or 0
    dias1, dias0 = (h1 - d1).days + 1, (h0 - d0).days + 1
    texto = f"{desc[0].upper() + desc[1:]} vendió {R.fmt(v1)} unidades en {n1} frente a {R.fmt(v0)} en {n0}: {n1} fue {A._pct(v1, v0)}."
    if abs(dias1 - dias0) > 3:
        texto += f" Como los periodos no duran lo mismo, por día fueron {R.fmt1(v1 / dias1)} frente a {R.fmt1(v0 / dias0)}."
    return {"texto": texto, "_ctx": {"periodos_cmp": [[n0, d0.isoformat(), h0.isoformat()], [n1, d1.isoformat(), h1.isoformat()]]}}


def explica_dif(ctx, info):
    """¿Qué categoría, departamento o tienda explica la diferencia entre los dos periodos que se comparan?"""
    t = info["normalizado"]
    clave = "categoria" if re.search(r"categoria", t) else "tienda" if re.search(r"tienda|sede", t) else "departamento" if re.search(r"departamento", t) else "categoria"
    (n0, a0, b0), (n1, a1, b1) = [(n, date.fromisoformat(a), date.fromisoformat(b)) for n, a, b in ctx["periodos_cmp"][:2]]
    qs, desc, error = A._alcance({k: v for k, v in ctx.items() if k != clave})
    if error:
        return {"texto": error}
    campo = CAMPOS[clave]
    base = VentaDiaria.objects.filter(serie__in=qs)
    v0 = {x[campo]: x["t"] for x in base.filter(fecha__range=(a0, b0)).values(campo).annotate(t=Sum("unidades"))}
    v1 = {x[campo]: x["t"] for x in base.filter(fecha__range=(a1, b1)).values(campo).annotate(t=Sum("unidades"))}
    dif = {k: v1.get(k, 0) - v0.get(k, 0) for k in set(v0) | set(v1)}
    total = sum(dif.values())
    orden = sorted(dif, key=lambda k: -abs(dif[k]))
    filas = [[k, R.fmt(v0.get(k, 0)), R.fmt(v1.get(k, 0)), f"{dif[k]:+,}".replace(",", ".")] for k in orden]
    top = orden[0]
    return {"texto": f"La diferencia total entre {n0} y {n1} es de {total:+,} unidades".replace(",", ".") + f"; la {clave if clave != 'categoria' else 'categoría'} que más la explica es {top} ({dif[top]:+,} unidades).".replace(",", "."),
            "columnas": [clave.capitalize() if clave != "categoria" else "Categoría", n0, n1, "Diferencia"], "filas": filas, "_ctx": {clave: top}}


def dia_pico_futuro(ctx, info):
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    corrida = R._activa("lightgbm")
    if not corrida:
        return R._sin_predicciones()
    t = info["normalizado"]
    asc = bool(re.search(r"menor|menos|minima|bajo", t))
    g = list(Prediccion.objects.filter(corrida=corrida, serie__in=qs).values("fecha").annotate(p50=Sum("p50"), p90=Sum("p90")).order_by("p50" if asc else "-p50")[:5])
    if not g:
        return {"texto": "No tengo proyección diaria para esa selección."}
    filas = [[A._f(x["fecha"]), R.DIAS_SEMANA[(x["fecha"].isoweekday() % 7) + 1].capitalize(), R.fmt(x["p50"]), R.fmt(x["p90"])] for x in g]
    return {"texto": f"El día con {'menor' if asc else 'mayor'} demanda esperada de {desc} en los próximos 28 días es el {filas[0][0]} ({filas[0][1].lower()}), con unas {filas[0][2]} unidades (mediana; P90 {filas[0][3]}).",
            "columnas": ["Día", "Día de la semana", "Mediana", "P90"], "filas": filas, "_ctx": {"dia_ref": g[0]["fecha"].isoformat()}}


def dia_info(ctx, info):
    ref = ctx.get("dia_ref") or (ctx.get("pasado") or {}).get("fecha")
    if not ref:
        return {"texto": "¿De qué día hablas? Dime una fecha, por ejemplo «¿el 4 de julio de 2015 cae en algún evento?»."}
    d = date.fromisoformat(ref)
    c = Calendario.objects.filter(fecha=d).first()
    partes = [f"el {A._f(d)} es {R.DIAS_SEMANA[(d.isoweekday() % 7) + 1]}"]
    if c is not None and c.evento:
        partes.append(f"el calendario marca «{c.evento}» ({c.tipo_evento})")
    elif c is not None:
        partes.append("el calendario no marca ningún evento")
    snaps = [e for e, v in (("CA", c.snap_ca), ("TX", c.snap_tx), ("WI", c.snap_wi)) if c is not None and v]
    partes.append("hay ayuda SNAP en " + ", ".join(snaps) if snaps else "no hay ayuda SNAP en ningún estado")
    return {"texto": "Sobre ese día: " + "; ".join(partes) + "."}


def rango_dia(ctx, info):
    ref = ctx.get("dia_ref")
    corrida = R._activa("lightgbm")
    if not corrida:
        return R._sin_predicciones()
    qs, desc, error = A._alcance(ctx)
    if error:
        return {"texto": error}
    d = date.fromisoformat(ref)
    g = Prediccion.objects.filter(corrida=corrida, serie__in=qs, fecha=d).aggregate(a=Sum("p10"), b=Sum("p50"), c=Sum("p90"))
    if g["b"] is None:
        return {"texto": "No tengo proyección para ese día."}
    return {"texto": f"Para el {A._f(d)}, {desc} tendría: escenario pesimista (P10) {R.fmt(g['a'])}, lo más probable (P50) {R.fmt(g['b'])} y escenario optimista (P90) {R.fmt(g['c'])} unidades. "
                     "La suma de P10 o P90 de varias series es solo una referencia, porque no todas coinciden en el extremo el mismo día."}


def tiempo_entrenamiento(ctx, info):
    return {"texto": "En este equipo (CPU, sin GPU): LightGBM tarda cerca de 1 minuto (botón «Generar predicciones»); ETS y el modelo naive, segundos; y el TFT cerca de 1 hora (54 minutos medidos con 1.500 pasos de entrenamiento). "
                     "Por eso el TFT se lanza aparte desde la pestaña Modelos.",
            "enlace": {"texto": "Ir a Modelos", "url": R.reverse("modelos")}}


EXTRA = {"rango_dia": rango_dia, "comparar_periodos": comparar_periodos, "explica_dif": explica_dif, "dia_pico_futuro": dia_pico_futuro, "dia_info": dia_info, "tiempo_entrenamiento": tiempo_entrenamiento, "dias_comparar": dias_comparar, "estacionalidad": estacionalidad, "comparar": comparar, "tendencia": tendencia2, "snap": snap2, "fin_semana": fin_semana2, "precio": precio2, "irregular": irregular, "estacional": estacional, "abc": abc,
         "parecidos": parecidos, "top_por_grupo": top_por_grupo, "cobertura": cobertura2, "real_vs_proyeccion": real_vs_proyeccion, "incertidumbre_semanas": incertidumbre_semanas,
         "cuando_pedir": cuando_pedir, "por_que": por_que, "umbral": umbral2, "sin_ventas": sin_ventas2}
