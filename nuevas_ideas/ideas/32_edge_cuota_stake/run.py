"""Idea 32 - Edge del pick de tenis contra la cuota de Stake (solo papel; no cambia filtros ni pick).

Hoy el edge del pick diario es model_prob - raw_implied, donde raw_implied es la MEDIA de las casas
(src/pipeline/coordinator.py). Pero se apuesta y se registra a la cuota de Stake. Si Stake paga menos que la media,
un pick puede pasar el filtro de +3 pp y tener EV negativo al precio real.

Para cada pick individual ya liquidado (data/predictions/*.json + data/track_record.json, solo lectura):
  - edge_stake = model_prob - 1/cuota_stake; ¿seguiría pasando el filtro de _MIN_EDGE?
  - ROI a 1 u plana a la cuota de Stake: todos / los que se quedarían / los que se caerían (con IC 95 % bootstrap).
  - Brier de tres probabilidades sobre los mismos picks: la del modelo, la media de casas y la de Stake (1/cuota).

  python run.py
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from src.agents.single_bet_agent import _MIN_EDGE  # noqa: E402


def load() -> list[dict]:
    months = json.loads((ROOT / "data" / "track_record.json").read_text(encoding="utf-8-sig"))["months"]
    result = {}
    for month, m in months.items():
        for day, d in m["days"].items():
            for p in d.get("parlays", []):
                if len(p.get("legs", [])) == 1 and p.get("won") is not None:
                    result[(f"{month}-{int(day):02d}", p["legs"][0])] = p["won"]
    picks = []
    for f in sorted((ROOT / "data" / "predictions").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for parl in doc.get("parlays", []):
            if len(parl.get("picks", [])) != 1:
                continue
            p = parl["picks"][0]
            won = result.get((doc["date"], p["player"]))
            if won is None or not p.get("stake_price"):
                continue
            picks.append({"date": doc["date"], "player": p["player"], "won": bool(won), "model_prob": p["model_prob"],
                          "raw_implied": p["raw_implied"], "edge": p["edge"], "stake": p["stake_price"]})
    return picks


def roi(rows: list[dict]) -> float | None:
    return sum((r["stake"] - 1) if r["won"] else -1 for r in rows) / len(rows) if rows else None


def roi_ci(rows: list[dict], n: int = 5000) -> tuple[float, float] | None:
    if len(rows) < 5:
        return None
    rng = random.Random(42)
    sims = sorted(roi([rng.choice(rows) for _ in rows]) for _ in range(n))
    return sims[int(0.025 * n)], sims[int(0.975 * n)]


def brier(rows: list[dict], key) -> float:
    return sum((key(r) - r["won"]) ** 2 for r in rows) / len(rows)


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:+.1f} %".replace(".", ",")


def main() -> None:
    picks = load()
    for r in picks:
        r["edge_stake"] = r["model_prob"] - 1 / r["stake"]
    keep = [r for r in picks if r["edge_stake"] >= _MIN_EDGE]
    drop = [r for r in picks if r["edge_stake"] < _MIN_EDGE]

    def line(name: str, rows: list[dict]) -> str:
        ci = roi_ci(rows)
        hits = sum(r["won"] for r in rows)
        return (f"| {name} | {len(rows)} | {hits} ({hits / len(rows):.0%}) | {pct(roi(rows))} | "
                f"{'—' if not ci else pct(ci[0]) + ' a ' + pct(ci[1])} |") if rows else f"| {name} | 0 | — | — | — |"

    L = ["# Idea 32 — Edge del pick de tenis contra la cuota de Stake", "",
         f"Solo papel. {len(picks)} picks individuales liquidados con cuota de Stake (de {picks[0]['date']} a {picks[-1]['date']}).",
         f"Filtro actual: edge = prob. del modelo − media de casas ≥ {_MIN_EDGE:.0%}. Alternativa: prob. del modelo − 1/cuota de Stake ≥ {_MIN_EDGE:.0%}.",
         "ROI a 1 u plana a la cuota de Stake; IC 95 % por bootstrap (con tan pocos picks el intervalo es muy ancho).", "",
         "| Grupo | Picks | Aciertos | ROI | IC 95 % del ROI |", "|---|---|---|---|---|",
         line("Todos (regla actual)", picks), line("Se quedarían con la regla Stake", keep), line("Se caerían con la regla Stake", drop), "",
         f"Stake pagó por debajo de la media de casas en {sum(1 / r['stake'] > r['raw_implied'] + 1e-9 for r in picks)} de {len(picks)} picks; "
         f"edge medio: {pct(sum(r['edge'] for r in picks) / len(picks))} contra la media, {pct(sum(r['edge_stake'] for r in picks) / len(picks))} contra Stake.", "",
         "## ¿Qué probabilidad acertó mejor en estos mismos picks? (Brier, más bajo = mejor)", "",
         "| Probabilidad | Brier |", "|---|---|",
         f"| Modelo (la que se publica, ya mezclada con el mercado) | {brier(picks, lambda r: r['model_prob']):.4f} |",
         f"| Media de casas (con margen) | {brier(picks, lambda r: r['raw_implied']):.4f} |",
         f"| Stake (1/cuota, con margen) | {brier(picks, lambda r: 1 / r['stake']):.4f} |", "",
         "## Picks que se caerían", "", "| Día | Jugador | Cuota Stake | Prob. modelo | Edge media | Edge Stake | Resultado |", "|---|---|---|---|---|---|---|"]
    L += [f"| {r['date']} | {r['player']} | {r['stake']:.2f} | {r['model_prob']:.0%} | {pct(r['edge'])} | {pct(r['edge_stake'])} | "
          f"{'ganó' if r['won'] else 'perdió'} |" for r in drop]
    (HERE / "RESULTADO.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
