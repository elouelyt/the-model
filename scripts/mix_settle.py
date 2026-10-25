#!/usr/bin/env python3
"""Settle the mixed NBA+NFL combos (data/mix_history) leg by leg with each sport's ESPN box scores and write data/mix_analysis.json.

Each leg carries its `sport`; NBA legs are settled with scripts/nba_settle.py (Espn, settle_leg), NFL legs with nfl/nfl_settle.py.
The NBA analysis (calibration, families, ...) is reused pointed at data/mix_history.   python scripts/mix_settle.py
"""

import json
import sys
from collections import defaultdict
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "nfl"))
import nba_settle  # noqa: E402
import nfl_settle  # noqa: E402

HISTORY = ROOT / "data" / "mix_history"
ANALYSIS = ROOT / "data" / "mix_analysis.json"


def settle_file(path: Path, nba: "nba_settle.Espn", nfl: "nfl_settle.Espn") -> int:
    snap = json.loads(path.read_text(encoding="utf-8"))
    results = snap.setdefault("results", {})
    legs = {}
    for run in snap["runs"]:
        for c in run["combos"]:
            for l in c["legs"]:
                legs.setdefault(l["key"], l)
    by_game: dict[tuple, list] = defaultdict(list)
    for key, leg in legs.items():
        if key not in results:
            by_game[(leg.get("sport", "nba"), leg["game"], leg["start"])].append((key, leg))
    done = 0
    for (sport, game, start), items in by_game.items():
        espn = nba if sport == "nba" else nfl
        ev = espn.find(game.split(" vs "), parsedate_to_datetime(start))
        box = espn.box(ev["id"]) if ev else None
        if box is None:
            continue
        for key, leg in items:
            results[key] = nba_settle.settle_leg(leg, box) if sport == "nba" else nfl_settle.settle_leg(leg, box)
            done += 1
    if done:
        path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return done


def main() -> None:
    nba, nfl = nba_settle.Espn(), nfl_settle.Espn()
    done = sum(settle_file(p, nba, nfl) for p in sorted(HISTORY.glob("*.json")))
    nba_settle.HISTORY = HISTORY
    nba_settle.ANALYSIS = ANALYSIS
    analysis = nba_settle.analyse()
    ANALYSIS.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    print(f"Settled {done} new mixed legs; {analysis['legs_settled']} legs / {analysis['combos_settled']} combos in analysis")


if __name__ == "__main__":
    main()
