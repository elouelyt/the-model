"""Idea 14 - CLV against SHARP references (FanDuel / Pinnacle / Novig / BettingPros, no vig), not against Stake's own close.

For every Stake line that appears in two or more archived batches of the same day: the first batch is "when we would have bet", the last batch
before the game is "the close". Measured: how the reference fair probability moved, and the EV of the first Stake price judged with the closing
fair probability (EV_close = odds_first * p_close - 1). Positive on average = we get better prices than the sharp market ends up believing.
Paper only: reads nuevas_ideas/archive/batches (written by archive.py); writes RESULTADO.md in this folder.
"""

import os
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import BASE, ROOT  # noqa: E402
import nba_ev  # noqa: E402
import universe  # noqa: E402

HERE = Path(__file__).resolve().parent


def snapshots() -> dict:
    """(fixture, player, stat, line, side) -> [(batch_time, p, stake_odds, books)] in time order, only lines still open at that batch."""
    out: dict[tuple, list] = {}
    for batch in sorted((BASE / "archive" / "batches").glob("*")):
        stake = universe._load(batch / "nba_stake_cache.json.gz")
        if not stake:
            continue
        bt = datetime.fromisoformat(stake["timestamp"])
        starts = {g["fixture"]: g["start"] for g in stake["games"]}
        index = universe.batch_books(batch, bt)
        for r in stake["rows"]:
            if r["stat"] not in nba_ev.ALLOWED_STATS or r["fixture"] not in starts:
                continue
            if parsedate_to_datetime(starts[r["fixture"]]) < bt:
                continue
            books = index.get((r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]))
            if not books:
                continue
            p_over = sum(nba_ev.fair_probs(o, u)[0] for o, u in books.values()) / len(books)
            for side, p, odds in (("Over", p_over, r["over"]), ("Under", 1 - p_over, r["under"])):
                out.setdefault((r["fixture"], r["player"], r["stat"], r["line"], side), []).append((bt, p, odds, len(books)))
    return out


def report() -> list[str]:
    snaps = snapshots()
    pairs = {k: v for k, v in snaps.items() if len(v) >= 2 and (v[-1][0] - v[0][0]).total_seconds() >= 1800}
    lines = ["# Idea 14 - CLV contra casas sharp", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}. Líneas con 2+ tandas separadas >= 30 min: {len(pairs)} (de {len(snaps)}).", ""]
    if not pairs:
        return lines + ["Aún sin pares: hace falta una tanda tardía cerca del inicio (tarea `TheModel-Ideas-Tarde-Late`). Se rellena sola cada noche."]

    def row(name: str, ks: list) -> str:
        if len(ks) < 5:
            return ""
        d = [pairs[k][-1][1] - pairs[k][0][1] for k in ks]
        ev = [pairs[k][0][2] * pairs[k][-1][1] - 1 for k in ks]
        return f"| {name} | {len(ks)} | {sum(d) / len(d) * 100:+.2f} | {sum(ev) / len(ev) * 100:+.2f} % | {sum(x > 0 for x in ev) / len(ev):.0%} |"
    rec = [k for k, v in pairs.items() if v[0][1] >= 0.54 and v[0][1] * v[0][2] - 1 > 0.005 and v[0][3] >= 2]
    lines += ["| Grupo | Líneas | Cambio de prob. justa (pts) | EV con prob. de cierre | % con EV > 0 |", "|---|---|---|---|---|",
              row("todas las líneas", list(pairs)), row("las que producción recomendaría (p>=54 %, EV>0,5 %, >=2 casas)", rec),
              row("Over (recomendables)", [k for k in rec if k[4] == "Over"]), row("Under (recomendables)", [k for k in rec if k[4] == "Under"])]
    lines += ["", "Lectura: EV con prob. de cierre > 0 de forma sostenida (cientos de líneas) = compramos mejor que el mercado sharp al cierre = ventaja real. ~0 = no la hay (o no se mide aún)."]
    return [l for l in lines if l is not None]


def main() -> None:
    if os.environ.get("IDEAS_SPORT", "nba") != "nba":
        return
    text = "\n".join(l for l in report() if l != "")
    (HERE / "RESULTADO.md").write_text(text + "\n", encoding="utf-8")
    print("[14_clv_sharp]", text.splitlines()[2] if len(text.splitlines()) > 2 else text)


if __name__ == "__main__":
    main()
