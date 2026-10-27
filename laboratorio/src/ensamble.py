"""Conjunto (ensamble) de modelos: promedio de cuantiles de ETS y LightGBM (y, donde existe, también del TFT h64), con pesos distintos.
No entrena nada: usa las predicciones guardadas de las 6 ventanas. Reutiliza la calidad y la simulación de reposición de posproceso.py.
Uso: python src/ensamble.py   -> resultados_completa/ENSAMBLE.md, ensamble_calidad.csv, ensamble_reposicion.csv, ensamble_por_serie.csv
"""
import numpy as np, pandas as pd
import posproceso as P

RES = P.RES
H = P.H
PESOS = (0.0, 0.25, 0.5, 0.75, 1.0)                    # peso de LightGBM en el promedio ETS-LightGBM (0 = solo ETS, 1 = solo LightGBM)


def mezcla(partes, pesos):
    q = sum(w * p for w, p in zip(pesos, partes))
    return P.ordenar(q)


def por_serie(Y, q, esc):
    pins = [P.pin(Y, q[:, :, j], t) for j, t in enumerate(P.TAUS)]
    return np.mean([p.mean(axis=1) for p in pins], axis=0) / esc, np.abs(Y - q[:, :, 1]).mean(axis=1) / esc


def main():
    datos = P.cargar()
    ventanas = sorted(set(datos["ets"]) & set(datos["lightgbm"]))
    print("ventanas con ETS y LightGBM:", ventanas)
    cache = {o: P.datos_ventana(o) for o in ventanas}
    configs = {f"ETS+LGBM (peso LGBM {w:.2f})": (("ets", "lightgbm"), (1 - w, w)) for w in PESOS}
    h64 = datos.get("tft_h64", {})
    v3 = [o for o in ventanas if o in h64]
    calid, repo, serie = [], [], []
    for nombre, (mods, pes) in configs.items():
        for o in ventanas:
            Y, esc, _ = cache[o]
            q = mezcla([datos[m][o] for m in mods], pes)
            r = P.calidad(Y, q, esc); r.update(config=nombre, origen=o, grupo="ets_lgbm"); calid.append(r)
            ps, ms = por_serie(Y, q, esc)
            serie.append(pd.DataFrame({"config": nombre, "origen": o, "unique_id": P.IDS, "pinball_esc": ps, "mase": ms}))
            for k in P.K_LISTA:
                nivel = q[:, :, 1] + k * (q[:, :, 2] - q[:, :, 1])
                a, b = P.simular(Y, nivel)
                for pol, s in (("28d", a), ("semanal", b)):
                    s.update(config=nombre, origen=o, politica=pol, k=k); repo.append(s)
    # tres modelos con pesos iguales (solo ventanas donde existe el TFT h64)
    for o in v3:
        Y, esc, _ = cache[o]
        q = mezcla([datos["ets"][o], datos["lightgbm"][o], h64[o]], (1 / 3, 1 / 3, 1 / 3))
        r = P.calidad(Y, q, esc); r.update(config="ETS+LGBM+TFT (1/3 c/u)", origen=o, grupo="tres"); calid.append(r)
        for nom, qq in (("ETS+LGBM (0,5)", mezcla([datos["ets"][o], datos["lightgbm"][o]], (.5, .5))), ("LightGBM", datos["lightgbm"][o]), ("TFT h64", h64[o]), ("ETS", datos["ets"][o])):
            rr = P.calidad(Y, qq, esc); rr.update(config=nom + " [ventanas con TFT]", origen=o, grupo="tres"); calid.append(rr)
        for k in P.K_LISTA:
            for nom, qq in (("ETS+LGBM+TFT (1/3 c/u)", q), ("ETS+LGBM (0,5) [ventanas con TFT]", mezcla([datos["ets"][o], datos["lightgbm"][o]], (.5, .5))),
                            ("LightGBM [ventanas con TFT]", datos["lightgbm"][o]), ("ETS [ventanas con TFT]", datos["ets"][o]), ("TFT h64 [ventanas con TFT]", h64[o])):
                nivel = qq[:, :, 1] + k * (qq[:, :, 2] - qq[:, :, 1])
                a, b = P.simular(Y, nivel)
                for pol, s in (("28d", a), ("semanal", b)):
                    s.update(config=nom, origen=o, politica=pol, k=k); repo.append(s)
    C, I, S = pd.DataFrame(calid), pd.DataFrame(repo), pd.concat(serie)
    C.to_csv(RES / "ensamble_calidad_detalle.csv", index=False); I.to_csv(RES / "ensamble_reposicion_detalle.csv", index=False); S.to_csv(RES / "ensamble_por_serie.csv", index=False)

    def agr(g):
        n = g.n.sum()
        return pd.Series({"ventanas": g.origen.nunique(), "MASE": g.mase_sum.sum() / n, "pinball_esc": g.pinball_esc_sum.sum() / n, "WQL": g.wql_num.sum() / g.suma_y.sum(),
                          "cob_P90": np.average(g.cov_p90, weights=g.n), "cob_80": np.average(g.cov_80, weights=g.n), "ancho_80": np.average(g.ancho, weights=g.n)})
    T1 = C[C.grupo == "ets_lgbm"].groupby("config").apply(agr, include_groups=False).round(4)
    T3 = C[C.grupo == "tres"].groupby("config").apply(agr, include_groups=False).round(4)

    # ¿La diferencia entre el mejor mezclado y LightGBM es real? Diferencia por serie-ventana y remuestreo (bootstrap) de las series.
    rng = np.random.default_rng(1)
    a = S[S.config == "ETS+LGBM (peso LGBM 0.50)"].set_index(["origen", "unique_id"]).pinball_esc
    b = S[S.config == "ETS+LGBM (peso LGBM 1.00)"].set_index(["origen", "unique_id"]).pinball_esc
    d = (a - b).groupby(level="unique_id").mean().to_numpy()                       # por serie, promediando ventanas (las ventanas de una serie no son independientes)
    boots = [rng.choice(d, len(d)).mean() for _ in range(4000)]
    ic = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
    gan = float((d < 0).mean())
    am = S[S.config == "ETS+LGBM (peso LGBM 0.50)"].set_index(["origen", "unique_id"]).mase
    bm = S[S.config == "ETS+LGBM (peso LGBM 1.00)"].set_index(["origen", "unique_id"]).mase
    dm = (am - bm).groupby(level="unique_id").mean().to_numpy()
    bm_boots = [rng.choice(dm, len(dm)).mean() for _ in range(4000)]
    icm = (float(np.percentile(bm_boots, 2.5)), float(np.percentile(bm_boots, 97.5)))

    def agri(g):
        return pd.Series({"tasa_servicio": g.vendidas.sum() / g.demanda.sum(), "faltante_rel": g.faltante.sum() / g.demanda.sum(), "sobrante_rel": g.sobrante.sum() / g.demanda.sum(),
                          "pct_sin_quiebre": g.sin_quiebre.sum() / g.n.sum()})
    I1 = I[~I.config.str.contains(r"\[|ETS\+LGBM\+TFT")]
    R1 = I1.groupby(["politica", "config", "k"]).apply(agri, include_groups=False).round(3)
    R1.to_csv(RES / "ensamble_reposicion.csv")
    I3 = I[I.config.str.contains(r"\[|ETS\+LGBM\+TFT")]
    R3 = I3.groupby(["politica", "config", "k"]).apply(agri, include_groups=False).round(3)

    # Comparación justa a igual servicio: sobrante necesario para llegar a ~90 % de tasa de servicio (interpolando en k)
    def sobrante_a(servicio, g):
        g = g.sort_values("k")
        if g.tasa_servicio.max() < servicio:
            return np.nan
        return float(np.interp(servicio, g.tasa_servicio.to_numpy(), g.sobrante_rel.to_numpy()))
    filas = []
    for pol in ("28d", "semanal"):
        for cfg in R1.loc[pol].index.get_level_values(0).unique():
            g = R1.loc[(pol, cfg)].reset_index()
            filas.append({"politica": pol, "config": cfg, "sobrante_para_95": sobrante_a(.95, g), "sobrante_para_97": sobrante_a(.97, g), "sobrante_para_98": sobrante_a(.98, g)})
    Q = pd.DataFrame(filas).round(3)
    Q3 = []
    for pol in ("28d", "semanal"):
        for cfg in R3.loc[pol].index.get_level_values(0).unique():
            g = R3.loc[(pol, cfg)].reset_index()
            Q3.append({"politica": pol, "config": cfg, "sobrante_para_95": sobrante_a(.95, g), "sobrante_para_97": sobrante_a(.97, g), "sobrante_para_98": sobrante_a(.98, g)})
    Q3 = pd.DataFrame(Q3).round(3)

    def md(df): return "```\n" + df.to_string() + "\n```\n\n"
    with open(RES / "ENSAMBLE.md", "w", encoding="utf-8") as f:
        f.write("# Conjunto ETS + LightGBM (promedio de cuantiles)\n\n")
        f.write(f"Se promedian, cuantil a cuantil (P10, P50, P90), las predicciones guardadas de ETS y LightGBM con distintos pesos y se reordenan los cuantiles. "
                f"No se entrena nada nuevo. Ventanas de 28 días con ambos modelos: {ventanas} (374 series cada una).\n\n")
        f.write("## 1) Calidad de la predicción (peso LGBM 0 = solo ETS, 1 = solo LightGBM)\n\n" + md(T1))
        f.write(f"**Mezcla 50/50 frente a LightGBM solo**, diferencia por serie (promedio de las ventanas), con remuestreo de las 374 series:\n"
                f"- pinball escalada (negativo = la mezcla es mejor): media {d.mean():+.4f}, intervalo 95 % [{ic[0]:+.4f}, {ic[1]:+.4f}]; la mezcla gana en {100 * gan:.0f} % de las series.\n"
                f"- MASE: media {dm.mean():+.4f}, intervalo 95 % [{icm[0]:+.4f}, {icm[1]:+.4f}].\n"
                "El intervalo solo mide la variación entre series; no incluye la incertidumbre de usar solo 6 ventanas ni un único periodo de M5.\n\n")
        f.write("## 2) Con tres modelos (ETS + LightGBM + TFT h64), solo ventanas donde existe el TFT\n\n" + md(T3))
        f.write("## 3) Reposición (unidades; ver POSPROCESO.md para las reglas de la simulación)\n\n"
                "Sobrante relativo a la demanda que hace falta para llegar a una tasa de servicio dada (interpolando en k de P50 + k x (P90 - P50)); menor es mejor.\n\n")
        f.write("### 2 modelos, todas las ventanas\n\n" + md(Q.set_index(["politica", "config"])))
        f.write("### con TFT, ventanas comunes\n\n" + md(Q3.set_index(["politica", "config"])))
    print((RES / "ENSAMBLE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
