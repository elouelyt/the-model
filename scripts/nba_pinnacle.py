#!/usr/bin/env python3
"""Fetch Pinnacle NBA player over/under lines from its public guest API (no Firecrawl, no credits).

Reads data/nba_stake_cache.json to map Pinnacle games to Stake games; writes data/nba_pinnacle_cache.json.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STAKE_CACHE = ROOT / "data" / "nba_stake_cache.json"
OUT = ROOT / "data" / "nba_pinnacle_cache.json"
BASE = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487"  # 487 = NBA
HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}

STATS = {  # suffix of Pinnacle's description -> Stake stat name
    "Total Points": "points",
    "Total Rebounds": "rebounds",
    "Total Assists": "assists",
    "Total Pts & Rebs & Asts": "points+assists+rebounds",
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
        for suffix, stat in STATS.items():
            if desc.endswith(suffix):
                parent = [p["name"] for p in (m.get("parent") or {}).get("participants", [])]
                fixture = game_by_teams.get(nicknames(parent)) if parent else None
                names = {p["id"]: p["name"].lower() for p in m.get("participants", [])}
                if fixture:
                    props[m["id"]] = (fixture, desc[: -len(suffix)].strip(), stat, names)
                break

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
        rows.append({"book": "Pinnacle", "fixture": fixture, "player": player, "stat": stat,
                     "line": float(over["points"]), "over_american": int(over["price"]),
                     "under_american": int(under["price"])})

    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                               "source": "Pinnacle guest API", "rows": rows}, ensure_ascii=False),
                   encoding="utf-8")
    logger.info("Saved %d Pinnacle lines (%d games mapped) to %s", len(rows),
                len({r["fixture"] for r in rows}), OUT)


if __name__ == "__main__":
    main()
