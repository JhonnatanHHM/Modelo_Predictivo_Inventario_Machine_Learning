"""Posproceso sobre las predicciones guardadas (no entrena nada):
1) Calibración conformal simple de P10/P50/P90 (desplazamiento por cuantil, escalado por serie), usando como calibración la ventana anterior.
2) Cobertura por cuantil antes y después.
3) Simulación mínima de reposición en unidades (política por periodo de 28 días y política semanal), con sensibilidad al cuantil.
Uso: python src/posproceso.py   -> resultados_completa/POSPROCESO.md, posproceso_*.csv, g3_reposicion.png, _calibrado/
"""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "resultados_completa"
H = 28
TAUS = (0.1, 0.5, 0.9)
COLS = ["p10", "p50", "p90"]
K_LISTA = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.25, 1.5)       # nivel = P50 + k*(P90-P50): k=0 es P50, k=1 es P90
C_MEDIA = (1.0, 1.5, 2.0)                               # referencia: media de los últimos 28 días x c

master = pd.read_parquet(ROOT / "datos_completa" / "tabla_maestra_alfa.parquet", columns=["unique_id", "ds", "dnum", "y"])
sel = pd.read_csv(ROOT / "datos_completa" / "series_alfa.csv")
tier = sel.set_index("id")["tier"]
IDS = sorted(master.unique_id.unique())
Ymat = {}                                                 # y completo por serie (dict de arrays indexados por dnum)
for uid, g in master.groupby("unique_id"):
    Ymat[uid] = g.set_index("dnum")["y"]

def datos_ventana(origen):
    """y real (n,28), escala por serie y media de los últimos 28 días antes del origen."""
    Y = np.full((len(IDS), H), np.nan); esc = np.full(len(IDS), np.nan); m28 = np.full(len(IDS), np.nan)
    for i, uid in enumerate(IDS):
        s = Ymat[uid]
        v = s[s.index <= origen].to_numpy(float)
        esc[i] = np.abs(v[7:] - v[:-7]).mean() if len(v) > 7 else np.nan
        m28[i] = v[-28:].mean()
        f = s.reindex(range(origen + 1, origen + H + 1)).to_numpy(float)
        Y[i] = f
    esc = np.where(esc > 0.05, esc, 0.05)
    return Y, esc, m28

def cargar():
    """{modelo_id: {origen: array (n,28,3)}}"""
    out = {}
    for d in sorted(RES.iterdir()):
        m = re.match(r"^(base|tft)_o(\d+)(?:_(.*))?$", d.name)
        if not m or not d.is_dir():
            continue
        tipo, origen, var = m.group(1), int(m.group(2)), m.group(3)
        for f in (d / "datos").glob("pred_*.parquet"):
            mod = f.stem.replace("pred_", "")
            if tipo == "tft" and mod != "tft":
                continue
            if tipo == "base" and mod == "tft":
                continue
            mid = f"tft_{var}" if mod == "tft" else mod
            p = pd.read_parquet(f)
            p["ds"] = pd.to_datetime(p["ds"])
            fechas = sorted(p.ds.unique())
            arr = np.full((len(IDS), H, 3), np.nan)
            idx = {u: i for i, u in enumerate(IDS)}
            tmp = p.sort_values(["unique_id", "ds"])
            for uid, g in tmp.groupby("unique_id"):
                arr[idx[uid]] = g[COLS].to_numpy(float)[:H]
            out.setdefault(mid, {})[origen] = arr
    return out

def ordenar(q):
    return np.sort(np.clip(q, 0, None), axis=2)

def calibrar(q_test, q_cal, Y_cal, esc_cal, esc_test):
    """Desplazamiento por cuantil: delta_tau = cuantil tau de (y - q_tau)/escala en la ventana de calibración."""
    deltas = []
    q_new = q_test.copy()
    for j, tau in enumerate(TAUS):
        r = ((Y_cal - q_cal[:, :, j]) / esc_cal[:, None]).ravel()
        r = r[np.isfinite(r)]
        dl = float(np.quantile(r, tau)); deltas.append(dl)
        q_new[:, :, j] = q_test[:, :, j] + dl * esc_test[:, None]
    return ordenar(q_new), deltas

