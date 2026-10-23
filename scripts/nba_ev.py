#!/usr/bin/env python3
"""Compare Stake NBA player props with FanDuel no-vig fair odds and list +EV bets.

Rule (as in the source video): keep sides whose FanDuel no-vig probability is >= 54.34%,
sorted by probability; EV = fair_prob * stake_odds - 1 must be positive. Same line on both books.
Output: data/nba_picks.json
"""

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PROB = 0.5434  # break-even of the 5/6-pick flex: the video's minimum hit rate per leg
MIN_EV = 0.0       # Stake price must beat the fair price
OUT = ROOT / "data" / "nba_picks.json"


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def implied(american: int) -> float:
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def fair_probs(over_am: int, under_am: int) -> tuple[float, float]:
    po, pu = implied(over_am), implied(under_am)
    return po / (po + pu), pu / (po + pu)


def build_picks(min_prob: float = MIN_PROB, min_ev: float = MIN_EV) -> list[dict]:
    stake = json.loads((ROOT / "data" / "nba_stake_cache.json").read_text(encoding="utf-8"))
    fd = json.loads((ROOT / "data" / "nba_fanduel_cache.json").read_text(encoding="utf-8"))
    starts = {g["fixture"]: (g["start"], g["teams"]) for g in stake["games"]}

    fd_index = {(r["fixture"], norm_name(r["player"]), r["stat"], r["line"]): r for r in fd["rows"]}
    picks = []
    for r in stake["rows"]:
        f = fd_index.get((r["fixture"], norm_name(r["player"]), r["stat"], r["line"]))
        if not f:
            continue
        p_over, p_under = fair_probs(f["over_american"], f["under_american"])
        for side, prob, odds in (("Over", p_over, r["over"]), ("Under", p_under, r["under"])):
            ev = prob * odds - 1
            if prob >= min_prob and ev > min_ev:
                start, teams = starts[r["fixture"]]
                picks.append({
                    "player": r["player"], "team": r["team"], "stat": r["stat"], "line": r["line"],
                    "side": side, "stake_odds": round(odds, 3), "fair_prob": round(prob, 4),
                    "fair_odds": round(1 / prob, 3), "ev": round(ev, 4),
                    "fanduel": f"O {f['over_american']:+d} / U {f['under_american']:+d}",
                    "game": " vs ".join(teams), "start": start,
                })
    picks.sort(key=lambda p: p["fair_prob"], reverse=True)
    return picks


def main() -> None:
    min_prob = float(sys.argv[1]) if len(sys.argv) > 1 else MIN_PROB
    picks = build_picks(min_prob)
    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                               "min_prob": min_prob, "min_ev": MIN_EV, "picks": picks}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{len(picks)} picks with fair prob >= {min_prob:.1%} and EV > 0")
    for p in picks[:25]:
        print(f"{p['fair_prob']:6.1%} EV {p['ev']:+6.1%}  {p['player']:<22} {p['stat']:<24} {p['side']:<5} {p['line']:<5} "
              f"stake {p['stake_odds']:<6} fair {p['fair_odds']:<6} FD {p['fanduel']}")


if __name__ == "__main__":
    main()
