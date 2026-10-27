"""Orquesta la prueba alfa de extremo a extremo. Uso: python src/run_alfa.py [--solo-datos] [--sin-tft] [--sin-lgbm] [--sin-ets] [--pasos N] [--series N]"""
import argparse, sys, time, traceback
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from config import OUT_RES, N_POR_ESTRATO, TFT_STEPS, TEST_START, SINTETICO, ORIGIN, H, TABLA_DIR
from utils import preparar_log, log, cronometro, info_equipo, guardar_json, TIEMPOS, guardar_tabla

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-datos", action="store_true"); ap.add_argument("--sin-tft", action="store_true")
    ap.add_argument("--sin-lgbm", action="store_true"); ap.add_argument("--sin-ets", action="store_true")
    ap.add_argument("--pasos", type=int, default=TFT_STEPS); ap.add_argument("--series", type=int, default=N_POR_ESTRATO); ap.add_argument("--reusar-tabla", action="store_true")
    a = ap.parse_args()
    preparar_log("alfa")
    equipo = info_equipo(); log().info(f"Equipo: {equipo}")
    if SINTETICO:
        from datos_sinteticos import generar
        log().info("MODO SINTÉTICO (datos inventados)"); generar()
    import etapa1_tabla_maestra as e1
    with cronometro("1_tabla_maestra"):
        if a.reusar_tabla:
            master = pd.read_parquet(TABLA_DIR / "tabla_maestra_alfa.parquet"); sel = pd.read_csv(TABLA_DIR / "series_alfa.csv")
            log().info(f"Tabla maestra reutilizada de {TABLA_DIR}: {len(master):,} filas, {master.unique_id.nunique()} series")
        else:
            master, sel = e1.construir(a.series)
    if a.solo_datos:
        guardar_json({"equipo": equipo, "tiempos_s": TIEMPOS}, OUT_RES / "tiempos_etapa1.json"); return
    import metricas as M, modelos_base as B
    master = master[master.dnum <= ORIGIN + H]                      # los modelos nunca ven nada posterior a la ventana de prueba
    test = master[master.dnum >= TEST_START][["unique_id", "ds", "y"]]
    esc = M.escalas(master)
    log().info(f"Ventana de prueba: {test.ds.min().date()} a {test.ds.max().date()} ({test.unique_id.nunique()} series)")
    modelos = [("naive", B.pronostico_naive)]
    if not a.sin_ets: modelos.append(("ets", B.pronostico_ets))
    if not a.sin_lgbm: modelos.append(("lightgbm", B.pronostico_lgbm))
    if not a.sin_tft:
        import modelo_tft as T
        modelos.append(("tft", lambda m: T.pronostico_tft(m, a.pasos)))
    preds, fallos = {}, {}
    for nombre, f in modelos:
        try:
            with cronometro(f"modelo_{nombre}"):
                preds[nombre] = f(master)
            guardar_tabla(preds[nombre], f"pred_{nombre}")
        except Exception as e:
            fallos[nombre] = f"{type(e).__name__}: {e}"
            log().info(f"!!! FALLÓ {nombre}: {fallos[nombre]}"); log().info(traceback.format_exc())
    OUT_RES.mkdir(parents=True, exist_ok=True)
    glob, por_serie = {}, {}
    for nombre, p in preds.items():
        ps = M.evaluar_series(p, test, esc); por_serie[nombre] = ps
        glob[nombre] = M.resumen(ps, sel).iloc[0]
    glob_df = pd.DataFrame(glob).T
    glob_df.to_csv(OUT_RES / "metricas_globales.csv")
    for col in ["store_id", "dept_id", "tier"]:
        pd.concat({n: M.resumen(ps, sel, col) for n, ps in por_serie.items()}).to_csv(OUT_RES / f"metricas_por_{col}.csv")
    pd.concat({n: ps for n, ps in por_serie.items()}).to_csv(OUT_RES / "metricas_por_serie.csv")
    try:
        from reportes import graficas
        graficas(master, preds, glob_df)
    except Exception as e:
        log().info(f"Gráficas no generadas: {e}")
    guardar_json({"equipo": equipo, "tiempos_s": TIEMPOS, "fallos": fallos, "pasos_tft": a.pasos, "origen": ORIGIN, "series": int(master.unique_id.nunique())}, OUT_RES / "tiempos_y_equipo.json")
    pd.set_option("display.width", 200)
    cols = ["MASE_medio", "MASE_mediana", "pinball_escalada_media", "WQL", "cobertura_p10", "cobertura_p90", "cobertura_80", "ancho_medio", "sesgo_relativo"]
    tabla = glob_df[cols].round(3)
    log().info("\n=== RESULTADOS GLOBALES (prueba alfa, 1 ventana de 28 días) ===\n" + tabla.to_string())
    with open(OUT_RES / "RESUMEN_ALFA.md", "w", encoding="utf-8") as f:
        f.write("# Resumen de la prueba alfa\n\n" + ("**DATOS SINTÉTICOS (inventados)**\n\n" if SINTETICO else "") +
                f"Series: {master.unique_id.nunique()} | ventana de prueba: {test.ds.min().date()} a {test.ds.max().date()}\n\n## Métricas globales\n\n" +
                "```\n" + tabla.to_string() + "\n```" + "\n\n## Tiempos (segundos)\n\n" + "\n".join(f"- {k}: {v}" for k, v in TIEMPOS.items()) +
                "\n\n## Fallos\n\n" + ("\n".join(f"- {k}: {v}" for k, v in fallos.items()) or "Ninguno") +
                "\n\n## Equipo\n\n" + "\n".join(f"- {k}: {v}" for k, v in equipo.items()) + "\n")
    log().info("Listo. Resultados en: " + str(OUT_RES))

if __name__ == "__main__":
    main()