def pin(y, q, tau):
    d = y - q
    return np.maximum(tau * d, (tau - 1) * d)

def calidad(Y, q, esc):
    pins = [pin(Y, q[:, :, j], t) for j, t in enumerate(TAUS)]
    pl = np.mean([p.mean(axis=1) for p in pins], axis=0)
    return {"n": len(Y), "mase_sum": float((np.abs(Y - q[:, :, 1]).mean(axis=1) / esc).sum()),
            "pinball_esc_sum": float((pl / esc).sum()), "wql_num": float(sum(2 * p.sum() for p in pins)), "suma_y": float(Y.sum()),
            "cov_p10": float((Y <= q[:, :, 0]).mean()), "cov_p10_estricta": float((Y < q[:, :, 0]).mean()),
            "cov_p50": float((Y <= q[:, :, 1]).mean()), "cov_p90": float((Y <= q[:, :, 2]).mean()),
            "cov_80": float(((Y >= q[:, :, 0]) & (Y <= q[:, :, 2])).mean()), "ancho": float((q[:, :, 2] - q[:, :, 0]).mean())}

def simular(Y, nivel):
    """nivel: (n,28) inventario objetivo diario (unidades). Devuelve sumas para política A (28 días) y B (semanal con arrastre)."""
    nivel = np.clip(nivel, 0, None)
    D = Y.sum(axis=1); S = nivel.sum(axis=1)
    a = {"demanda": float(D.sum()), "vendidas": float(np.minimum(S, D).sum()), "faltante": float(np.maximum(0, D - S).sum()),
         "sobrante": float(np.maximum(0, S - D).sum()), "n": len(Y), "sin_quiebre": int((D <= S).sum())}
    onhand = np.zeros(len(Y)); vendidas = 0.0; falt = 0.0; sob_fin = 0.0; sin_q = 0
    for w in range(4):
        sl = slice(7 * w, 7 * w + 7)
        onhand = onhand + np.maximum(0, nivel[:, sl].sum(axis=1) - onhand)          # se pide hasta el objetivo de la semana
        fw = np.zeros(len(Y))
        for t in range(7 * w, 7 * w + 7):
            v = np.minimum(onhand, Y[:, t]); onhand -= v; vendidas += v.sum(); fw += Y[:, t] - v
        falt += fw.sum(); sin_q += int((fw <= 1e-9).sum()); sob_fin += onhand.sum()
    b = {"demanda": float(Y.sum()), "vendidas": float(vendidas), "faltante": float(falt), "sobrante": float(sob_fin), "n": len(Y) * 4, "sin_quiebre": sin_q}
    return a, b

