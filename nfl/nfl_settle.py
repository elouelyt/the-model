#!/usr/bin/env python3
"""Settle NFL legs and combos with ESPN box scores and write nfl/data/nfl_analysis.json.

Same flow as scripts/nba_settle.py (its analyse() is reused, pointed at nfl/data/nfl_history). A leg is void when the player
does not appear in any box-score category of his game (inactive / did not play); a player who played but has no row in a
category (e.g. a WR with no catches) counts 0. Run: python nfl/nfl_settle.py
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nba_settle  # noqa: E402
from nba_ev import norm_name  # noqa: E402

BASE = Path(__file__).resolve().parent
HISTORY = BASE / "data" / "nfl_history"
ANALYSIS = BASE / "data" / "nfl_analysis.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"


def get(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def nick(team: str) -> str:
    return team.split()[-1].lower()


class Espn:
    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = {}
        self._boxes: dict[str, dict] = {}

    def events(self, yyyymmdd: str) -> list[dict]:
        if yyyymmdd not in self._events:
            self._events[yyyymmdd] = get(f"{ESPN}/scoreboard", {"dates": yyyymmdd}).get("events", [])
        return self._events[yyyymmdd]

    def find(self, teams: list[str], start: datetime) -> dict | None:
        want = frozenset(nick(t) for t in teams)
        for delta in (0, -1, 1):
            for ev in self.events((start + timedelta(days=delta)).strftime("%Y%m%d")):
                if frozenset(nick(c["team"]["displayName"]) for c in ev["competitions"][0]["competitors"]) == want:
                    return ev
        return None

    def box(self, event_id: str) -> dict | None:
        """{norm player: stats} of a FINAL game, or None while it is not over."""
        if event_id in self._boxes:
            return self._boxes[event_id]
        d = get(f"{ESPN}/summary", {"event": event_id})
        comp = d["header"]["competitions"][0]
        if comp["status"]["type"]["name"] != "STATUS_FINAL":
            return None
        players: dict[str, dict] = {}
        for team in d["boxscore"]["players"]:
            for block in team["statistics"]:
                labels = block["labels"]
                for a in block["athletes"]:
                    row = dict(zip(labels, a.get("stats", [])))
                    p = players.setdefault(norm_name(a["athlete"]["displayName"]), {})
                    num = lambda k: float(row[k]) if str(row.get(k, "")).replace("-", "").replace(".", "").isdigit() else 0.0  # noqa: E731
                    if block["name"] == "passing":
                        cmp_, att = (row.get("C/ATT", "0/0").split("/") + ["0"])[:2]
                        p.update({"passing yards": num("YDS"), "passing attempts": float(att or 0), "passing completions": float(cmp_ or 0),
                                  "passing touchdowns": num("TD"), "interceptions": num("INT")})
                    elif block["name"] == "rushing":
                        p.update({"rushing yards": num("YDS"), "rushing attempts": num("CAR")})
                    elif block["name"] == "receiving":
                        p.update({"receiving yards": num("YDS"), "receptions": num("REC")})
        scores = [float(c["score"]) for c in comp["competitors"]]
        players["__game"] = {"margin": abs(scores[0] - scores[1]), "total": sum(scores)}
        self._boxes[event_id] = players
        return players


def settle_leg(leg: dict, players: dict) -> dict:
    game = players.get("__game", {})
    p = players.get(norm_name(leg["player"]))
    if p is None:
        return {"status": "void", "actual": None, "min": None, "margin": game.get("margin"), "total": game.get("total")}
    actual = p.get(leg["stat"], 0.0)
    won = actual > leg["line"] if leg["side"] == "Over" else actual < leg["line"]
    return {"status": "won" if won else "lost", "actual": actual, "min": None, "margin": game.get("margin"), "total": game.get("total")}


def settle_file(path: Path, espn: Espn) -> int:
    snap = json.loads(path.read_text(encoding="utf-8"))
    results = snap.setdefault("results", {})
    legs = {}
    for run in snap["runs"]:
        for p in run["picks"]:
            legs.setdefault(f'{p["start"][:16]}|{p["player"]}|{p["stat"]}|{p["side"]}|{p["line"]}', p)
        for c in run["combos"]:
            for l in c["legs"]:
                legs.setdefault(l["key"], l)
    by_game: dict[tuple, list] = defaultdict(list)
    for key, leg in legs.items():
        if key not in results or results[key].get("margin") is None:   # also re-settle legs stored before the margin was kept
            by_game[(leg["game"], leg["start"])].append((key, leg))
    done = 0
    for (game, start), items in by_game.items():
        ev = espn.find(game.split(" vs "), parsedate_to_datetime(start))
        box = espn.box(ev["id"]) if ev else None
        if box is None:
            continue
        for key, leg in items:
            results[key] = settle_leg(leg, box)
            done += 1
    if done:
        path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return done


def main() -> None:
    espn = Espn()
    done = sum(settle_file(p, espn) for p in sorted(HISTORY.glob("*.json")))
    nba_settle.HISTORY = HISTORY          # reuse the NBA analysis on the NFL history
    nba_settle.ANALYSIS = ANALYSIS
    analysis = nba_settle.analyse()
    ANALYSIS.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    print(f"Settled {done} new NFL legs; {analysis['legs_settled']} legs / {analysis['combos_settled']} combos in analysis")


if __name__ == "__main__":
    main()
