"""Etapa 1: construye la tabla maestra (formato largo) para las series de la alfa."""
import numpy as np, pandas as pd
from config import DATA_DIR, SERIES_CSV, LAST_DAY, N_POR_ESTRATO, SEMILLA
from utils import log, guardar_tabla

def elegir_series(n_por_estrato=N_POR_ESTRATO):
    """n series por tienda x departamento, intentando que sean de rotación distinta (baja, media, alta)."""
    sel = pd.read_csv(SERIES_CSV)
    partes = []
    for i, (_, g) in enumerate(sel.groupby(["store_id", "dept_id"])):
        g = g.sample(frac=1, random_state=SEMILLA + i)            # barajar con semilla distinta por grupo
        distintas = g.drop_duplicates("tier")
        resto = g[~g.id.isin(distintas.id)]
        partes.append(pd.concat([distintas, resto]).head(min(n_por_estrato, len(g))))
    return pd.concat(partes).reset_index(drop=True)

def construir(n_por_estrato=N_POR_ESTRATO):
    sel = elegir_series(n_por_estrato)
    ids = set(sel["id"])
    log().info(f"Series elegidas para la alfa: {len(sel)} (por tienda: {sel.store_id.value_counts().to_dict()})")

    cal = pd.read_csv(DATA_DIR / "calendar.csv")
    cal["dnum"] = cal["d"].str[2:].astype(int)
    cal["ds"] = pd.to_datetime(cal["date"])
    cal["event_flag"] = cal["event_name_1"].notna().astype("int8")
    cal["event_type_1"] = cal["event_type_1"].fillna("ninguno")
    cal = cal[cal.dnum <= LAST_DAY]

    # ventas: se lee por bloques y se filtra para no gastar memoria
    dcols = [f"d_{i}" for i in range(1, LAST_DAY + 1)]
    partes = []
    for bloque in pd.read_csv(DATA_DIR / "sales_train_evaluation.csv", chunksize=3000,
                              dtype={c: "int16" for c in dcols}):
        partes.append(bloque[bloque["id"].isin(ids)])
    ventas = pd.concat(partes, ignore_index=True)
    assert len(ventas) == len(ids), f"Faltan series: {len(ids) - len(ventas)}"

    largas = []
    snap_por_estado = {"CA": cal["snap_CA"].values, "TX": cal["snap_TX"].values, "WI": cal["snap_WI"].values}
    for _, r in ventas.iterrows():
        y = r[dcols].to_numpy(dtype=np.int32)
        primero = int(np.argmax(y > 0))              # índice (0-based) de la primera venta
        n = len(y) - primero
        dias = np.arange(primero + 1, len(y) + 1)    # d_primero+1 ... d_1941
        largas.append(pd.DataFrame({
            "unique_id": r["id"], "dnum": dias, "y": y[primero:],
            "item_id": r["item_id"], "dept_id": r["dept_id"], "cat_id": r["cat_id"],
            "store_id": r["store_id"], "state_id": r["state_id"],
            "snap": snap_por_estado[r["state_id"]][primero:len(y)].astype("int8")}))
    df = pd.concat(largas, ignore_index=True)
    df = df.merge(cal[["dnum", "ds", "wm_yr_wk", "wday", "month", "year", "event_flag", "event_type_1"]], on="dnum", how="left")

    precios = pd.read_csv(DATA_DIR / "sell_prices.csv")
    precios = precios.merge(sel[["store_id", "item_id"]].drop_duplicates(), on=["store_id", "item_id"])
    df = df.merge(precios, on=["store_id", "item_id", "wm_yr_wk"], how="left")
    df["on_sale"] = df["sell_price"].notna().astype("int8")

    # ---- Verificaciones ----
    viol = int(((df.on_sale == 0) & (df.y > 0)).sum())
    log().info(f"Filas: {len(df):,} | series: {df.unique_id.nunique()} | días con venta y SIN precio: {viol}")
    g = df.groupby("unique_id")["ds"].agg(["min", "max", "count"])
    cont = ((g["max"] - g["min"]).dt.days + 1 == g["count"]).all()
    log().info(f"Series con fechas continuas: {bool(cont)} | y nulos: {int(df.y.isna().sum())} | negativos: {int((df.y < 0).sum())}")
    log().info(f"Porcentaje de ceros (desde la primera venta): {100 * (df.y == 0).mean():.1f} %")
    assert cont and df.y.isna().sum() == 0

    df = df.sort_values(["unique_id", "ds"]).reset_index(drop=True)
    ruta = guardar_tabla(df, "tabla_maestra_alfa")
    sel.to_csv(ruta.parent / "series_alfa.csv", index=False)
    log().info(f"Tabla maestra guardada: {ruta}")
    return df, sel

if __name__ == "__main__":
    from utils import preparar_log
    preparar_log("etapa1"); construir()
