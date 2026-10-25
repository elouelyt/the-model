#!/usr/bin/env python3
"""Compare Stake NFL player props with the reference books' no-vig fair odds and list +EV legs.

Same method as scripts/nba_ev.py: fair_prob = average over the reference books of their no-vig probability for the
same line; EV = fair_prob * stake_odds - 1. Reference books for NFL: Pinnacle (public API). Output: nfl/data/nfl_picks.json
"""

import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nba_ev import fair_probs, norm_name  # noqa: E402

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = DATA / "nfl_picks.json"
MIN_EV = 0.003
HIGH_PROB = 0.56
MAX_CACHE_AGE_H = 6
BOOK_FILES = {"Pinnacle": "nfl_pinnacle_cache.json", "BettingPros": "nfl_bettingpros_cache.json"}
SHORT = {"Pinnacle": "PIN", "FanDuel": "FD", "DraftKings": "DK", "Caesars": "CZR", "BetMGM": "MGM", "Novig": "NOV", "ProphetX": "PX",
         "HardRock": "HR", "theScore": "SCR", "Fanatics": "FAN"}
CONS_MAX_AGE_H = 30   # BettingPros consensus is only shown, never used for EV
CONS_AGE_H: float | None = None


def load_books() -> tuple[dict, dict]:
    """((fixture, player, stat, line) -> {book: (over, under)}, same key -> BettingPros consensus (over, under))."""
    global CONS_AGE_H
    index: dict[tuple, dict] = {}
    cons: dict[tuple, tuple[int, int]] = {}
    for book, fname in BOOK_FILES.items():
        path = DATA / fname
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["timestamp"])).total_seconds() / 3600
        stale = age_h > MAX_CACHE_AGE_H
        if stale:
            print(f"[nfl_ev] {fname}: {age_h:.1f} h old -> not used as a reference book")
            if not (book == "BettingPros" and age_h <= CONS_MAX_AGE_H):
                continue
        for r in doc["rows"]:
            if abs(r["over_american"]) > 400 or abs(r["under_american"]) > 400:
                continue
            key = (r["fixture"], norm_name(r["player"]), r["stat"], r["line"])
            if r.get("book") == "Consensus":
                cons[key] = (r["over_american"], r["under_american"])
                CONS_AGE_H = age_h
            elif not stale:
                index.setdefault(key, {})[r.get("book", book)] = (r["over_american"], r["under_american"])
    return index, cons


def build_picks(min_ev: float = MIN_EV) -> tuple[list[dict], list[dict]]:
    stake = json.loads((DATA / "nfl_stake_cache.json").read_text(encoding="utf-8"))
    starts = {g["fixture"]: (g["start"], g["teams"]) for g in stake["games"]}
    index, cons_index = load_books()
    now = datetime.now(timezone.utc)
    upcoming = {fx for fx, (s, _) in starts.items() if parsedate_to_datetime(s) > now}
    picks, high = [], []
    for r in stake["rows"]:
        if r["fixture"] not in upcoming:
            continue
        books = index.get((r["fixture"], norm_name(r["player"]), r["stat"], r["line"]))
        if not books:
            continue
        p_over = sum(fair_probs(o, u)[0] for o, u in books.values()) / len(books)
        cq = cons_index.get((r["fixture"], norm_name(r["player"]), r["stat"], r["line"]))
        cons_over = fair_probs(*cq)[0] if cq else None
        start, teams = starts[r["fixture"]]
        detail = " · ".join(f"{SHORT.get(b, b)} {o:+d}/{u:+d}" for b, (o, u) in books.items())
        for side, prob, odds, opp in (("Over", p_over, r["over"], r["under"]), ("Under", 1 - p_over, r["under"], r["over"])):
            ev = prob * odds - 1
            if not (prob >= HIGH_PROB or ev > min_ev):
                continue
            leg = {"player": r["player"], "team": r["team"], "stat": r["stat"], "line": r["line"], "side": side,
                   "stake_odds": round(odds, 3), "stake_opp": round(opp, 3), "fair_prob": round(prob, 4),
                   "outcome_id": r.get("outcome_id"), "event_id": r.get("event_id"), "fixture": r["fixture"],
                   "fair_odds": round(1 / prob, 3), "ev": round(ev, 4), "fanduel": detail, "books": len(books),
                   "cons_prob": None if cons_over is None else round(cons_over if side == "Over" else 1 - cons_over, 4),
                   "cons_age_h": None if cons_over is None or CONS_AGE_H is None else round(CONS_AGE_H, 1),
                   "game": " vs ".join(teams), "start": start}
            if ev > min_ev:
                picks.append(leg)
            if prob >= HIGH_PROB:
                high.append(leg)
    picks.sort(key=lambda p: p["ev"], reverse=True)
    high.sort(key=lambda p: p["fair_prob"], reverse=True)
    return picks, high


def main() -> None:
    picks, high = build_picks()
    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "min_ev": MIN_EV, "high_prob": high[:120],
                               "picks": picks}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(picks)} NFL picks with EV >= {MIN_EV:.1%}; {len(high)} with fair prob >= {HIGH_PROB:.0%}")
    for p in picks[:15]:
        print(f"{p['fair_prob']:6.1%} EV {p['ev']:+6.1%}  {p['player']:<22} {p['stat']:<20} {p['side']:<5} {p['line']:<6} stake {p['stake_odds']:<6} [{p['books']}] {p['fanduel']}  {p['game']}")


if __name__ == "__main__":
    main()
