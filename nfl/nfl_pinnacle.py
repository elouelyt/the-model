#!/usr/bin/env python3
"""Fetch Pinnacle NFL player over/under lines from its public guest API (no credits, no login).

Reads nfl/data/nfl_stake_cache.json to map Pinnacle games to Stake fixtures; writes nfl/data/nfl_pinnacle_cache.json
with the same row format as the NBA caches (book, fixture, player, stat, line, over_american, under_american).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STAKE_CACHE = BASE_DIR / "data" / "nfl_stake_cache.json"
OUT = BASE_DIR / "data" / "nfl_pinnacle_cache.json"
BASE = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/889"  # 889 = NFL
HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}

STATS = {  # suffix of Pinnacle's description -> Stake stat name
    "Receptions": "receptions", "Receiving Yards": "receiving yards", "Rushing Yards": "rushing yards",
    "Rush Attempts": "rushing attempts", "Pass Attempts": "passing attempts", "Passing Yards": "passing yards",
    "Pass Completions": "passing completions", "Touchdown Passes": "passing touchdowns", "Interceptions": "interceptions",
}


def nicknames(teams: list[str]) -> frozenset[str]:
    return frozenset(t.split()[-1].lower() for t in teams)


def main() -> None:
    stake = json.loads(STAKE_CACHE.read_text(encoding="utf-8"))
    game_by_teams = {nicknames(g["teams"]): g["fixture"] for g in stake["games"]}
    matchups = requests.get(f"{BASE}/matchups?brandId=0", headers=HEADERS, timeout=30).json()
    markets = requests.get(f"{BASE}/markets/straight", headers=HEADERS, timeout=30).json()

    props = {}
    for m in matchups:
        special = m.get("special") or {}
        if m.get("type") != "special" or special.get("category") != "Player Props":
            continue
        desc = special.get("description", "")
        if " Total " not in desc:
            continue
        player, suffix = desc.rsplit(" Total ", 1)
        stat = STATS.get(suffix.strip())
        if not stat:
            continue
        parent = [p["name"] for p in (m.get("parent") or {}).get("participants", [])]
        fixture = game_by_teams.get(nicknames(parent)) if parent else None
        if fixture:
            props[m["id"]] = (fixture, player.strip(), stat, {p["id"]: p["name"].lower() for p in m.get("participants", [])})

    rows = []
    for mk in markets:
        info = props.get(mk["matchupId"])
        if not info or mk.get("status") not in (None, "open") or mk.get("isAlternate"):
            continue
        fixture, player, stat, names = info
        side = {names.get(p.get("participantId")): p for p in mk["prices"]}
        over, under = side.get("over"), side.get("under")
        if not over or not under or over.get("points") != under.get("points"):
            continue
        rows.append({"book": "Pinnacle", "fixture": fixture, "player": player, "stat": stat, "line": float(over["points"]),
                     "over_american": int(over["price"]), "under_american": int(under["price"])})
    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "source": "Pinnacle guest API",
                               "rows": rows}, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d Pinnacle NFL lines (%d games mapped) to %s", len(rows), len({r["fixture"] for r in rows}), OUT)


if __name__ == "__main__":
    main()
