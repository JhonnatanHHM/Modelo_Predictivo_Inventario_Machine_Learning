"""Comprueba que las bibliotecas y los archivos de M5 estén donde deben, y mide la velocidad del equipo."""
import sys, time, os
sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, SERIES_CSV
from utils import info_equipo

def main():
    print("=== Equipo y bibliotecas ===")
    for k, v in info_equipo().items():
        print(f"  {k}: {v}")
    print("\n=== Archivos de datos ===")
    for p in (DATA_DIR / "sales_train_evaluation.csv", DATA_DIR / "calendar.csv", DATA_DIR / "sell_prices.csv", SERIES_CSV):
        print(f"  {'OK ' if p.exists() else 'FALTA'}  {p}")
    try:
        import torch
        torch.manual_seed(0); a = torch.randn(1500, 1500); t0 = time.perf_counter()
        for _ in range(10): a @ a
        print(f"\n=== Velocidad: 10 multiplicaciones de matrices 1500x1500 en {time.perf_counter() - t0:.2f} s (referencia, no es una nota) ===")
    except Exception as e:
        print("\nNo se pudo medir la velocidad con torch:", e)
    print("\nSi todo dice OK y no hay 'NO INSTALADO', puedes seguir con el paso 2.")

if __name__ == "__main__":
    main()
