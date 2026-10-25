"""NFL version of universe.py: EVERY Stake NFL line of every archived batch (nuevas_ideas/archive/nfl_batches, written by
archive.archive_nfl_batch) with Pinnacle's fair probability at that moment and the real result from the ESPN NFL box score.

    python nuevas_ideas/nfl_universe.py     # download missing NFL box scores, rebuild archive/nfl_universe.jsonl.gz, print the report
Reads only nuevas_ideas/archive/ and ESPN; never touches production files. The report function is shared with the NBA universe.
"""

import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nfl"))
from common import BASE  # noqa: E402
import nba_ev  # noqa: E402
import nfl_settle  # noqa: E402
import universe  # noqa: E402

ARCH = BASE / "archive"
BOX = ARCH / "nfl_boxscores"
UNIVERSE = ARCH / "nfl_universe.jsonl.gz"
MAX_AGE_H = 6.0


def download_boxscores() -> int:
    BOX.mkdir(parents=True, exist_ok=True)
    espn = nfl_settle.Espn()
    new, seen = 0, set()
    for batch in sorted((ARCH / "nfl_batches").glob("*")):
        stake = universe._load(batch / "nfl_stake_cache.json.gz")
        for g in (stake or {}).get("games", []):
            fx = g["fixture"]
            if fx in seen or (BOX / f"{fx}.json").exists():
                continue
            seen.add(fx)
            start = parsedate_to_datetime(g["start"])
            if start > datetime.now(timezone.utc) - timedelta(hours=4):
                continue
            ev = espn.find(g["teams"], start)
            box = espn.box(ev["id"]) if ev else None
            if box is not None:
                (BOX / f"{fx}.json").write_text(json.dumps(box), encoding="utf-8")
                new += 1
    return new


def build() -> list[dict]:
    rows: dict[tuple, dict] = {}
    for batch in sorted((ARCH / "nfl_batches").glob("*")):
        stake = universe._load(batch / "nfl_stake_cache.json.gz")
        pin = universe._load(batch / "nfl_pinnacle_cache.json.gz")
        if not stake or not pin:
            continue
        bt = datetime.fromisoformat(stake["timestamp"])
        if (bt - datetime.fromisoformat(pin["timestamp"])).total_seconds() > MAX_AGE_H * 3600:
            continue
        index = {(r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]): {"Pinnacle": (r["over_american"], r["under_american"])}
                 for r in pin["rows"] if abs(r["over_american"]) <= 400 and abs(r["under_american"]) <= 400}
        starts = {g["fixture"]: (g["start"], g["teams"]) for g in stake["games"]}
        for r in stake["rows"]:
            if r["fixture"] not in starts:
                continue
            start_s, teams = starts[r["fixture"]]
            if parsedate_to_datetime(start_s) < bt + timedelta(minutes=10):
                continue
            books = index.get((r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]))
            if not books:
                continue
            p_over = sum(nba_ev.fair_probs(o, u)[0] for o, u in books.values()) / len(books)
            for side, p, odds, opp in (("Over", p_over, r["over"], r["under"]), ("Under", 1 - p_over, r["under"], r["over"])):
                rows[(r["fixture"], r["player"], r["stat"], r["line"], side)] = {
                    "batch": batch.name, "fixture": r["fixture"], "game": " vs ".join(teams), "start": start_s, "player": r["player"],
                    "stat": r["stat"], "line": r["line"], "side": side, "stake_odds": round(odds, 3), "opp_odds": round(opp, 3),
                    "p": round(p, 4), "books": len(books), "ev": round(p * odds - 1, 4)}
    out = []
    for row in rows.values():
        f = BOX / f'{row["fixture"]}.json'
        if not f.exists():
            continue
        players = json.loads(f.read_text(encoding="utf-8"))
        p = players.get(nba_ev.norm_name(row["player"]))
        if p is None:
            row["status"] = "void"
        else:
            actual = p.get(row["stat"], 0.0)
            row["actual"] = actual
            row["status"] = "won" if (actual > row["line"]) == (row["side"] == "Over") else "lost"
        out.append(row)
    with gzip.open(UNIVERSE, "wt", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    return out


def report(rows: list[dict] | None = None) -> list[str]:
    if rows is None:
        rows = [json.loads(l) for l in gzip.open(UNIVERSE, "rt", encoding="utf-8")] if UNIVERSE.exists() else []
    lines = universe.report(rows)
    return [l.replace("Universo completo: TODAS las líneas de Stake con casas de referencia (archivo por tanda + box scores)",
                      "Universo NFL: TODAS las líneas de Stake con Pinnacle (archivo por tanda + box scores de ESPN)") for l in lines]


if __name__ == "__main__":
    n = download_boxscores()
    rows = build()
    print(f"NFL box scores new: {n}; universe rows: {len(rows)} ({sum(r['status'] != 'void' for r in rows)} settled)")
    print("\n".join(report(rows)))
