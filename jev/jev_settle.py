#!/usr/bin/env python3
"""Settle Jev's legs and combos (data/jev_history) with ESPN box scores and compare them with our own method, day by day.

Writes data/jev_analysis.json = the usual settlement analysis (calibration, combo families named '<scope>:<family>') plus:
  - brier: Jev's probability vs ours on the very same legs (lower = better calibrated)
  - comparison: per scope (nba / nfl / total) and per day, Jev's bettable combos vs the ones from our rules (same days only)
    python jev/jev_settle.py
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

HISTORY = ROOT / "data" / "jev_history"
ANALYSIS = ROOT / "data" / "jev_analysis.json"
OURS = {"nba": ROOT / "data" / "nba_analysis.json", "nfl": ROOT / "nfl" / "data" / "nfl_analysis.json",
        "total": ROOT / "data" / "mix_analysis.json"}


def settle_file(path: Path, nba: "nba_settle.Espn", nfl: "nfl_settle.Espn") -> int:
    snap = json.loads(path.read_text(encoding="utf-8"))
    results = snap.setdefault("results", {})
    legs = {}
    for run in snap["runs"]:
        for l in run["picks"] + [l for c in run["combos"] for l in c["legs"]]:
            legs.setdefault(l.get("key") or nba_settle_key(l), l)
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


def nba_settle_key(p: dict) -> str:
    return f'{p["start"][:16]}|{p["player"]}|{p["stat"]}|{p["side"]}|{p["line"]}'


def profit(c: dict) -> float:
    if c["void_legs"] == len(c["legs"]):
        return 0.0
    return c["odds"] - 1 if c["hit"] else -1.0


def summary(cs: list[dict]) -> dict:
    n = len(cs)
    p = sum(profit(c) for c in cs)
    return {"n": n, "won": sum(c["hit"] for c in cs), "profit": round(p, 2), "roi": round(p / n, 3) if n else None}


def comparison(analysis: dict) -> dict:
    """Jev vs our rules, only on the days Jev has settled combos."""
    out = {}
    for scope, path in OURS.items():
        ours = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"combos": []}
        jev = [c for c in analysis["combos"] if any(f.startswith(f"{scope}:") for f in c["families"]) and not c["tracking"]]
        days = sorted({c["date"] for c in jev})
        mine = [c for c in ours.get("combos", []) if c["date"] in days and not c["tracking"]]
        per_day = [{"date": d, "jev": summary([c for c in jev if c["date"] == d]), "ours": summary([c for c in mine if c["date"] == d])}
                   for d in days]
        out[scope] = {"jev": summary(jev), "ours": summary(mine), "days": per_day}
    return out


def brier(analysis_legs: list[dict]) -> dict | None:
    rows = [l for l in analysis_legs if l.get("our_prob") is not None]
    if len(rows) < 10:
        return None
    return {"n": len(rows),
            "jev": round(sum((l["win"] - l["ok"]) ** 2 for l in rows) / len(rows), 4),
            "ours": round(sum((l["our_prob"] - l["ok"]) ** 2 for l in rows) / len(rows), 4),
            "hit": round(sum(l["ok"] for l in rows) / len(rows), 3),
            "jev_mean": round(sum(l["win"] for l in rows) / len(rows), 3), "ours_mean": round(sum(l["our_prob"] for l in rows) / len(rows), 3)}


def main() -> None:
    nba, nfl = nba_settle.Espn(), nfl_settle.Espn()
    done = sum(settle_file(p, nba, nfl) for p in sorted(HISTORY.glob("*.json")))
    nba_settle.HISTORY = HISTORY
    analysis = nba_settle.analyse()
    # analyse() drops our_prob: recover it from the snapshots to score both probabilities on the same legs
    ours = {}
    for p in HISTORY.glob("*.json"):
        for run in json.loads(p.read_text(encoding="utf-8"))["runs"]:
            for pk in run["picks"]:
                ours[(p.stem, pk["player"], pk["stat"], pk["side"], pk["line"])] = pk.get("our_prob")
    for l in analysis["legs"]:
        l["our_prob"] = ours.get((l["date"], l["player"], l["stat"], l["side"], l["line"]))
    analysis["brier"] = brier(analysis["legs"])
    analysis["comparison"] = comparison(analysis)
    ANALYSIS.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    print(f"Jev: settled {done} new legs; {analysis['legs_settled']} legs / {analysis['combos_settled']} combos in analysis; brier {analysis['brier']}")


if __name__ == "__main__":
    main()
