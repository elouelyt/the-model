#!/usr/bin/env python3
"""Settle recommended legs and combos with real box scores (ESPN) and build the analysis.

Reads data/nba_history/<date>.json (written by nba_combos.py), settles every leg whose game is
final, stores results in the same file under "results" and writes data/nba_analysis.json:
calibration (predicted vs real hit rate), results by market / side / EV bucket / books,
combo results per family and context signals (blowouts, minutes, did-not-play).
"""

import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nba_ev import norm_name  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "nba_history"
ANALYSIS = ROOT / "data" / "nba_analysis.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
BLOWOUT = 18  # final margin from which starters usually sit in the fourth quarter

STAT_COLS = {"points": ["PTS"], "rebounds": ["REB"], "assists": ["AST"],
             "points+rebounds": ["PTS", "REB"], "points+assists": ["PTS", "AST"],
             "assists+rebounds": ["AST", "REB"], "points+assists+rebounds": ["PTS", "AST", "REB"]}


def nick(team: str) -> str:
    return team.split()[-1].lower()


def get(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


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
            day = (start + timedelta(days=delta)).strftime("%Y%m%d")
            for ev in self.events(day):
                names = frozenset(nick(c["team"]["displayName"]) for c in ev["competitions"][0]["competitors"])
                if names == want:
                    return ev
        return None

    def box(self, event_id: str) -> dict | None:
        """Final box score as {norm_name: {min, PTS, REB, AST, dnp}} plus margin/total, or None if not final."""
        if event_id in self._boxes:
            return self._boxes[event_id]
        d = get(f"{ESPN}/summary", {"event": event_id})
        comp = d["header"]["competitions"][0]
        if comp["status"]["type"]["name"] != "STATUS_FINAL":
            return None
        scores = [int(c["score"]) for c in comp["competitors"]]
        players: dict[str, dict] = {}
        for team in d["boxscore"]["players"]:
            for block in team["statistics"]:
                labels = block["labels"]
                for a in block["athletes"]:
                    row = dict(zip(labels, a.get("stats", [])))
                    minutes = int(row["MIN"]) if row.get("MIN", "").isdigit() else 0
                    players[norm_name(a["athlete"]["displayName"])] = {
                        "min": minutes, "dnp": bool(a.get("didNotPlay")) or minutes == 0,
                        **{k: int(row[k]) for k in ("PTS", "REB", "AST") if row.get(k, "").lstrip("-").isdigit()}}
        box = {"players": players, "margin": abs(scores[0] - scores[1]), "total": sum(scores)}
        self._boxes[event_id] = box
        return box


def settle_leg(leg: dict, box: dict) -> dict:
    p = box["players"].get(norm_name(leg["player"]))
    base = {"margin": box["margin"], "total": box["total"]}
    if not p or p["dnp"]:
        return {**base, "status": "void", "actual": None, "min": p["min"] if p else None}
    actual = sum(p.get(c, 0) for c in STAT_COLS[leg["stat"]])
    won = actual > leg["line"] if leg["side"] == "Over" else actual < leg["line"]
    return {**base, "status": "won" if won else "lost", "actual": actual, "min": p["min"]}


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
    done = 0
    by_game: dict[tuple, list] = defaultdict(list)
    for key, leg in legs.items():
        if key not in results:
            by_game[(leg["game"], leg["start"])].append((key, leg))
    for (game, start), items in by_game.items():
        ev = espn.find(game.split(" vs "), parsedate_to_datetime(start))
        box = espn.box(ev["id"]) if ev else None
        if not box:
            continue
        for key, leg in items:
            results[key] = settle_leg(leg, box)
            done += 1
    if done:
        path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return done


def bucket(x: float, edges: list[float], labels: list[str]) -> str:
    for e, lab in zip(edges, labels):
        if x < e:
            return lab
    return labels[-1]


def analyse() -> dict:
    legs, combos = [], []
    for path in sorted(HISTORY.glob("*.json")):
        snap = json.loads(path.read_text(encoding="utf-8"))
        res = snap.get("results", {})
        seen = set()
        for run in snap["runs"]:
            for p in run["picks"]:
                key = f'{p["start"][:16]}|{p["player"]}|{p["stat"]}|{p["side"]}|{p["line"]}'
                if key in res and key not in seen:
                    seen.add(key)
                    legs.append({**p, **res[key], "key": key, "date": snap["date"]})
            for c in run["combos"]:
                outcomes = [res.get(l["key"]) for l in c["legs"]]
                if all(outcomes):
                    live = [(l, o) for l, o in zip(c["legs"], outcomes) if o["status"] != "void"]
                    odds = 1.0
                    for l, _ in live:
                        odds *= l["stake_odds"]
                    hit = bool(live) and all(o["status"] == "won" for _, o in live)
                    combos.append({"date": snap["date"], "families": c["families"], "prob": c["prob"],
                                   "legs": c["legs"], "outcomes": outcomes, "odds": odds if live else 1.0,
                                   "hit": hit, "void_legs": 3 - len(live)})
    played = [l for l in legs if l["status"] != "void"]

    def table(rows: list[dict], keyfn) -> list[dict]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            groups[keyfn(r)].append(r)
        out = []
        for name, rs in sorted(groups.items()):
            hits = sum(r["status"] == "won" for r in rs)
            profit = sum((r["stake_odds"] - 1) if r["status"] == "won" else -1 for r in rs)
            out.append({"name": name, "n": len(rs), "hit": round(hits / len(rs), 3),
                        "expected": round(sum(r["fair_prob"] for r in rs) / len(rs), 3),
                        "roi": round(profit / len(rs), 3)})
        return out

    prob_labels = ["<52%", "52-54%", "54-56%", "56-60%", "60%+"]
    ev_labels = ["<3%", "3-6%", "6-10%", "10%+"]
    blow = [l for l in played if l["margin"] >= BLOWOUT]
    close = [l for l in played if l["margin"] < BLOWOUT]

    def rate(rows: list[dict]) -> float | None:
        return round(sum(r["status"] == "won" for r in rows) / len(rows), 3) if rows else None

    fam: dict[str, list[dict]] = defaultdict(list)
    for c in combos:
        for f in c["families"]:
            fam[f].append(c)
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "legs_settled": len(played), "legs_void": len(legs) - len(played), "combos_settled": len(combos),
        "calibration": table(played, lambda r: bucket(r["fair_prob"], [0.52, 0.54, 0.56, 0.60], prob_labels)),
        "by_stat": table(played, lambda r: r["stat"]),
        "by_side": table(played, lambda r: r["side"]),
        "by_ev": table(played, lambda r: bucket(r["ev"], [0.03, 0.06, 0.10], ev_labels)),
        "by_books": table(played, lambda r: f'{r.get("books", 1)} casa(s)'),
        "context": {
            "blowout_threshold": BLOWOUT,
            "over_blowout": rate([l for l in blow if l["side"] == "Over"]), "over_close": rate([l for l in close if l["side"] == "Over"]),
            "under_blowout": rate([l for l in blow if l["side"] == "Under"]), "under_close": rate([l for l in close if l["side"] == "Under"]),
            "n_blowout": len(blow), "n_close": len(close),
        },
        "combo_families": [
            {"name": f, "n": len(cs), "hits": sum(c["hit"] for c in cs),
             "roi": round(sum((c["odds"] - 1) if c["hit"] else -1 for c in cs) / len(cs), 3),
             "expected_hit": round(sum(c["prob"] for c in cs) / len(cs), 3)} for f, cs in sorted(fam.items())],
        "combos": combos[-30:],
    }


def main() -> None:
    espn = Espn()
    total = 0
    for path in sorted(HISTORY.glob("*.json")):
        try:
            total += settle_file(path, espn)
        except Exception as exc:  # noqa: BLE001
            logger.warning("settle %s failed: %s", path.name, str(exc)[:120])
    analysis = analyse()
    ANALYSIS.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    logger.info("Settled %d new legs; %d legs / %d combos in analysis", total,
                analysis["legs_settled"], analysis["combos_settled"])


if __name__ == "__main__":
    main()
