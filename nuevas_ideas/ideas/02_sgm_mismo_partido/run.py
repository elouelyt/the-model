"""Idea 02 - combinadas del MISMO PARTIDO con el precio del constructor de Stake (SGM).

Why: measured on 24-25/10 with Stake's own price query (calculateSwishCustomBet) - the same-game builder prices
2 legs at ~0.90-0.96 of the no-margin product (one margin for the whole bet), while a normal multi of the displayed
odds carries the margin of every leg. Stake also adjusts for correlation: it blocks some pairs ('invalidCombinations')
and prices same-team over/over lighter (x0.96) than over/under (x0.88).
Our own data (ESPN game logs 2025-26, ideas/05) says teammate correlation is ~0, so we value a combo as
    EV = prod(reference-book fair probability of each leg) * SGM odds - 1      (independence)
Paper only: legs from the same game, one leg per player, top legs by fair probability, pairs and triples,
only combinations Stake prices without 'invalidCombinations'. Settled like the production combos, except that a
voided leg voids the whole SGM (Stake rule), see settle_ideas.py.

Needs the debug Chrome with a stake.com tab (like the production batches); read-only price queries, no login.
"""

import itertools
import json
import os
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import BASE, STAKE_CACHE, StakePage, combo_from_legs, save_combos  # noqa: E402
import nba_ev  # noqa: E402

IDEA = "02_sgm_mismo_partido"
MIN_PROB = 0.52     # a leg's reference-book fair probability
TOP_SINGLES = 24    # legs per game whose single (no-margin) price is queried
TOP_PAIR = 12       # legs per game (best edge first) used for pairs
TOP_TRIPLE = 8      # legs per game used for triples
MIN_BOOKS = 2
TEST = bool(os.environ.get("IDEAS_TEST"))   # include started games, 1 game only, write nothing to the history


def candidate_legs() -> dict[str, list[dict]]:
    stake = json.loads(STAKE_CACHE.read_text(encoding="utf-8"))
    starts = {g["fixture"]: (g["start"], g["teams"]) for g in stake["games"]}
    limit = datetime.now(timezone.utc) + timedelta(minutes=15)
    upcoming = {fx for fx, (s, _) in starts.items() if TEST or parsedate_to_datetime(s) > limit}
    index, _ = nba_ev.load_books()
    best: dict[tuple, dict] = {}
    for r in stake["rows"]:
        if r["stat"] not in nba_ev.ALLOWED_STATS or r["fixture"] not in upcoming or not r.get("outcome_id"):
            continue
        books = index.get((r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]))
        if not books or len(books) < MIN_BOOKS:
            continue
        p_over = sum(nba_ev.fair_probs(o, u)[0] for o, u in books.values()) / len(books)
        start, teams = starts[r["fixture"]]
        for side, p, odds in (("Over", p_over, r["over"]), ("Under", 1 - p_over, r["under"])):
            if p < MIN_PROB:
                continue
            leg = {"player": r["player"], "team": r["team"], "stat": r["stat"], "line": r["line"], "side": side,
                   "stake_odds": round(odds, 3), "fair_prob": round(p, 4), "ev": round(p * odds - 1, 4),
                   "game": " vs ".join(teams), "start": start, "fixture": r["fixture"],
                   "outcome_id": r["outcome_id"], "line_type": side.lower(), "books": len(books)}
            key = (r["fixture"], r["player"])
            if key not in best or p > best[key]["fair_prob"]:
                best[key] = leg
    by_fx: dict[str, list[dict]] = {}
    if TEST:
        best = {k: v for k, v in best.items() if k[0] == next(iter(sorted({k2[0] for k2 in best})), None)}
    for (fx, _), leg in best.items():
        by_fx.setdefault(fx, []).append(leg)
    for fx in by_fx:
        by_fx[fx].sort(key=lambda l: -l["fair_prob"])
    return by_fx


