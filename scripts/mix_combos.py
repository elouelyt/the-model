#!/usr/bin/env python3
"""Cross-sport combos: 3 legs that mix NBA and NFL (different games, so independent), chosen with the NBA engine.

Pool = NBA legs under the NBA rule (>= 2 reference books) + NFL legs under the NFL rule (>= 1: Pinnacle). Then scripts/nba_combos.py's
build_combos with its families (probabilidad / valor / mixta), restricted to combos that really mix both sports, plus freeze_combos (a shown
combo stays until its games start) and a daily snapshot in data/mix_history/<date>.json (settled by scripts/mix_settle.py).
Output: data/mix_picks.json = {timestamp, mixed: [...], nba: [...], nfl: [...]} (the sections of the 'Combinadas' tab).
Run after nba_publish / nfl_publish refreshed their picks:  python scripts/mix_combos.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import nba_combos as nc  # noqa: E402

NBA_PICKS = ROOT / "data" / "nba_picks.json"
NFL_PICKS = ROOT / "nfl" / "data" / "nfl_picks.json"
HISTORY = ROOT / "data" / "mix_history"
OUT = ROOT / "data" / "mix_picks.json"
NFL_MIN_BOOKS = 1


def tag(legs: list[dict], sport: str) -> list[dict]:
    return [{**l, "sport": sport} for l in legs]


def main() -> None:
    nba = json.loads(NBA_PICKS.read_text(encoding="utf-8")) if NBA_PICKS.exists() else {"picks": [], "combos": []}
    nfl = json.loads(NFL_PICKS.read_text(encoding="utf-8")) if NFL_PICKS.exists() else {"picks": [], "combos": []}
    pool = (tag([p for p in nba["picks"] if p.get("books", 1) >= nc.MIN_LEG_BOOKS], "nba")
            + tag([p for p in nfl["picks"] if p.get("books", 1) >= NFL_MIN_BOOKS], "nfl"))
    sport_of = {nc.leg_key(p): p["sport"] for p in pool}

    def mixed(c: dict) -> bool:  # c["legs"] are leg keys here
        return len({sport_of[k] for k in c["legs"]}) > 1

    fams = {name: (lambda c, keep=keep: mixed(c) and keep(c), score) for name, (keep, score) in nc.FAMILIES.items()}
    fresh = nc.build_combos(pool, families=fams, min_books=1)
    for c in fresh:
        for l in c["legs"]:
            l["sport"] = sport_of[l["key"]]

    day = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")
    HISTORY.mkdir(parents=True, exist_ok=True)
    snap_path = HISTORY / f"{day}.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {"date": day, "runs": []}
    nba_cache = ROOT / "data" / "nba_stake_cache.json"
    nfl_cache = ROOT / "nfl" / "data" / "nfl_stake_cache.json"
    combos = nc.freeze_combos(fresh, snap, available=nc.available_lines(nba_cache, nfl_cache))
    for c in combos:  # frozen ones keep their stored legs (already tagged)
        for l in c["legs"]:
            l.setdefault("sport", sport_of.get(l["key"], "nba"))

    known = {tuple(sorted(l["key"] for l in c["legs"])) for r in snap["runs"] for c in r["combos"]}
    new = [c for c in combos if tuple(sorted(l["key"] for l in c["legs"])) not in known]
    snap["runs"].append({"at": datetime.now(timezone.utc).isoformat(), "picks": [], "combos": new, "quotes": {}})
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    def sport_combos(doc: dict, sport: str) -> list[dict]:
        return [{**c, "legs": tag(c["legs"], sport)} for c in doc.get("combos", [])]

    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "mixed": combos,
                               "nba": sport_combos(nba, "nba"), "nfl": sport_combos(nfl, "nfl")}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"mix: pool {len(pool)} legs ({sum(v == 'nba' for v in sport_of.values())} NBA / {sum(v == 'nfl' for v in sport_of.values())} NFL); "
          f"{len(combos)} mixed combos ({len(new)} new); NBA combos {len(nba.get('combos', []))}, NFL combos {len(nfl.get('combos', []))}")


if __name__ == "__main__":
    main()
