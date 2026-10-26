#!/usr/bin/env python3
"""Idea 10: how often does a team lead by 16+ at half and lose (the Stake NBA 'half-time refund' promo)?

Reads ESPN scoreboards (public) day by day for a date range and writes history/halftime_games.json.
    python halftime_backtest.py 20251021 20260412
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "data"
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"


def main(start: str, end: str) -> None:
    OUT.mkdir(exist_ok=True)
    cache = OUT / "halftime_games.json"
    games = {g["id"]: g for g in json.loads(cache.read_text(encoding="utf-8"))} if cache.exists() else {}
    d, last = datetime.strptime(start, "%Y%m%d"), datetime.strptime(end, "%Y%m%d")
    while d <= last:
        try:
            ev = requests.get(URL.format(d=d.strftime("%Y%m%d")), timeout=20).json().get("events", [])
        except Exception:  # noqa: BLE001
            ev = []
        for e in ev:
            c = e["competitions"][0]
            if not e["status"]["type"]["completed"] or e["id"] in games or len(c["competitors"]) != 2:
                continue
            try:
                t = {x["homeAway"]: x for x in c["competitors"]}
                half = {k: sum(float(p["value"]) for p in v["linescores"][:2]) for k, v in t.items()}
                games[e["id"]] = {"id": e["id"], "date": d.strftime("%Y-%m-%d"), "half": half,
                                  "final": {k: float(v["score"]) for k, v in t.items()},
                                  "ot": len(t["home"]["linescores"]) > 4}
            except (KeyError, ValueError):
                continue
        d += timedelta(days=1)
        time.sleep(0.15)
    cache.write_text(json.dumps(list(games.values())), encoding="utf-8")
    rows = list(games.values())
    lead = [r for r in rows if abs(r["half"]["home"] - r["half"]["away"]) >= 16]
    lost = [r for r in lead if (r["half"]["home"] > r["half"]["away"]) != (r["final"]["home"] > r["final"]["away"])]
    print(f"games {len(rows)} | half-time lead >= 16: {len(lead)} ({len(lead)/max(len(rows),1):.1%}) | led and lost: {len(lost)} "
          f"({len(lost)/max(len(rows),1):.2%} of games, {len(lost)/max(len(lead),1):.1%} of leaders)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
