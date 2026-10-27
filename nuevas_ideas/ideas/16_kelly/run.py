"""Idea 16 - stake size by confidence (fractional Kelly) instead of a flat amount, on the bettable combos already settled.

Kelly fraction of the bankroll for a bet with win probability p and decimal odds o: f = (p*o - 1) / (o - 1). Quarter Kelly with a 100-unit bankroll gives the
stake in units (capped 2.5 u, floor 0.25 u). Compared with 1 u flat on the same combos (void legs removed, same convention as the Resultados tab).
Paper only: reads the analysis files; writes RESULTADO.md here. The combo probability comes from the same model, so this says how a size rule WOULD have
behaved, not whether the model is right.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import results_data  # noqa: E402

SOURCES = {"NBA": ROOT / "data" / "nba_analysis.json", "NFL": ROOT / "nfl" / "data" / "nfl_analysis.json", "Mezcla": ROOT / "data" / "mix_analysis.json"}
FRACTION, BANK, CAP, FLOOR = 0.25, 100.0, 2.5, 0.25


def stake_units(p: float, odds: float) -> float:
    f = (p * odds - 1) / (odds - 1) if odds > 1 else 0.0
    return min(CAP, max(FLOOR, f * FRACTION * BANK))


def main() -> None:
    if os.environ.get("IDEAS_SPORT", "nba") != "nba":
        return
    lines = ["# Idea 16 - tamaño de apuesta por confianza (Kelly 1/4)", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}. Banco de referencia {BANK:.0f} u, límites {FLOOR}-{CAP} u por apuesta.", "",
             "| Deporte | Combinadas | Plano: u apostadas / resultado | Kelly: u apostadas / resultado | ROI plano | ROI Kelly |", "|---|---|---|---|---|---|"]
    tot = [0, 0.0, 0.0, 0.0, 0.0]
    detail = []
    for name, path in SOURCES.items():
        if not path.exists():
            continue
        combos = [c for c in json.loads(path.read_text(encoding="utf-8")).get("combos", []) if not c.get("tracking") and c["date"] > results_data.BASELINE_DAY and "outcomes" in c and c.get("prob")]
        n, flat_p, ks, kp = 0, 0.0, 0.0, 0.0
        for c in combos:
            pr = results_data.combo_profit(c)
            if pr is None:
                continue
            u = stake_units(c["prob"], c["odds"])
            n += 1; flat_p += pr; ks += u; kp += u * pr
            detail.append((c["date"], name, round(c["odds"], 2), round(c["prob"], 3), round(u, 2), round(pr, 2)))
        if n:
            lines.append(f"| {name} | {n} | {n} u / {flat_p:+.1f} u | {ks:.1f} u / {kp:+.1f} u | {flat_p / n:+.1%} | {kp / ks:+.1%} |")
            tot = [tot[0] + n, tot[1] + flat_p, tot[2] + ks, tot[3] + kp, 0]
    if tot[0]:
        lines.append(f"| **Total** | {tot[0]} | {tot[0]} u / {tot[1]:+.1f} u | {tot[2]:.1f} u / {tot[3]:+.1f} u | {tot[1] / tot[0]:+.1%} | {tot[3] / tot[2]:+.1%} |")
    lines += ["", "Cada combinada: fecha, deporte, cuota, prob. del modelo, unidades Kelly, resultado a 1 u:", ""] + [f"- {d}" for d in detail]
    (HERE / "RESULTADO.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[16_kelly]", lines[-len(detail) - 3] if tot[0] else "sin combinadas")


if __name__ == "__main__":
    main()
