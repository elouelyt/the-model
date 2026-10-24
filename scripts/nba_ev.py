#!/usr/bin/env python3
"""Compare Stake NBA player props with FanDuel no-vig fair odds and list +EV bets.

Rule (as in the source video's feed): list every side with positive EV, sorted by EV% descending;
EV = fair_prob * stake_odds - 1 with FanDuel's no-vig probability, same line on both books.
Output: data/nba_picks.json
"""

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIGH_PROB = 0.56   # pool for the "pure probability" paper family (EV ignored)
MIN_PROB = 0.0     # his feed shows win% from ~53%; no probability cut-off
MIN_EV = 0.003     # his feed lists +EV down to ~0.3%
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


# Markets used in the source videos (no threes): points, rebounds, assists and their combos
ALLOWED_STATS = {"points", "rebounds", "assists", "points+rebounds", "points+assists",
                 "assists+rebounds", "points+assists+rebounds"}
BOOK_FILES = {  # later files override earlier ones for the same book (fresher, broader sources last)
    "FanDuel": "nba_fanduel_cache.json",      # Firecrawl, optional
    "Pinnacle": "nba_pinnacle_cache.json",    # direct public API
    "BettingPros": "nba_bettingpros_cache.json",  # rows carry their own "book"
}
SHORT = {"FanDuel": "FD", "Pinnacle": "PIN", "DraftKings": "DK", "Caesars": "CZR", "BetMGM": "MGM",
         "Novig": "NOV", "ProphetX": "PX"}


def load_books() -> tuple[dict, dict]:
    """((fixture, player, stat, line) -> {book: (over, under)} for reference books, same key -> consensus quote)."""
    index: dict[tuple, dict[str, tuple[int, int]]] = {}
    cons: dict[tuple, tuple[int, int]] = {}
    for book, fname in BOOK_FILES.items():
        path = ROOT / "data" / fname
        if not path.exists():
            continue
        for r in json.loads(path.read_text(encoding="utf-8"))["rows"]:
            if abs(r["over_american"]) > 400 or abs(r["under_american"]) > 400:  # placeholder quotes
                continue
            key = (r["fixture"], norm_name(r["player"]), r["stat"], r["line"])
            name = r.get("book", book)
            if name == "Consensus":
                cons[key] = (r["over_american"], r["under_american"])
            else:
                index.setdefault(key, {})[name] = (r["over_american"], r["under_american"])
    return index, cons


def build_picks(min_prob: float = MIN_PROB, min_ev: float = MIN_EV, with_high: bool = False):
    stake = json.loads((ROOT / "data" / "nba_stake_cache.json").read_text(encoding="utf-8"))
    starts = {g["fixture"]: (g["start"], g["teams"]) for g in stake["games"]}
    index, cons_index = load_books()
    now = datetime.now(timezone.utc)
    upcoming = {fx for fx, (start, _) in starts.items() if parsedate_to_datetime(start) > now}

    picks, high = [], []
    for r in stake["rows"]:
        if r["stat"] not in ALLOWED_STATS or r["fixture"] not in upcoming:
            continue
        books = index.get((r["fixture"], norm_name(r["player"]), r["stat"], r["line"]))
        if not books:
            continue
        probs = [fair_probs(o, u) for o, u in books.values()]
        p_over = sum(p[0] for p in probs) / len(probs)  # average of each book's no-vig probability
        cq = cons_index.get((r["fixture"], norm_name(r["player"]), r["stat"], r["line"]))
        cons_over = fair_probs(*cq)[0] if cq else None  # BettingPros consensus, for comparison only
        for side, prob, odds, opp in (("Over", p_over, r["over"], r["under"]), ("Under", 1 - p_over, r["under"], r["over"])):
            ev = prob * odds - 1
            if not (prob >= HIGH_PROB or (prob >= min_prob and ev > min_ev)):
                continue
            start, teams = starts[r["fixture"]]
            detail = " · ".join(f"{SHORT[b]} {o:+d}/{u:+d}" for b, (o, u) in books.items())
            leg = {
                "player": r["player"], "team": r["team"], "stat": r["stat"], "line": r["line"],
                "side": side, "stake_odds": round(odds, 3), "stake_opp": round(opp, 3), "fair_prob": round(prob, 4),
                "fair_odds": round(1 / prob, 3), "ev": round(ev, 4),
                "cons_prob": None if cons_over is None else round(cons_over if side == "Over" else 1 - cons_over, 4),
                "fanduel": detail, "books": len(books),
                "game": " vs ".join(teams), "start": start,
            }
            if prob >= min_prob and ev > min_ev:
                picks.append(leg)
            if prob >= HIGH_PROB:
                high.append(leg)
    picks.sort(key=lambda p: p["ev"], reverse=True)
    high.sort(key=lambda p: p["fair_prob"], reverse=True)
    return (picks, high) if with_high else picks


def main() -> None:
    min_prob = float(sys.argv[1]) if len(sys.argv) > 1 else MIN_PROB
    picks, high = build_picks(min_prob, with_high=True)
    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                               "min_prob": min_prob, "min_ev": MIN_EV, "high_prob": high[:80], "picks": picks}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{len(picks)} picks with EV >= {MIN_EV:.1%}")
    for p in picks[:25]:
        print(f"{p['fair_prob']:6.1%} EV {p['ev']:+6.1%}  {p['player']:<22} {p['stat']:<24} {p['side']:<5} {p['line']:<5} "
              f"stake {p['stake_odds']:<6} fair {p['fair_odds']:<6} [{p['books']}] {p['fanduel']}")


if __name__ == "__main__":
    main()
