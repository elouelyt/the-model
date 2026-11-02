#!/usr/bin/env python3
"""Do the combos the extension ranks first (biggest stake) hit more often than the ones it ranks last?

The extension (panel.js) sorts the combos of a tab by probability x odds and sizes the stakes 1.5x / 1.0x / 0.5x of the base % (first, middle,
last; linear for other counts). This script repeats that ranking offline on every settled day, separately for Jev (data/jev_analysis.json) and for
our own bettable combos (nba / nfl / mix analysis, `tracking` False), and compares the rank groups: hit rate, profit at 1 u per combo and
profit weighted by the suggested stake.   python scripts/priority_analysis.py  -> data/priority_analysis.json
"""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "priority_analysis.json"
LABEL = {0: "1.ª (más importe)", 1: "2.ª", 2: "3.ª (menos importe)"}


def weight(i: int, n: int) -> float:
    return 1.5 - i / (n - 1) if n > 1 else 1.0


def ranked(combos: list[dict]) -> list[tuple[int, float, dict]]:
    """[(rank index, stake weight, combo)] per (day, scope) group, best prob x odds first."""
    groups: dict[tuple, list] = defaultdict(list)
    for c in combos:
        groups[(c["date"], c["scope"])].append(c)
    out = []
    for g in groups.values():
        g.sort(key=lambda c: -(c["prob"] * c["odds"]))
        out += [(i, weight(i, len(g)), c) for i, c in enumerate(g)]
    return out


def summarize(rows: list[tuple[int, float, dict]]) -> list[dict]:
    res = []
    for i in (0, 1, 2):
        sel = [(w, c) for r, w, c in rows if (r == i if i < 2 else r >= 2)]
        n = len(sel)
        won = sum(1 for _, c in sel if c["hit"])
        profit = sum(c["odds"] - 1 if c["hit"] else -1 for _, c in sel)
        weighted = sum(w * (c["odds"] - 1 if c["hit"] else -1) for w, c in sel)
        res.append({"rank": LABEL[i], "n": n, "won": won, "hit": round(won / n, 3) if n else None, "profit": round(profit, 2),
                    "weighted": round(weighted, 2), "avg_prob": round(sum(c["prob"] for _, c in sel) / n, 3) if n else None})
    return res


def load(path: str, scope_of) -> list[dict]:
    p = ROOT / path
    if not p.exists():
        return []
    out = []
    for c in json.loads(p.read_text(encoding="utf-8")).get("combos", []):
        if c.get("tracking") or c.get("hit") is None or not c.get("prob"):
            continue
        out.append({"date": c["date"], "scope": scope_of(c), "prob": c["prob"], "odds": c["odds"], "hit": bool(c["hit"])})
    return out


def main() -> None:
    jev = load("data/jev_analysis.json", lambda c: c["families"][0].split(":")[0])
    ours = (load("data/nba_analysis.json", lambda c: "nba") + load("nfl/data/nfl_analysis.json", lambda c: "nfl")
            + load("data/mix_analysis.json", lambda c: "total"))
    doc = {"jev": summarize(ranked(jev)), "ours": summarize(ranked(ours)), "jev_n": len(jev), "ours_n": len(ours)}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(doc)


if __name__ == "__main__":
    main()
