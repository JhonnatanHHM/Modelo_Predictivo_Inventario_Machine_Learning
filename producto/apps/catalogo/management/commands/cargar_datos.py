"""Carga a PostgreSQL el calendario, las series, las ventas diarias y los precios semanales de M5.

Uso:  python manage.py cargar_datos [--limpiar]
Lee las rutas de config/settings.py (variables M5_DIR, TABLA_MAESTRA y SERIES_CSV del archivo .env).
Los datos de M5 no se redistribuyen: este comando los lee de tu computador y solo los guarda en tu base de datos local.
"""
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogo.models import Calendario, Categoria, Departamento, PrecioSemanal, Serie, Tienda, VentaDiaria

LOTE = 20000


class Command(BaseCommand):
    help = "Carga calendario, series, ventas diarias y precios de M5 en la base de datos."

    def add_arguments(self, parser):
        parser.add_argument("--limpiar", action="store_true", help="Borra antes lo que ya estaba cargado.")

    def handle(self, *args, **opts):
        for ruta in (settings.M5_DIR / "calendar.csv", settings.M5_DIR / "sell_prices.csv", settings.TABLA_MAESTRA, settings.SERIES_CSV):
            if not ruta.exists():
                raise CommandError(f"No encuentro {ruta}. Revisa M5_DIR, TABLA_MAESTRA y SERIES_CSV en tu archivo .env.")
        with transaction.atomic():
            if opts["limpiar"]:
                for modelo in (VentaDiaria, PrecioSemanal, Serie, Departamento, Categoria, Tienda, Calendario):
                    modelo.objects.all().delete()
                self.stdout.write("Tablas limpiadas.")
            self.calendario()
            series = self.series()
            self.ventas(series)
            self.precios(series)
        self.stdout.write(self.style.SUCCESS("Carga completa."))

    def calendario(self):
        cal = pd.read_csv(settings.M5_DIR / "calendar.csv")
        filas = [Calendario(fecha=r.date, dnum=int(r.d[2:]), wm_yr_wk=r.wm_yr_wk, dia_semana=r.wday, mes=r.month, anio=r.year,
                            evento="" if pd.isna(r.event_name_1) else r.event_name_1, tipo_evento="" if pd.isna(r.event_type_1) else r.event_type_1,
                            snap_ca=bool(r.snap_CA), snap_tx=bool(r.snap_TX), snap_wi=bool(r.snap_WI)) for r in cal.itertuples()]
        Calendario.objects.bulk_create(filas, ignore_conflicts=True)
        self.stdout.write(f"Calendario: {len(filas)} días (hasta {cal.date.iloc[-1]}).")

    def series(self):
        s = pd.read_csv(settings.SERIES_CSV)
        fechas = dict(Calendario.objects.values_list("dnum", "fecha"))
        tiendas = {c: Tienda.objects.get_or_create(codigo=c, defaults={"estado": e})[0] for c, e in s[["store_id", "state_id"]].drop_duplicates().itertuples(index=False)}
        categorias = {c: Categoria.objects.get_or_create(codigo=c)[0] for c in s.cat_id.unique()}
        deptos = {d: Departamento.objects.get_or_create(codigo=d, defaults={"categoria": categorias[c]})[0] for d, c in s[["dept_id", "cat_id"]].drop_duplicates().itertuples(index=False)}
        filas = [Serie(id_m5=r.id, item_id=r.item_id, tienda=tiendas[r.store_id], departamento=deptos[r.dept_id], rotacion=r.tier,
                       primera_venta=fechas.get(int(r.first_sale_day))) for r in s.itertuples()]
        Serie.objects.bulk_create(filas, ignore_conflicts=True)
        self.stdout.write(f"Series: {len(filas)} (tiendas {len(tiendas)}, departamentos {len(deptos)}).")
        return dict(Serie.objects.values_list("id_m5", "id"))

    def ventas(self, series):
        m = pd.read_parquet(settings.TABLA_MAESTRA, columns=["unique_id", "ds", "y", "sell_price", "snap", "event_flag"])
        m["serie_id"] = m.unique_id.map(series)
        total = 0
        for i in range(0, len(m), LOTE):
            b = m.iloc[i:i + LOTE]
            VentaDiaria.objects.bulk_create([
                VentaDiaria(serie_id=r.serie_id, fecha=r.ds.date(), unidades=int(r.y), precio=None if pd.isna(r.sell_price) else round(r.sell_price, 2),
                            snap=bool(r.snap), evento=bool(r.event_flag)) for r in b.itertuples()], ignore_conflicts=True)
            total += len(b)
            self.stdout.write(f"\rVentas diarias: {total:,} de {len(m):,}", ending="")
        self.stdout.write("")

    def precios(self, series):
        pares = {(s.item_id, s.tienda.codigo): s.id for s in Serie.objects.select_related("tienda")}
        total = 0
        for bloque in pd.read_csv(settings.M5_DIR / "sell_prices.csv", chunksize=1_000_000):
            bloque["sid"] = [pares.get((i, t)) for i, t in zip(bloque.item_id, bloque.store_id)]
            b = bloque[bloque.sid.notna()]
            PrecioSemanal.objects.bulk_create([PrecioSemanal(serie_id=int(r.sid), wm_yr_wk=int(r.wm_yr_wk), precio=round(r.sell_price, 2)) for r in b.itertuples()],
                                              batch_size=LOTE, ignore_conflicts=True)
            total += len(b)
        self.stdout.write(f"Precios semanales: {total:,}.")
