#!/usr/bin/env python3
"""Collect every settled result (NBA, NFL, mixed NBA+NFL, and the user's own Stake bets) into data/results.json for the 'Resultados' tab.

Reads only the analysis files written by the settlement scripts, plus nuevas_ideas/data/mis_apuestas.json (the user's real bets, local only).
Profit is in units: 1 u per combo at the odds saved when it was published (voided legs are already removed from `odds`).
    python scripts/results_data.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results.json"
SOURCES = {"NBA": ROOT / "data" / "nba_analysis.json", "NFL": ROOT / "nfl" / "data" / "nfl_analysis.json",
           "Mezcla": ROOT / "data" / "mix_analysis.json"}
MINE = ROOT / "nuevas_ideas" / "data" / "mis_apuestas.json"
BASELINE_DAY = "2026-10-23"   # old rules (see CLAUDE.md): kept, shown apart


def combo_profit(c: dict) -> float:
    if c["void_legs"] == len(c["legs"]):
        return 0.0
    return c["odds"] - 1 if c["hit"] else -1.0


def summarize_combos(cs: list[dict]) -> dict:
    n = len(cs)
    wins = sum(c["hit"] for c in cs)
    profit = sum(combo_profit(c) for c in cs)
    return {"n": n, "won": wins, "profit": round(profit, 2), "roi": round(profit / n, 3) if n else None}


def summarize_legs(ls: list[dict]) -> dict:
    n = len(ls)
    if not n:
        return {"n": 0}
    hit = sum(l["ok"] for l in ls)
    prof = sum((l["odds"] - 1) if l["ok"] else -1 for l in ls)
    return {"n": n, "hit": round(hit / n, 3), "expected": round(sum(l["win"] for l in ls) / n, 3), "roi": round(prof / n, 3)}


def sport_block(a: dict) -> dict:
    combos, legs = a.get("combos", []), a.get("legs", [])
    days = sorted({c["date"] for c in combos} | {l["date"] for l in legs})
    per_day = []
    for d in days:
        cs = [c for c in combos if c["date"] == d]
        per_day.append({"date": d, "baseline": d == BASELINE_DAY,
                        "bettable": summarize_combos([c for c in cs if not c["tracking"]]),
                        "tracking": summarize_combos([c for c in cs if c["tracking"]]),
                        "legs": summarize_legs([l for l in legs if l["date"] == d]),
                        "legs54": summarize_legs([l for l in legs if l["date"] == d and l["win"] >= 0.54])})
    cur = [c for c in combos if c["date"] > BASELINE_DAY]
    fam: dict[str, list] = {}
    for c in cur:
        for f in c["families"]:
            fam.setdefault(f, []).append(c)
    cur_legs = [l for l in legs if l["date"] > BASELINE_DAY]

    def group(key, only54=False):
        g: dict[str, list] = {}
        for l in cur_legs:
            if only54 and l["win"] < 0.54:
                continue
            g.setdefault(l[key], []).append(l)
        return sorted(({"name": k, **summarize_legs(v)} for k, v in g.items()), key=lambda r: -r["n"])
    return {"days": per_day,
            "bettable_total": summarize_combos([c for c in cur if not c["tracking"]]),
            "families": sorted(({"name": f, **summarize_combos(v)} for f, v in fam.items()), key=lambda r: -r["n"]),
            "legs_total": summarize_legs(cur_legs), "legs54_total": summarize_legs([l for l in cur_legs if l["win"] >= 0.54]),
            "by_stat": group("stat"), "by_side": group("side"),
            "by_stat54": group("stat", True), "by_side54": group("side", True),
            "tracking_total": summarize_combos([c for c in cur if c["tracking"]])}


def mine() -> dict:
    if not MINE.exists():
        return {}
    raw = json.loads(MINE.read_text(encoding="utf-8"))
    out = {}
    for day, d in raw.items():
        if not isinstance(d, dict):
            continue
        wins = d.get("ganadoras", [])
        profit = sum(w["cuota"] for w in wins) - d["apostadas"]
        out[day] = {"placed": d["apostadas"], "won": len(wins), "profit": round(profit, 2), "roi": round(profit / d["apostadas"], 3),
                    "winners": [{"odds": w["cuota"], "legs": w["legs"], "note": w.get("nota", "")} for w in wins]}
    return out


def main() -> dict:
    doc = {"timestamp": datetime.now(timezone.utc).isoformat(), "baseline_day": BASELINE_DAY, "mine": mine()}
    for name, path in SOURCES.items():
        doc[name] = sport_block(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


if __name__ == "__main__":
    d = main()
    for k in ("NBA", "NFL", "Mezcla"):
        print(k, d[k]["bettable_total"], d[k]["legs54_total"])
    print("mine", d["mine"])
