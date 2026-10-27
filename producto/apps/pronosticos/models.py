from django.db import models

from apps.catalogo.models import Serie


class CorridaModelo(models.Model):
    """Una ejecución de un modelo: cuándo se entrenó, con qué origen y si es un pronóstico real hacia el futuro."""
    TIPOS = [("naive", "Naive estacional"), ("ets", "ETS"), ("lightgbm", "LightGBM (cuantiles diarios)"),
             ("tft", "Temporal Fusion Transformer"), ("lgbm_agregado", "LightGBM (cuantil de la demanda agregada)")]

    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    dnum_origen = models.PositiveIntegerField(help_text="Último día observado por el modelo (d_N).")
    fecha_origen = models.DateField()
    es_futuro_real = models.BooleanField(default=False, help_text="True si pronostica días posteriores al último dato real.")
    parametros = models.JSONField(default=dict, blank=True)
    ruta_modelo = models.CharField(max_length=300, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=False, help_text="La corrida que usa el panel y el chat.")

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return f"{self.nombre} (origen d_{self.dnum_origen})"


class Prediccion(models.Model):
    """Pronóstico diario por cuantiles de una serie."""
    corrida = models.ForeignKey(CorridaModelo, on_delete=models.CASCADE, related_name="predicciones")
    serie = models.ForeignKey(Serie, on_delete=models.CASCADE, related_name="predicciones")
    fecha = models.DateField()
    p10 = models.FloatField()
    p50 = models.FloatField()
    p90 = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["corrida", "serie", "fecha"], name="prediccion_unica")]
        indexes = [models.Index(fields=["corrida", "serie", "fecha"])]


class PrediccionAgregada(models.Model):
    """Cuantil de la demanda total de un horizonte (semana 1 a 4, o los 28 días)."""
    HORIZONTES = [("sem1", "Semana 1"), ("sem2", "Semana 2"), ("sem3", "Semana 3"), ("sem4", "Semana 4"), ("28d", "28 días")]

    corrida = models.ForeignKey(CorridaModelo, on_delete=models.CASCADE, related_name="agregadas")
    serie = models.ForeignKey(Serie, on_delete=models.CASCADE, related_name="agregadas")
    horizonte = models.CharField(max_length=5, choices=HORIZONTES)
    tau = models.FloatField()
    unidades = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["corrida", "serie", "horizonte", "tau"], name="agregada_unica")]
        indexes = [models.Index(fields=["corrida", "serie", "horizonte"])]


class SugerenciaReposicion(models.Model):
    """Cuánto tener en inventario al inicio del horizonte para un nivel de servicio dado."""
    POLITICAS = [("28d", "Una reposición de 28 días"), ("semanal", "Reposición semanal")]

    corrida = models.ForeignKey(CorridaModelo, on_delete=models.CASCADE, related_name="sugerencias")
    serie = models.ForeignKey(Serie, on_delete=models.CASCADE, related_name="sugerencias")
    politica = models.CharField(max_length=10, choices=POLITICAS)
    nivel_servicio = models.FloatField(help_text="Cuantil tau usado (ej. 0,9).")
    stock_objetivo = models.FloatField(help_text="Unidades a tener disponibles para el horizonte.")
    demanda_mediana = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["corrida", "serie", "politica", "nivel_servicio"], name="sugerencia_unica")]


class MetricaModelo(models.Model):
    """Resultados de evaluación (se cargan de los consolidados de las pruebas) para la página de comparación de modelos."""
    modelo = models.CharField(max_length=40)
    ventana_origen = models.PositiveIntegerField(null=True, blank=True)
    segmento = models.CharField(max_length=40, default="global")
    metrica = models.CharField(max_length=40)
    valor = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["modelo", "metrica"])]


class InventarioActual(models.Model):
    """Unidades que hay hoy de cada serie. Con esto la reposición se calcula al instante: pedido = stock objetivo - inventario actual."""
    serie = models.OneToOneField(Serie, on_delete=models.CASCADE, related_name="inventario")
    unidades = models.PositiveIntegerField(default=0)
    simulado = models.BooleanField(default=False, help_text="True si lo generó el comando de demostración (no es un dato real).")
    actualizado = models.DateTimeField(auto_now=True)


class EjecucionTarea(models.Model):
    """Una tarea lanzada desde la pestaña Modelos (corre en un proceso aparte; el registro sirve para ver su estado y su registro)."""
    COMANDOS = [("generar_predicciones", "Generar predicciones"), ("entrenar_tft", "Entrenar TFT")]
    ESTADOS = [("pendiente", "Pendiente"), ("ejecutando", "Ejecutando"), ("ok", "Terminada"), ("error", "Con error"), ("interrumpida", "Interrumpida")]

    comando = models.CharField(max_length=40, choices=COMANDOS)
    parametros = models.JSONField(default=dict, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default="pendiente")
    creada = models.DateTimeField(auto_now_add=True)
    inicio = models.DateTimeField(null=True, blank=True)
    fin = models.DateTimeField(null=True, blank=True)
    pid = models.IntegerField(null=True, blank=True)
    ruta_log = models.CharField(max_length=300, blank=True)
    resumen = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-creada"]

    @property
    def duracion(self):
        from django.utils import timezone
        if not self.inicio:
            return None
        return (self.fin or timezone.now()) - self.inicio
