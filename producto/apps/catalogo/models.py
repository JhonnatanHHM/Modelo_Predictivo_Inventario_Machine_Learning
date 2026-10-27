from django.db import models


class Tienda(models.Model):
    codigo = models.CharField(max_length=10, unique=True)          # CA_1, TX_2, WI_2
    estado = models.CharField(max_length=2)                        # CA, TX, WI

    class Meta:
        ordering = ["codigo"]

    def __str__(self):
        return self.codigo


class Categoria(models.Model):
    codigo = models.CharField(max_length=20, unique=True)          # FOODS, HOBBIES, HOUSEHOLD

    class Meta:
        ordering = ["codigo"]

    def __str__(self):
        return self.codigo


class Departamento(models.Model):
    codigo = models.CharField(max_length=20, unique=True)          # FOODS_1 ...
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="departamentos")

    class Meta:
        ordering = ["codigo"]

    def __str__(self):
        return self.codigo


class Serie(models.Model):
    """Un producto en una tienda (la unidad que se pronostica)."""
    ROTACIONES = [("alta", "Alta"), ("media", "Media"), ("baja", "Baja")]

    id_m5 = models.CharField(max_length=60, unique=True)           # FOODS_1_004_CA_1_evaluation
    item_id = models.CharField(max_length=30, db_index=True)       # FOODS_1_004
    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, related_name="series")
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, related_name="series")
    rotacion = models.CharField(max_length=5, choices=ROTACIONES)
    primera_venta = models.DateField(null=True)

    class Meta:
        ordering = ["tienda__codigo", "item_id"]
        indexes = [models.Index(fields=["tienda", "departamento"])]

    def __str__(self):
        return f"{self.item_id} @ {self.tienda.codigo}"


class Calendario(models.Model):
    """Calendario de M5 (incluye los 28 días posteriores al histórico, que son el futuro conocido)."""
    fecha = models.DateField(unique=True)
    dnum = models.PositiveIntegerField(unique=True)                # d_1 ... d_1969
    wm_yr_wk = models.PositiveIntegerField(db_index=True)
    dia_semana = models.PositiveSmallIntegerField()                # wday de M5 (1 = sábado)
    mes = models.PositiveSmallIntegerField()
    anio = models.PositiveSmallIntegerField()
    evento = models.CharField(max_length=40, blank=True)
    tipo_evento = models.CharField(max_length=20, blank=True)
    snap_ca = models.BooleanField(default=False)
    snap_tx = models.BooleanField(default=False)
    snap_wi = models.BooleanField(default=False)

    class Meta:
        ordering = ["fecha"]

    def __str__(self):
        return str(self.fecha)


class PrecioSemanal(models.Model):
    serie = models.ForeignKey(Serie, on_delete=models.CASCADE, related_name="precios")
    wm_yr_wk = models.PositiveIntegerField()
    precio = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["serie", "wm_yr_wk"], name="precio_unico_por_semana")]


class VentaDiaria(models.Model):
    serie = models.ForeignKey(Serie, on_delete=models.CASCADE, related_name="ventas")
    fecha = models.DateField()
    unidades = models.PositiveIntegerField()
    precio = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    snap = models.BooleanField(default=False)
    evento = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["serie", "fecha"], name="venta_unica_por_dia")]
        indexes = [models.Index(fields=["fecha"])]