def rank_by_edge(page: "StakePage", legs_by_fx: dict[str, list[dict]]) -> None:
    """Stake's own no-margin price of each single leg (same query with one line); edge = fair_prob * that price - 1.
    Legs are then sorted by that edge: the SGM margin (~9 %) is only beaten by legs the reference books rate
    above Stake's model, not simply by the most probable ones."""
    todo = [(fx, l) for fx, legs in legs_by_fx.items() for l in legs[:TOP_SINGLES]]
    prices = page.sgm_prices([[[l["outcome_id"], l["line_type"]]] for _, l in todo])
    for (_, l), r in zip(todo, prices):
        l["fair_single"] = r["odds"] if r and r.get("odds") and not r.get("invalid") else None
        l["edge"] = round(l["fair_prob"] * l["fair_single"] - 1, 4) if l["fair_single"] else -1.0
    for fx in legs_by_fx:
        legs_by_fx[fx] = sorted([l for l in legs_by_fx[fx][:TOP_SINGLES] if l.get("fair_single")], key=lambda l: -l["edge"])


def main() -> None:
    legs_by_fx = candidate_legs()
    if not legs_by_fx:
        print(f"[{IDEA}] no upcoming games with reference lines")
        return
    page = StakePage()
    rank_by_edge(page, legs_by_fx)
    jobs: list[tuple[str, tuple]] = []   # (fixture, legs)
    for fx, legs in legs_by_fx.items():
        for n, top in ((2, TOP_PAIR), (3, TOP_TRIPLE)):
            for combo in itertools.combinations(legs[:top], n):
                jobs.append((fx, combo))
    print(f"[{IDEA}] {len(legs_by_fx)} games, {len(jobs)} combination price queries", flush=True)
    prices = page.sgm_prices([[[l["outcome_id"], l["line_type"]] for l in legs] for _, legs in jobs])

    evaluated = []
    for (fx, legs), r in zip(jobs, prices):
        if not r or r.get("invalid") or not r.get("odds"):
            evaluated.append({"fixture": fx, "n": len(legs), "valid": False, "keys": [f"{l['player']}|{l['stat']}|{l['side']}|{l['line']}" for l in legs]})
            continue
        prob = 1.0
        multi = 1.0
        for l in legs:
            prob *= l["fair_prob"]
            multi *= l["stake_odds"]
        evaluated.append({"fixture": fx, "n": len(legs), "valid": True, "sgm_odds": r["odds"], "multi_odds": round(multi, 3),
                          "prob": round(prob, 4), "ev_sgm": round(prob * r["odds"] - 1, 4), "ev_multi": round(prob * multi - 1, 4),
                          "legs": legs})
    ok = [e for e in evaluated if e["valid"]]
    cdir = BASE / "ideas" / IDEA / "candidates"
    cdir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    if not TEST:
        (cdir / f"{stamp}.json").write_text(json.dumps(evaluated, ensure_ascii=False), encoding="utf-8")
    if not ok:
        print(f"[{IDEA}] no valid SGM price")
        return

    combos = []
    for fx in legs_by_fx:
        mine = [e for e in ok if e["fixture"] == fx]   # any EV sign: the 7-day test also checks the independence assumption
        picked: set[tuple] = set()
        for fam, key in (("sgm_ev", lambda e: e["ev_sgm"]), ("sgm_prob", lambda e: e["prob"])):
            n = 0
            for e in sorted(mine, key=key, reverse=True):
                ident = tuple(sorted(l["player"] for l in e["legs"]))
                if ident in picked:
                    continue
                picked.add(ident)
                combos.append(combo_from_legs(e["legs"], [fam], e["sgm_odds"], e["prob"],
                                              {"sgm": True, "odds_multi": e["multi_odds"], "ev_multi": e["ev_multi"]}))
                n += 1
                if n == 2:
                    break
    evs = [e["ev_sgm"] for e in ok]
    better = sum(e["ev_sgm"] > e["ev_multi"] for e in ok)
    print(f"[{IDEA}] valid {len(ok)}/{len(evaluated)}; EV_sgm median {st.median(evs):+.1%} max {max(evs):+.1%}; "
          f"EV>0: {sum(v > 0 for v in evs)}; SGM better than the plain multi in {better}/{len(ok)}; "
          f"{len(combos)} paper combos, {0 if TEST else save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
