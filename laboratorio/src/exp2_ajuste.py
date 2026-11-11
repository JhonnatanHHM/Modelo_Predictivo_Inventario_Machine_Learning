"""Experimento 2: ajuste de hiperparámetros con Optuna (TPE) sobre ventanas de validación.

Objetivo: pinball escalada media (promedio de los tres cuantiles) en los orígenes de validación.
Uso: python src/exp2_ajuste.py <conjunto_de_variables: base|todas_nuevas|lista separada por comas de grupos> <n_pruebas> [limite_minutos]
Las ventanas de prueba (1885 y 1913) no se tocan.
"""
import sys, time, warnings, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")
import optuna
import pandas as pd
import lab_lgbm as L

optuna.logging.set_verbosity(optuna.logging.WARNING)
VALIDACION = [1773, 1801, 1829, 1857]
conjunto = sys.argv[1]
n_pruebas = int(sys.argv[2])
limite = float(sys.argv[3]) * 60 if len(sys.argv) > 3 else None
SAL = L.LAB / "resultados"

if conjunto == "base":
    VARS = L.VARS_BASE
elif conjunto == "todas_nuevas":
    VARS = L.VARS_BASE + L.VARS_NUEVAS
else:
    VARS = L.VARS_BASE + [v for g in conjunto.split(",") for v in L.GRUPOS_NUEVOS[g]]

L.no_dormir()
master, sel = L.cargar()
D = L.preparar(master)
tablas = {}
for o in VALIDACION:
    tr, va, te = L.tablas(D, o, nuevas=len(VARS) > len(L.VARS_BASE))
    tablas[o] = (tr, va, te, L.escalas(master, o))
print("tablas listas", flush=True)


def espacio(trial):
    return dict(
        n_estimators=1500,
        learning_rate=trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
        num_leaves=trial.suggest_int("num_leaves", 8, 255, log=True),
        max_depth=trial.suggest_categorical("max_depth", [-1, 4, 6, 8, 10, 12]),
        min_child_samples=trial.suggest_int("min_child_samples", 10, 400, log=True),
        subsample=trial.suggest_float("subsample", 0.5, 1.0),
        subsample_freq=1,
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.4, 1.0),
        reg_alpha=trial.suggest_float("reg_alpha", 1e-3, 10, log=True),
        reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 30, log=True),
        max_bin=trial.suggest_categorical("max_bin", [63, 127, 255]),
        path_smooth=trial.suggest_float("path_smooth", 0, 50),
        verbose=-1, random_state=L.SEMILLA)


def objetivo(trial):
    p = espacio(trial)
    vals, mases = [], []
    for k, o in enumerate(VALIDACION):
        tr, va, te, esc = tablas[o]
        out, it = L.ajustar_predecir(tr, va, te, VARS, p)
        ps, g = L.evaluar(L.a_pronostico(out, D), master, sel, o, esc)
        vals.append(g.pinball_escalada_media); mases.append(g.MASE_medio)
        trial.report(sum(vals) / len(vals), k)
        if trial.should_prune():
            raise optuna.TrialPruned()
    trial.set_user_attr("MASE", sum(mases) / len(mases))
    return sum(vals) / len(vals)


estudio = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=L.SEMILLA, n_startup_trials=10),
                              pruner=optuna.pruners.MedianPruner(n_startup_trials=8, n_warmup_steps=1))
# la configuración de la Unidad 1 como primera prueba, para que sea comparable
estudio.enqueue_trial(dict(learning_rate=0.05, num_leaves=31, max_depth=-1, min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                           reg_alpha=1e-3, reg_lambda=1e-3, max_bin=255, path_smooth=0.0))
t0 = time.time()
for i in range(n_pruebas):
    if limite and time.time() - t0 > limite:
        print("límite de tiempo alcanzado", flush=True)
        break
    estudio.optimize(objetivo, n_trials=1)
    t = estudio.trials[-1]
    mejor = estudio.best_value if any(x.state.name == "COMPLETE" for x in estudio.trials) else float("nan")
    print(f"prueba {i:3d} {t.state.name:9s} valor {t.value if t.value is not None else float('nan'):.5f}  mejor {mejor:.5f}  ({time.time() - t0:.0f} s)", flush=True)
df = estudio.trials_dataframe()
df.to_csv(SAL / f"exp2_pruebas_{conjunto}.csv", index=False)
mejor = dict(estudio.best_params, n_estimators=1500)
json.dump({"conjunto": conjunto, "variables": VARS, "mejor_valor": estudio.best_value, "mejores_parametros": mejor,
           "MASE_mejor": estudio.best_trial.user_attrs.get("MASE")}, open(SAL / f"exp2_mejor_{conjunto}.json", "w"), indent=1)
print("MEJOR", json.dumps(mejor), estudio.best_value)
