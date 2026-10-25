#!/usr/bin/env python3
"""Build 3-leg NFL combos from nfl/data/nfl_picks.json and snapshot the slate (same rules as scripts/nba_combos.py).

Production NBA rules reused through nba_combos.build_combos: legs with win >= 54 % and EV > 0.5 %, games not started, one leg per player,
max 2 legs per game, families probabilidad / valor / mixta, plus paper (tracking) combos with started games. For NFL the only
reference book is Pinnacle (1 book), so the '>= 2 books' rule is relaxed to 1 book until BettingPros / FanDuel are added.
Output: merged into nfl/data/nfl_picks.json; snapshot in nfl/data/nfl_history/<date>.json (settled by nfl_settle.py).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nba_combos as nc  # noqa: E402

BASE = Path(__file__).resolve().parent
PICKS = BASE / "data" / "nfl_picks.json"
HISTORY = BASE / "data" / "nfl_history"
MIN_BOOKS = 1


def main() -> None:
    doc = json.loads(PICKS.read_text(encoding="utf-8"))
    combos = nc.build_combos(doc["picks"], min_books=MIN_BOOKS)
    day = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")
    HISTORY.mkdir(parents=True, exist_ok=True)
    snap_path = HISTORY / f"{day}.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {"date": day, "runs": []}
    combos = nc.freeze_combos(combos, snap)  # a combo already shown stays until its games start
    for c in combos:
        for l in c["legs"]:
            if not l.get("fixture"):
                l["fixture"] = next((p.get("fixture") for p in doc["picks"] if nc.leg_key(p) == l["key"]), None)

    pool = {nc.leg_key(p): p for r in snap["runs"] for p in r["picks"]}
    pool.update({nc.leg_key(p): p for p in doc["picks"]})
    tracking = []
    if doc["picks"]:
        tracking = nc.build_combos(list(pool.values()), tracking=True, per_family=nc.TRACKING_PER_FAMILY,
                                   game_cap=nc.TRACKING_GAME_CAP, min_books=MIN_BOOKS)
        pure = nc.build_combos(doc.get("high_prob", []), tracking=True, per_family=nc.TRACKING_PER_FAMILY, min_leg_ev=-1.0,
                               families={"pura": (lambda c: True, lambda c: c["prob"])}, future_only=True, min_leg_prob=0.0,
                               game_cap=nc.TRACKING_GAME_CAP, min_books=MIN_BOOKS)
        tracking += pure
    doc["combos"], doc["combos_tracking"] = combos, tracking
    PICKS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    known_legs = {nc.leg_key(p) for r in snap["runs"] for p in r["picks"]}
    known_combos = {tuple(sorted(l["key"] for l in c["legs"])) for r in snap["runs"] for c in r["combos"]}
    extras = [{**p, "extra": True} for p in doc.get("high_prob", []) if nc.leg_key(p) not in {nc.leg_key(q) for q in doc["picks"]}]
    new_picks = [p for p in doc["picks"] + extras if nc.leg_key(p) not in known_legs]
    new_combos = [c for c in combos + tracking if tuple(sorted(l["key"] for l in c["legs"])) not in known_combos]
    quotes = {nc.leg_key(p): [p["stake_odds"], p.get("stake_opp"), p["fair_prob"]] for p in doc["picks"]}
    snap["runs"].append({"at": doc["timestamp"], "picks": new_picks, "combos": new_combos, "quotes": quotes})
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    print(f"{len(combos)} bettable NFL combos + {len(tracking)} tracking combos (new: {len(new_combos)}), snapshot {snap_path.name}")


if __name__ == "__main__":
    main()
