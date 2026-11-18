"""Idea 31 - Validación honesta del modelo de tenis (solo medición; no cambia el modelo ni los picks).

scripts/train_model.py da un 63,7 % de acierto con validación cruzada aleatoria: mezcla años y pone las dos filas
espejo de un mismo partido en pliegues distintos, así que no dice cómo irá en partidos futuros. Aquí:

  1. Walk-forward por año: entrenar con 2018..N-1 y probar en N (N = 2021..último año con datos), con el escalador
     dentro del entrenamiento. Se evalúa una fila por partido (la del ganador), no las dos espejo.
  2. El modelo de producción (models/lr_model.json, entrenado 2018-2024) en 2025-2026: partidos que nunca vio.
  3. Métricas que importan para apostar: Brier y log-loss (calidad de la probabilidad) además del acierto, contra
     dos referencias simples: "gana el mejor clasificado" y la fórmula de puntos p = pA / (pA + pB).
  4. Calibración: por tramos de probabilidad del favorito, probabilidad media dada vs % real de victorias.

No hay cuotas históricas en Sackmann, así que esto NO compara contra el mercado (eso necesita otra fuente de cuotas).

  python run.py        # descarga los CSV de Sackmann en memoria (no guarda nada de ellos) y escribe RESULTADO.md
"""

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import train_model as tm  # noqa: E402  (mismos filtros y variables que producción)

YEARS = range(2018, 2027)
FIRST_TEST = 2021
# JeffSackmann/tennis_atp desapareció de GitHub (404, nov. 2026). Solo para esta prueba en papel (decisión del usuario,
# 18/11) se usa Tennismylife/TML-Database: mismo formato de columnas, un CSV por año. Producción no la usa.
SOURCE = "https://raw.githubusercontent.com/Tennismylife/TML-Database/master/{year}.csv"


def load_year(year: int) -> pd.DataFrame | None:
    r = requests.get(SOURCE.format(year=year), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), usecols=tm._COLS, dtype=str)
    df = df[~df["score"].str.contains("|".join(tm._INCOMPLETE), na=False, case=False)].copy()
    df["surface"] = df["surface"].map(tm._SURFACE_NORM).fillna("hard")
    for c in ["winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"])
    return df[(df["winner_rank_points"] > 0) & (df["loser_rank_points"] > 0)].reset_index(drop=True)


def winner_rows(df: pd.DataFrame) -> np.ndarray:
    """One row per match, winner as 'home' (same features as train_model.build_features)."""
    s = df["surface"]
    return np.column_stack([
        np.log(df["winner_rank_points"] / df["loser_rank_points"]),
        df["loser_rank"] - df["winner_rank"],
        (s == "clay").astype(float), (s == "grass").astype(float), (s == "indoor_hard").astype(float),
    ])


def metrics(p_winner: np.ndarray) -> dict:
    p = np.clip(p_winner, 1e-6, 1 - 1e-6)
    return {"n": int(len(p)), "acierto": float(np.mean(p > 0.5)), "brier": float(np.mean((1 - p) ** 2)),
            "logloss": float(np.mean(-np.log(p)))}


def calibration(p_winner: np.ndarray) -> list[dict]:
    """Favourite's probability (max(p, 1-p)) by bins vs how often the favourite actually won."""
    fav_p = np.maximum(p_winner, 1 - p_winner)
    fav_won = p_winner >= 0.5
    out = []
    for lo in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8):
        hi = lo + 0.05 if lo < 0.8 else 1.01
        m = (fav_p >= lo) & (fav_p < hi)
        if m.sum():
            out.append({"tramo": f"{lo:.0%}-{min(hi, 1):.0%}", "n": int(m.sum()), "prob_media": float(fav_p[m].mean()),
                        "real": float(fav_won[m].mean())})
    return out


def production_probs(X: np.ndarray) -> np.ndarray:
    m = json.loads((ROOT / "models" / "lr_model.json").read_text(encoding="utf-8"))
    z = ((X - np.array(m["scaler_mean"])) / np.array(m["scaler_std"])) @ np.array(m["coef"]) + m["intercept"]
    return 1 / (1 + np.exp(-z))


def main() -> None:
    data = {}
    for y in YEARS:
        df = load_year(y)
        if df is not None and len(df):
            data[y] = df
            print(f"{y}: {len(df)} partidos")
    res = {"walk_forward": [], "produccion_fuera_de_muestra": [], "calibracion": {}}

    for test in [y for y in data if y >= FIRST_TEST]:
        train = pd.concat([data[y] for y in data if y < test])
        Xtr, ytr = tm.build_features(train)           # filas espejo para entrenar, como producción
        model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
        model.fit(Xtr, ytr)
        df = data[test]
        Xte = winner_rows(df)
        p_lr = model.predict_proba(Xte)[:, 1]
        p_pts = (df["winner_rank_points"] / (df["winner_rank_points"] + df["loser_rank_points"])).to_numpy()
        rank_acc = float(np.mean(df["winner_rank"] < df["loser_rank"]))
        res["walk_forward"].append({"año": test, "entrenado": f"{min(data)}-{test - 1}", "modelo": metrics(p_lr),
                                    "formula_puntos": metrics(p_pts), "acierto_mejor_clasificado": rank_acc})
        if test == max(data):
            res["calibracion"][f"walk-forward {test}"] = calibration(p_lr)

    for y in [y for y in data if y >= 2025]:
        p = production_probs(winner_rows(data[y]))
        res["produccion_fuera_de_muestra"].append({"año": y, **metrics(p)})
        res["calibracion"][f"producción {y}"] = calibration(p)

    (HERE / "resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(res)


def pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def num(x: float) -> str:
    return f"{x:.4f}".replace(".", ",")


def write_report(res: dict) -> None:
    L = ["# Idea 31 — Validación honesta del modelo de tenis", "",
         "Solo medición (no cambia el modelo ni los picks). Generado por `run.py` con los CSV de Tennismylife/TML-Database (formato Sackmann; Sackmann ya no está en GitHub).",
         "Una fila por partido; Brier y log-loss: cuanto más bajos, mejor probabilidad. Sin cuotas: no compara con el mercado.", "",
         "## Walk-forward (entrenar con años anteriores, probar en el siguiente)", "",
         "| Año de prueba | Partidos | Acierto modelo | Acierto mejor clasificado | Brier modelo | Brier fórmula puntos | Log-loss modelo |",
         "|---|---|---|---|---|---|---|"]
    for r in res["walk_forward"]:
        m, f = r["modelo"], r["formula_puntos"]
        L.append(f"| {r['año']} | {m['n']} | {pct(m['acierto'])} | {pct(r['acierto_mejor_clasificado'])} | {num(m['brier'])} | "
                 f"{num(f['brier'])} | {num(m['logloss'])} |")
    L += ["", "## Modelo de producción (lr_model.json, entrenado 2018-2024) en años que nunca vio", "",
          "| Año | Partidos | Acierto | Brier | Log-loss |", "|---|---|---|---|---|"]
    for r in res["produccion_fuera_de_muestra"]:
        L.append(f"| {r['año']} | {r['n']} | {pct(r['acierto'])} | {num(r['brier'])} | {num(r['logloss'])} |")
    for name, rows in res["calibracion"].items():
        L += ["", f"## Calibración — {name}", "", "| Prob. del favorito | Partidos | Prob. media dada | Ganó de verdad |", "|---|---|---|---|"]
        L += [f"| {c['tramo']} | {c['n']} | {pct(c['prob_media'])} | {pct(c['real'])} |" for c in rows]
    (HERE / "RESULTADO.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