def main():
    P = cargar()
    print("modelos:", {m: sorted(v) for m, v in P.items()})
    cache = {}
    def win(o):
        if o not in cache:
            cache[o] = datos_ventana(o)
        return cache[o]
    calid, inv, deltas_json = [], [], {}
    cal_dir = RES / "_calibrado"; cal_dir.mkdir(exist_ok=True)
    for mid, por_o in P.items():
        for o, q in por_o.items():
            Y, esc, m28 = win(o)
            versiones = {"cruda": q}
            if o - H in por_o:
                Yc, escc, _ = win(o - H)
                qc, dl = calibrar(q, por_o[o - H], Yc, escc, esc)
                versiones["calibrada"] = qc; deltas_json[f"{mid}@{o}"] = dl
                pd.DataFrame(qc.reshape(-1, 3), columns=COLS).assign(unique_id=np.repeat(IDS, H), dia=np.tile(np.arange(1, H + 1), len(IDS))).to_parquet(cal_dir / f"pred_cal_{mid}_{o}.parquet", index=False)
            for ver, qq in versiones.items():
                r = calidad(Y, qq, esc); r.update(modelo=mid, origen=o, version=ver, con_calibracion=("calibrada" in versiones)); calid.append(r)
                tiers = tier.reindex(IDS).to_numpy()
                for tr in ("alta", "media", "baja"):
                    mk = tiers == tr
                    rr = calidad(Y[mk], qq[mk], esc[mk]); rr.update(modelo=mid, origen=o, version=ver, tier=tr, con_calibracion=("calibrada" in versiones)); calid.append(rr)
                for k in K_LISTA:
                    nivel = qq[:, :, 1] + k * (qq[:, :, 2] - qq[:, :, 1])
                    a, b = simular(Y, nivel)
                    for pol, s in (("28d", a), ("semanal", b)):
                        s.update(modelo=mid, origen=o, version=ver, politica=pol, nivel=f"P50+{k}x(P90-P50)", k=k, con_calibracion=("calibrada" in versiones)); inv.append(s)
            if "cruda" in versiones and mid == "naive":                  # referencia: media móvil de 28 días (sin modelo)
                for c in C_MEDIA:
                    nivel = np.repeat((m28 * c)[:, None], H, axis=1)
                    a, b = simular(Y, nivel)
                    for pol, s in (("28d", a), ("semanal", b)):
                        s.update(modelo="media28d", origen=o, version="cruda", politica=pol, nivel=f"media28 x{c}", k=c, con_calibracion=False); inv.append(s)
    C = pd.DataFrame(calid); I = pd.DataFrame(inv)
    C.to_csv(RES / "posproceso_calidad_detalle.csv", index=False); I.to_csv(RES / "posproceso_reposicion_detalle.csv", index=False)
    (cal_dir / "deltas_conformales.json").write_text(json.dumps(deltas_json, indent=1))

    # ------------- 1) calibración: solo ventanas donde existe calibración (para comparar justo crudo vs calibrado)
    G = C[(C.get("tier").isna()) & (C.con_calibracion)]
    def agr(g):
        n = g.n.sum(); return pd.Series({"ventanas": ",".join(str(x) for x in sorted(g.origen.unique())), "MASE": g.mase_sum.sum() / n,
            "pinball_esc": g.pinball_esc_sum.sum() / n, "WQL": g.wql_num.sum() / g.suma_y.sum(),
            "cob_P10": np.average(g.cov_p10, weights=g.n), "cob_P10_estricta": np.average(g.cov_p10_estricta, weights=g.n), "cob_P50": np.average(g.cov_p50, weights=g.n),
            "cob_P90": np.average(g.cov_p90, weights=g.n), "cob_80": np.average(g.cov_80, weights=g.n), "ancho_80": np.average(g.ancho, weights=g.n)})
    T1 = G.groupby(["modelo", "version"]).apply(agr, include_groups=False).round(3)
    T1.to_csv(RES / "posproceso_calibracion.csv")
    Gt = C[(C.tier.notna()) & (C.con_calibracion)]
    T1t = Gt.groupby(["modelo", "version", "tier"]).apply(lambda g: pd.Series({"cob_P90": np.average(g.cov_p90, weights=g.n), "cob_80": np.average(g.cov_80, weights=g.n), "pinball_esc": g.pinball_esc_sum.sum() / g.n.sum()}), include_groups=False).round(3)
    # ------------- 2) reposición: ventanas comunes para comparar justo (donde existe calibración y todos los modelos principales)
    ref = I[I.con_calibracion | (I.modelo == "media28d")]
    def agri(g):
        return pd.Series({"tasa_servicio": g.vendidas.sum() / g.demanda.sum(), "faltante_rel": g.faltante.sum() / g.demanda.sum(),
                          "sobrante_rel": g.sobrante.sum() / g.demanda.sum(), "pct_sin_quiebre": g.sin_quiebre.sum() / g.n.sum(), "ventanas": ",".join(str(x) for x in sorted(g.origen.unique()))})
    comunes = sorted(set.intersection(*[set(P[m]) for m in ("naive", "ets", "lightgbm")]) & set(o for m in P for o in P[m] if m.startswith("tft_") and (o - H) in P[m]))
    I2 = ref[ref.origen.isin(comunes)]
    T2 = I2.groupby(["politica", "modelo", "version", "nivel"]).apply(agri, include_groups=False).round(3)
    T2.to_csv(RES / "posproceso_reposicion.csv")

    # ------------- 3) gráfica servicio vs sobrante
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ejes = plt.subplots(1, 2, figsize=(13, 5))
    modelos_g = [m for m in ["naive", "ets", "lightgbm", "tft_s1", "tft_h64"] if m in I2.modelo.unique()]
    for ax, pol in zip(ejes, ["28d", "semanal"]):
        for m in modelos_g + ["media28d"]:
            for ver, ls in (("cruda", "-"), ("calibrada", "--")):
                d = I2[(I2.politica == pol) & (I2.modelo == m) & (I2.version == ver)]
                if d.empty: continue
                g = d.groupby("k").apply(agri, include_groups=False).sort_index()
                ax.plot(g.sobrante_rel, g.tasa_servicio, ls, marker="o", ms=3, label=f"{m} ({ver})", alpha=.85)
        ax.set_title(f"Política {pol}: servicio vs. sobrante"); ax.set_xlabel("Sobrante relativo a la demanda"); ax.set_ylabel("Tasa de servicio (unidades vendidas / demandadas)"); ax.grid(alpha=.3)
    ejes[1].legend(fontsize=6, ncol=2); fig.tight_layout(); fig.savefig(RES / "g3_reposicion.png", dpi=130)

    # ------------- 4) informe
    def md(df): return "```\n" + df.to_string() + "\n```\n\n"
    with open(RES / "POSPROCESO.md", "w", encoding="utf-8") as f:
        f.write("# Posproceso: calibración conformal y simulación de reposición\n\n")
        f.write("Calibración: para cada modelo y ventana se estima, con la ventana inmediatamente anterior, el desplazamiento de cada cuantil "
                "(cuantil tau de (y - q_tau)/escala de la serie) y se aplica a la ventana de prueba. Solo se evalúan ventanas que tienen una anterior.\n\n")
        f.write("## 1) Cobertura por cuantil, crudo vs calibrado (objetivo: P10=0,10; P50=0,50; P90=0,90; intervalo 80 %=0,80)\n\n" + md(T1))
        f.write("`cob_P10_estricta` = proporción de días con y < P10. La cobertura `y <= P10` no puede bajar de la proporción de ceros (~60 %), por eso se reporta también la estricta.\n\n")
        f.write("## 2) Cobertura del P90 y del intervalo 80 % por rotación\n\n" + md(T1t))
        f.write(f"## 3) Simulación de reposición (unidades). Ventanas comunes: {comunes}\n\n")
        f.write("- **28d:** una sola reposición al inicio de los 28 días hasta el nivel indicado (suma de los 28 niveles diarios).\n"
                "- **semanal:** cada 7 días se repone hasta la suma de los niveles de esa semana (plazo de entrega 0); lo que sobra se arrastra.\n"
                "- **Nivel:** P50 + k x (P90 - P50). k=0 es el P50, k=1 es el P90. `media28 xc` = media de los últimos 28 días por c (sin modelo, referencia).\n"
                "- **Métricas:** tasa de servicio = vendidas/demandadas; faltante y sobrante relativos a la demanda; % de series-periodos sin quiebre. No hay costos ni dólares.\n\n")
        for pol in ("28d", "semanal"):
            sub = T2.loc[pol].reset_index()
            sub = sub[sub.nivel.isin(["P50+0.0x(P90-P50)", "P50+0.2x(P90-P50)", "P50+0.3x(P90-P50)", "P50+0.5x(P90-P50)", "P50+1.0x(P90-P50)", "media28 x1.0", "media28 x1.5", "media28 x2.0"])]
            f.write(f"### Política {pol}\n\n" + md(sub.set_index(["modelo", "version", "nivel"]).drop(columns="ventanas")))
    print((RES / "POSPROCESO.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()
