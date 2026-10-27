"""Idea 15 - weight each reference book by how much margin (overround) it charges, instead of a plain average of no-vig probabilities.

Production: p = mean over books of the no-vig probability. Here: weights w = 1/overround^k (k=4 hits the vig-width idea: a book that charges
more margin is less sure of the line). Compared on every settled Stake line of the archive (universe): Brier score and log-loss of p_equal vs p_weighted,
and the hit rate of the lines each method would select (p >= 54 %, EV > 0.5 %, >= 2 books). Paper only; writes RESULTADO.md here.
"""

import math
import os
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import BASE  # noqa: E402
import nba_ev  # noqa: E402
import universe  # noqa: E402
import json  # noqa: E402

HERE = Path(__file__).resolve().parent
K = 4


def rows() -> list[dict]:
    out = {}
    for batch in sorted((BASE / "archive" / "batches").glob("*")):
        stake = universe._load(batch / "nba_stake_cache.json.gz")
        if not stake:
            continue
        bt = datetime.fromisoformat(stake["timestamp"])
        starts = {g["fixture"]: g["start"] for g in stake["games"]}
        index = universe.batch_books(batch, bt)
        for r in stake["rows"]:
            if r["stat"] not in nba_ev.ALLOWED_STATS or r["fixture"] not in starts or parsedate_to_datetime(starts[r["fixture"]]) < bt:
                continue
            books = index.get((r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]))
            if not books or len(books) < 2:
                continue
            ps, ws = [], []
            for o, u in books.values():
                over_p = nba_ev.fair_probs(o, u)[0]
                overround = nba_ev.implied(o) + nba_ev.implied(u)
                ps.append(over_p)
                ws.append(1 / overround ** K)
            p_eq = sum(ps) / len(ps)
            p_w = sum(p * w for p, w in zip(ps, ws)) / sum(ws)
            spread = max(ps) - min(ps)
            out[(r["fixture"], r["player"], r["stat"], r["line"])] = {"fixture": r["fixture"], "player": r["player"], "stat": r["stat"], "line": r["line"],
                "p_eq": p_eq, "p_w": p_w, "spread": spread, "n": len(books), "over": r["over"], "under": r["under"]}
    res = []
    for r in out.values():
        f = universe.BOX / f'{r["fixture"]}.json'
        if not f.exists():
            continue
        box = json.loads(f.read_text(encoding="utf-8"))
        pl = box["players"].get(nba_ev.norm_name(r["player"]))
        if not pl or pl["dnp"]:
            continue
        actual = sum(pl.get(c, 0) for c in universe.nba_settle.STAT_COLS[r["stat"]])
        if actual == r["line"]:
            continue
        r["y"] = 1.0 if actual > r["line"] else 0.0
        res.append(r)
    return res


def main() -> None:
    if os.environ.get("IDEAS_SPORT", "nba") != "nba":
        return
    rs = rows()
    lines = ["# Idea 15 - consenso ponderado por margen", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}. Líneas liquidadas con >= 2 casas: {len(rs)}.", ""]
    if len(rs) < 30:
        lines.append("Aún pocas líneas liquidadas.")
    else:
        def brier(key): return sum((r[key] - r["y"]) ** 2 for r in rs) / len(rs)
        def ll(key): return -sum(math.log(max(min(r[key], 0.999), 0.001) if r["y"] else max(min(1 - r[key], 0.999), 0.001)) for r in rs) / len(rs)
        lines += ["| Método | Brier (menor = mejor) | Log-loss |", "|---|---|---|",
                  f"| media simple (producción) | {brier('p_eq'):.4f} | {ll('p_eq'):.4f} |", f"| ponderada por 1/margen^{K} | {brier('p_w'):.4f} | {ll('p_w'):.4f} |", ""]
        def sel(key):
            out = []
            for r in rs:
                p = r[key]
                for side, ps, odds, hit in (("Over", p, r["over"], r["y"]), ("Under", 1 - p, r["under"], 1 - r["y"])):
                    if ps >= 0.54 and ps * odds - 1 > 0.005:
                        out.append((hit, odds, ps))
            return out
        lines += ["| Selección (p>=54 %, EV>0,5 %) | Líneas | Acierto | Esperado | ROI plano |", "|---|---|---|---|---|"]
        for name, key in (("media simple", "p_eq"), (f"ponderada", "p_w")):
            s = sel(key)
            if s:
                n = len(s)
                lines.append(f"| {name} | {n} | {sum(h for h, _, _ in s) / n:.1%} | {sum(p for _, _, p in s) / n:.1%} | {sum((o - 1) if h else -1 for h, o, _ in s) / n:+.1%} |")
        agree = [r for r in rs if r["spread"] <= 0.04]
        lines += ["", f"Casas que coinciden (dispersión <= 4 pts): {len(agree)} líneas de {len(rs)}."]
    text = "\n".join(lines) + "\n"
    (HERE / "RESULTADO.md").write_text(text, encoding="utf-8")
    print("[15_consenso_ponderado]", lines[2])


if __name__ == "__main__":
    main()
