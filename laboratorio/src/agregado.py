"""Cuantil de la demanda AGREGADA (semanal y de 28 días) con LightGBM, para decidir la reposición.
En vez de sumar cuantiles diarios, se entrena para predecir directamente el cuantil de la suma de la demanda.
Uso: python src/agregado.py   -> resultados_completa/agregado/ (curvas, AGREGADO.md, g4_agregado.png)
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import lightgbm as lgb
sys.path.insert(0, str(Path(__file__).parent))
import posproceso as PP
from modelos_base import _arreglos

ROOT = PP.ROOT; RES = PP.RES; OUT = RES / "agregado"; OUT.mkdir(exist_ok=True)
H = 28
TAUS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975)
VENTANAS = [1773, 1801, 1829, 1857, 1885, 1913]
PARAMS = dict(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=50, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, random_state=42)
COLS = ["sem", "ult_L", "m7", "m28", "m56", "sd28", "nz28", "edad", "precio", "precio_rel", "snap", "evento", "mes", "tienda", "depto", "estado"]

master = pd.read_parquet(ROOT / "datos_completa" / "tabla_maestra_alfa.parquet")
ids, Y, P, SN, EV, DOW, MES, stat, inicio = _arreglos(master)
assert list(ids) == list(PP.IDS)
n = len(ids)

def fila(k, o, w0, L):
    """Rasgos de la serie k con último día observado o (dnum, 1-based), para la ventana de L días que empieza en o+1+w0."""
    s0 = inicio[k]; hist = Y[k, s0:o]
    if len(hist) < 56:
        return None
    t0 = o + w0                                   # índice 0-based del primer día de la ventana
    p = P[k, t0:t0 + L]; p_hist = P[k, max(s0, o - 28):o]
    pm = np.nanmean(p) if np.isfinite(p).any() else np.nan
    ph = np.nanmean(p_hist) if np.isfinite(p_hist).any() else np.nan
    return [w0 // 7, hist[-L:].sum() if L == 7 else hist[-28:].sum(), hist[-7:].mean(), hist[-28:].mean(), hist[-56:].mean(), hist[-28:].std(),
            (hist[-28:] > 0).mean(), min(o - s0, 1000), pm, pm / ph if ph and ph > 0 else np.nan, SN[k, t0:t0 + L].sum(),
            EV[k, t0:t0 + L].sum(), MES[t0 + L // 2], stat["store"][k], stat["dept"][k], stat["state"][k]]

def tabla(O, L, w0s, entrenamiento):
    """Filas (k, o, w0). Entrenamiento: orígenes cada 7 días con el objetivo terminando antes o en O. Prueba: origen O."""
    X, y = [], []
    for k in range(n):
        for w0 in w0s:
            if entrenamiento:
                o_max = O - w0 - L
                for o in range(o_max, max(inicio[k] + 56, O - 28 - 364) - 1, -7):
                    f = fila(k, o, w0, L); t = Y[k, o + w0:o + w0 + L]
                    if f is not None and np.isfinite(t).all():
                        X.append(f); y.append(t.sum())
            else:
                f = fila(k, O, w0, L)
                if f is not None:
                    X.append(f); y.append(np.nan)
    return pd.DataFrame(X, columns=COLS), np.array(y)

def predecir(O, L, w0s):
    Xtr, ytr = tabla(O, L, w0s, True)
    Xte, _ = tabla(O, L, w0s, False)
    Q = np.zeros((len(Xte), len(TAUS)))
    for j, tau in enumerate(TAUS):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, **PARAMS)
        m.fit(Xtr, ytr, categorical_feature=["tienda", "depto", "estado"])
        Q[:, j] = m.predict(Xte)
    return np.sort(np.clip(Q, 0, None), axis=1), len(Xtr)

def sim28(Yd, S):
    D = Yd.sum(1)
    return {"demanda": D.sum(), "vendidas": np.minimum(S, D).sum(), "faltante": np.maximum(0, D - S).sum(), "sobrante": np.maximum(0, S - D).sum(), "n": len(D), "sin_quiebre": int((D <= S).sum())}

def simw(Yd, T):
    onhand = np.zeros(len(Yd)); vend = 0.0; falt = 0.0; sob = 0.0; sq = 0
    for w in range(4):
        onhand = onhand + np.maximum(0, T[:, w] - onhand)
        fw = np.zeros(len(Yd))
        for t in range(7 * w, 7 * w + 7):
            v = np.minimum(onhand, Yd[:, t]); onhand -= v; vend += v.sum(); fw += Yd[:, t] - v
        falt += fw.sum(); sq += int((fw <= 1e-9).sum()); sob += onhand.sum()
    return {"demanda": Yd.sum(), "vendidas": vend, "faltante": falt, "sobrante": sob, "n": len(Yd) * 4, "sin_quiebre": sq}

def main():
    filas, cobs = [], []
    for O in VENTANAS:
        Yd, esc, m28 = PP.datos_ventana(O)
        Qw, ntr_w = predecir(O, 7, [0, 7, 14, 21])                         # filas ordenadas por serie y semana
        Qw = Qw.reshape(n, 4, len(TAUS))
        Q28, ntr_28 = predecir(O, 28, [0])
        print(f"ventana {O}: filas de entrenamiento semanal {ntr_w:,}, 28 días {ntr_28:,}", flush=True)
        Dsem = np.stack([Yd[:, 7 * w:7 * w + 7].sum(1) for w in range(4)], axis=1)
        for j, tau in enumerate(TAUS):
            a = sim28(Yd, Q28[:, j]); b = simw(Yd, Qw[:, :, j])
            for pol, s in (("28d", a), ("semanal", b)):
                s.update(origen=O, tau=tau, politica=pol); filas.append(s)
            cobs.append({"origen": O, "tau": tau, "cob_semanal": float((Dsem <= Qw[:, :, j]).mean()), "cob_28d": float((Yd.sum(1) <= Q28[:, j]).mean())})
    R = pd.DataFrame(filas); C = pd.DataFrame(cobs)
    R.to_csv(OUT / "agregado_reposicion_detalle.csv", index=False); C.to_csv(OUT / "agregado_cobertura_detalle.csv", index=False)

    def curva(df, grupo):
        g = df.groupby(grupo).apply(lambda x: pd.Series({"servicio": x.vendidas.sum() / x.demanda.sum(), "sobrante": x.sobrante.sum() / x.demanda.sum(),
                                                         "faltante": x.faltante.sum() / x.demanda.sum(), "sin_quiebre": x.sin_quiebre.sum() / x.n.sum()}), include_groups=False)
        return g
    old = pd.read_csv(RES / "posproceso_reposicion_detalle.csv"); old = old[old.version == "cruda"]
    def a_servicio(g, s):
        g = g.sort_values("sobrante"); return float(np.interp(s, g.sobrante, g.servicio))
    comunes = [1857, 1885, 1913]
    lineas = []
    comp = {}
    for alcance, vent in (("3 ventanas (1857, 1885, 1913)", comunes), ("6 ventanas (1773 a 1913)", VENTANAS)):
        for pol in ("28d", "semanal"):
            nuevo = curva(R[(R.politica == pol) & R.origen.isin(vent)], "tau")
            fila_ = {"agregado_lgbm": [a_servicio(nuevo, s) for s in (0.3, 0.5, 1.0)]}
            for m in ["ets", "lightgbm", "tft_h64", "tft_s1", "naive", "media28d"]:
                d = old[(old.politica == pol) & (old.modelo == m) & old.origen.isin(vent)]
                if d.empty or set(d.origen.unique()) != set(vent):
                    continue
                fila_[m] = [a_servicio(d.assign(servicio=0).groupby("k").apply(lambda x: pd.Series({"servicio": x.vendidas.sum() / x.demanda.sum(), "sobrante": x.sobrante.sum() / x.demanda.sum()}), include_groups=False), s) for s in (0.3, 0.5, 1.0)]
            comp[(alcance, pol)] = pd.DataFrame(fila_, index=["serv@sobrante0.3", "serv@sobrante0.5", "serv@sobrante1.0"]).T.round(3)
    cobt = C.groupby("tau")[["cob_semanal", "cob_28d"]].mean().round(3)
    # gráfica
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ejes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, pol in zip(ejes, ["28d", "semanal"]):
        nuevo = curva(R[(R.politica == pol) & R.origen.isin(comunes)], "tau")
        ax.plot(nuevo.sobrante, nuevo.servicio, "-o", ms=4, lw=2.5, color="black", label="LightGBM cuantil de la suma (nuevo)")
        for m, c in (("ets", "tab:green"), ("lightgbm", "tab:purple"), ("tft_h64", "tab:red"), ("media28d", "tab:blue")):
            d = old[(old.politica == pol) & (old.modelo == m) & old.origen.isin(comunes)]
            g = d.groupby("k").apply(lambda x: pd.Series({"servicio": x.vendidas.sum() / x.demanda.sum(), "sobrante": x.sobrante.sum() / x.demanda.sum()}), include_groups=False).sort_values("sobrante")
            ax.plot(g.sobrante, g.servicio, "--", color=c, label=f"{m} (suma de cuantiles diarios)" if m != "media28d" else "media móvil 28 d x c")
        ax.set_xlim(0, 2.0); ax.set_title(f"Política {pol}: servicio vs. sobrante"); ax.set_xlabel("Sobrante relativo a la demanda"); ax.set_ylabel("Tasa de servicio"); ax.grid(alpha=.3)
    ejes[0].legend(fontsize=7); fig.tight_layout(); fig.savefig(OUT / "g4_agregado.png", dpi=130)
    def md(df): return "```\n" + df.to_string() + "\n```\n\n"
    with open(OUT / "AGREGADO.md", "w", encoding="utf-8") as f:
        f.write("# Cuantil de la demanda agregada (LightGBM) para reposición\n\n"
                "Se entrena un LightGBM por cuantil tau para predecir directamente la **suma** de la demanda: semanal (4 semanas por serie) y de 28 días. "
                "El nivel de reposición es ese cuantil; no se suman cuantiles diarios. Mismo simulador y mismas ventanas que antes (plazo de entrega 0, solo unidades).\n\n"
                "## Cobertura de los cuantiles agregados (promedio de 6 ventanas; debería ser igual a tau)\n\n" + md(cobt))
        for (alcance, pol), t in comp.items():
            f.write(f"## Tasa de servicio con el mismo sobrante: política {pol}, {alcance}\n\n" + md(t))
    print((OUT / "AGREGADO.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()
